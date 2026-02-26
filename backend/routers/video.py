"""Generate-video router — shared Phase 2 endpoint for all three input flows.

POST /api/v1/projects/{project_id}/generate-video

Accepts the ScriptGenerationResponse returned by /generate-script (after the
user reviewed and approved it) plus the final video config. Runs:

  Veo 3 (one clip per scene) → captions → FFmpeg compose → S3 upload

Returns PipelineResponse with per-stage status and S3 video URLs.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.schemas import (
    ArtStyle,
    CaptionStyleEnum,
    GenerateVideoRequest,
    MusicPreset,
    PipelineResponse,
    PipelineStageStatus,
    SeriesConfig,
    VideoFormat,
    VideoDurationRange,
)
from routers.catalog import DURATION_MAP
from services import gcs
from services.pipeline_runner import run_pipeline_stages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["video"])


@router.post("/projects/{project_id}/generate-video", response_model=PipelineResponse)
async def generate_video(project_id: UUID, request: GenerateVideoRequest):
    """Generate video from a user-confirmed script.

    Runs Veo 3 clip generation → captions → FFmpeg composition → S3 upload.
    Returns video URLs for each requested platform plus a master copy.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_gv_{project_id}_")

    try:
        # ── Resolve series config (series wins; fallback to per-field overrides) ──
        series: SeriesConfig | None = None

        if request.series_id:
            try:
                config_data = await gcs.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
                logger.info("Loaded series %s (%s)", request.series_id, series.series_name)
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

        elif request.voice_id or request.art_style_override or request.music_preset_override:
            # Build a minimal SeriesConfig from the per-field overrides
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

        # ── Run pipeline stages 4–7: Veo clips → captions → compose → upload ──
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

        # ── Save project metadata ─────────────────────────────────────────────
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "project_id":         str(project_id),
            "created_at":         created_at,
            "status":             "completed",
            "series_id":          request.series_id,
            "series_name":        series.series_name if series else None,
            "hook":               script.hook.text if script else None,
            "scenes_count":       len(script.scenes) if script else 0,
            "voiceover_duration": None,
            "platforms":          [p.value for p in request.target_platforms],
            "video_urls":         video_urls,
        }
        try:
            await gcs.store_json(metadata, f"projects/{project_id}/metadata.json")
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
            await gcs.store_json(
                {
                    "project_id": str(project_id),
                    "created_at": failed_at,
                    "status":     "failed",
                    "platforms":  [p.value for p in request.target_platforms],
                    "video_urls": {},
                    "error":      str(e),
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
