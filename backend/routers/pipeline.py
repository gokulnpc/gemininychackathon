import logging
import tempfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.schemas import (
    ArtStyle,
    CaptionStyleEnum,
    GenerateScriptRequest,
    GenerateVideoRequest,
    MusicPreset,
    PipelineRequest,
    PipelineResponse,
    PipelineStageStatus,
    ScriptGenerationResponse,
    SeriesConfig,
    VideoDurationRange,
    VideoFormat,
)
from routers.series import DURATION_MAP
from services import s3
from services.gemini_agent import generate_script_with_agent
from services.pipeline_runner import run_pipeline_stages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


@router.post("/projects/{project_id}/process", response_model=PipelineResponse)
async def process_pipeline(project_id: UUID, request: PipelineRequest):
    """Run the full VoiceVid pipeline: transcribe → agent script → video → voiceover → compose.

    Option A — user fills the form manually.
    Stage 2 uses a Claude Agent SDK loop (claude-sonnet-4-6) + Nemotron sub-agent for hooks and scoring.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_{project_id}_")

    try:
        # ── Load series config (if series_id provided) ────────────────────────
        series: SeriesConfig | None = None
        if request.series_id:
            try:
                config_data = await s3.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
                logger.info("Loaded series config %s (%s)", request.series_id, series.series_name)
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

        # ── Stage 1: Transcription ────────────────────────────────────────────
        stages.append(PipelineStageStatus(stage="transcribe", status="running"))

        if request.transcript:
            transcript = request.transcript
            stages[-1].status = "completed"
            stages[-1].detail = "Used provided transcript"
        else:
            raise HTTPException(
                status_code=422,
                detail="Provide either audio_base64 or transcript",
            )

        # ── Stages 2–7: Script → Video → Voiceover → Captions → Compose → Upload ──
        video_duration = (
            DURATION_MAP.get(series.video_duration.value, request.video_duration)
            if series else request.video_duration
        )

        pipeline_stages, video_urls, script = await run_pipeline_stages(
            project_id=project_id,
            transcript=transcript,
            series=series,
            series_id=request.series_id,
            target_platforms=request.target_platforms,
            style=request.style.value,
            video_duration=video_duration,
            caption_style_override=request.caption_style.value,
            brand_voice=request.brand_voice,
            cta_preference=request.cta_preference,
            work_dir=work_dir,
        )
        stages.extend(pipeline_stages)

        # ── Save project metadata (powers dashboard) ──────────────────────────
        quality_score = script.metadata.get("agent_quality_score") if script else None
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "project_id": str(project_id),
            "created_at": created_at,
            "status": "completed",
            "series_id": request.series_id,
            "series_name": series.series_name if series else None,
            "hook": script.hook.text if script else None,
            "scenes_count": len(script.scenes) if script else 0,
            "voiceover_duration": None,
            "platforms": [p.value for p in request.target_platforms],
            "video_urls": video_urls,
        }
        try:
            await s3.store_json(metadata, f"projects/{project_id}/metadata.json")
        except Exception:
            logger.warning("Failed to save project metadata for %s", project_id)

        return PipelineResponse(
            project_id=project_id,
            status="completed",
            stages=stages,
            video_urls=video_urls,
            script=script,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pipeline failed for project %s", project_id)
        for stage in stages:
            if stage.status == "running":
                stage.status = "failed"
                stage.detail = str(e)
        failed_at = datetime.now(timezone.utc).isoformat()
        try:
            await s3.store_json(
                {
                    "project_id": str(project_id),
                    "created_at": failed_at,
                    "status": "failed",
                    "series_id": request.series_id,
                    "platforms": [p.value for p in request.target_platforms],
                    "video_urls": {},
                    "error": str(e),
                },
                f"projects/{project_id}/metadata.json",
            )
        except Exception:
            pass
        return PipelineResponse(
            project_id=project_id,
            status="failed",
            stages=stages,
            error=str(e),
        )


# ── Two-phase Speech/Text flow ────────────────────────────────────────────────


@router.post("/projects/{project_id}/generate-script", response_model=ScriptGenerationResponse)
async def generate_script_only(project_id: UUID, request: GenerateScriptRequest):
    """Phase 1 — Transcribe audio (or use provided text) and generate script.

    Returns the full ScriptGenerationResponse so the frontend can display it
    for user review. The user can regenerate as many times as they like.
    When satisfied, they call /generate-video with the confirmed script.
    """
    # Stage 1: resolve transcript
    if request.transcript:
        transcript = request.transcript
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either audio_base64 or transcript",
        )

    # Optionally load series config to pull niche / format hints
    series: SeriesConfig | None = None
    if request.series_id:
        try:
            config_data = await s3.load_json(f"series/{request.series_id}/config.json")
            series = SeriesConfig(**config_data)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

    video_duration = (
        DURATION_MAP.get(series.video_duration.value, request.video_duration)
        if series else request.video_duration
    )

    try:
        script_data = await generate_script_with_agent(
            transcript=transcript,
            target_platforms=[p.value for p in request.target_platforms],
            style=request.style.value,
            video_duration=video_duration,
            brand_voice=request.brand_voice,
            cta_preference=request.cta_preference,
            niche=series.niche if series else None,
            art_style=series.art_style.value if series else "realism",
            video_format=series.video_format.value if series else "storytelling",
        )
    except Exception as e:
        logger.exception("Script generation failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Script generation failed: {e}")

    script = ScriptGenerationResponse(**script_data)
    # Override project_id so it matches the path param
    script.project_id = project_id
    return script


@router.post("/projects/{project_id}/generate-video", response_model=PipelineResponse)
async def generate_video_from_script(project_id: UUID, request: GenerateVideoRequest):
    """Phase 2 — Generate video from a user-confirmed script.

    Accepts the ScriptGenerationResponse returned by /generate-script (after
    the user reviewed and approved it). Runs stages 3-7:
    voiceover → images → captions → compose → upload.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_gv_{project_id}_")

    try:
        # Load series config if provided
        series: SeriesConfig | None = None
        if request.series_id:
            try:
                config_data = await s3.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")
        elif request.voice_id or request.art_style_override or request.music_preset_override:
            # Build a minimal series from per-field overrides
            art_val = request.art_style_override or "realism"
            if art_val not in {e.value for e in ArtStyle}:
                art_val = "realism"
            music_val = request.music_preset_override or "none"
            if music_val not in {e.value for e in MusicPreset}:
                music_val = "none"
            series = SeriesConfig(
                series_name="Custom",
                video_format=VideoFormat.storytelling,
                voice_id=request.voice_id or "21m00Tcm4TlvDq8ikWAM",
                background_music=MusicPreset(music_val),
                art_style=ArtStyle(art_val),
                caption_style=request.caption_style,
                video_duration=VideoDurationRange.medium,
            )

        video_duration = (
            DURATION_MAP.get(series.video_duration.value, request.video_duration)
            if series else request.video_duration
        )

        pipeline_stages, video_urls, script = await run_pipeline_stages(
            project_id=project_id,
            transcript=request.script.voiceover_full_script,
            series=series,
            series_id=request.series_id,
            target_platforms=request.target_platforms,
            style="modern_energetic",
            video_duration=video_duration,
            caption_style_override=request.caption_style.value,
            brand_voice=None,
            cta_preference=None,
            work_dir=work_dir,
            pre_generated_script=request.script,
        )
        stages.extend(pipeline_stages)

        # Save project metadata
        quality_score = script.metadata.get("agent_quality_score") if script else None
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "project_id": str(project_id),
            "created_at": created_at,
            "status": "completed",
            "series_id": request.series_id,
            "series_name": series.series_name if series else None,
            "hook": script.hook.text if script else None,
            "scenes_count": len(script.scenes) if script else 0,
            "voiceover_duration": None,
            "platforms": [p.value for p in request.target_platforms],
            "video_urls": video_urls,
        }
        try:
            await s3.store_json(metadata, f"projects/{project_id}/metadata.json")
        except Exception:
            logger.warning("Failed to save metadata for %s", project_id)

        return PipelineResponse(
            project_id=project_id,
            status="completed",
            stages=stages,
            video_urls=video_urls,
            script=script,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Generate-video failed for project %s", project_id)
        for stage in stages:
            if stage.status == "running":
                stage.status = "failed"
                stage.detail = str(e)
        failed_at = datetime.now(timezone.utc).isoformat()
        try:
            await s3.store_json(
                {
                    "project_id": str(project_id),
                    "created_at": failed_at,
                    "status": "failed",
                    "platforms": [p.value for p in request.target_platforms],
                    "video_urls": {},
                    "error": str(e),
                },
                f"projects/{project_id}/metadata.json",
            )
        except Exception:
            pass
        return PipelineResponse(
            project_id=project_id,
            status="failed",
            stages=stages,
            error=str(e),
        )
