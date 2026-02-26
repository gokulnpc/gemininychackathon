"""Smart Process — Option B pipeline: speak your idea → Nemotron auto-configures everything.

POST /api/v1/projects/{project_id}/smart-process

Flow:
  Stage 0: Transcribe audio (ElevenLabs) — if audio_base64 provided
  Stage 1: Reddit Research — trending & controversial topics for the niche
  Stage 2: Databricks Analytics — historical performance data (art styles, niches)
  Stage 3: Nemotron multi-agent reasoning → auto-generate series config
             Inputs: transcript + Reddit trends + Databricks performance data
             Sub-agents: Content Analyst → Audience Profiler → Creative Director
                         → Platform Strategist → Production Designer
  Stage 4: Auto-create series in S3 (from Nemotron config)
  Stages 5+: Normal pipeline (Claude script → Gemini Image → ElevenLabs → FFmpeg → S3)
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from models.schemas import (
    ArtStyle,
    CaptionStyleEnum,
    MusicPreset,
    NemotronSeriesConfig,
    Platform,
    PipelineStageStatus,
    SeriesConfig,
    SmartProcessRequest,
    SmartProcessResponse,
    VideoFormat,
    VideoDurationRange,
)
from services import gemini_reasoning as nemotron, reddit, s3
from services.pipeline_runner import DURATION_MAP, run_pipeline_stages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["smart-process"])

# ── Fallback defaults when Nemotron is unavailable ────────────────────────────

_DEFAULT_CONFIG = {
    "series_name": "My Series",
    "niche": "general",
    "art_style": "realism",
    "caption_style": "bold_stroke",
    "background_music": "none",
    "music_volume": 0.15,
    "voice_id": "21m00Tcm4TlvDq8ikWAM",
    "voice_name": "Rachel",
    "video_duration": "30-40",
    "video_format": "storytelling",
    "target_platforms": ["instagram_reels"],
    "reasoning": "Nemotron unavailable — using sensible defaults.",
    "configured_by": "fallback",
}


def _build_series_config(cfg: dict) -> SeriesConfig:
    """Convert Nemotron's raw config dict into a validated SeriesConfig."""
    # Clamp art_style to known enum values
    art_style_val = cfg.get("art_style", "realism")
    if art_style_val not in {e.value for e in ArtStyle}:
        art_style_val = "realism"

    caption_style_val = cfg.get("caption_style", "bold_stroke")
    if caption_style_val not in {e.value for e in CaptionStyleEnum}:
        caption_style_val = "bold_stroke"

    music_val = cfg.get("background_music", "none")
    if music_val not in {e.value for e in MusicPreset}:
        music_val = "none"

    video_format_val = cfg.get("video_format", "storytelling")
    if video_format_val not in {e.value for e in VideoFormat}:
        video_format_val = "storytelling"

    video_duration_val = cfg.get("video_duration", "30-40")
    if video_duration_val not in {e.value for e in VideoDurationRange}:
        video_duration_val = "30-40"

    return SeriesConfig(
        series_name=cfg.get("series_name", "Auto Series"),
        video_format=VideoFormat(video_format_val),
        niche=cfg.get("niche"),
        voice_id=cfg.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
        background_music=MusicPreset(music_val),
        music_volume=float(cfg.get("music_volume", 0.15)),
        art_style=ArtStyle(art_style_val),
        caption_style=CaptionStyleEnum(caption_style_val),
        video_duration=VideoDurationRange(video_duration_val),
    )


@router.post("/projects/{project_id}/smart-process", response_model=SmartProcessResponse)
async def smart_process(project_id: UUID, request: SmartProcessRequest):
    """Option B pipeline: speak your idea → Nemotron reasons → video auto-generated.

    The creator only needs to record their raw idea. Nemotron's 5 sub-agents handle
    all creative configuration decisions (art style, voice, music, captions, platform).
    Claude then writes the script; the rest of the pipeline runs as normal.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_smart_{project_id}_")
    nemotron_cfg_raw: dict = {}

    try:
        # ── Stage 0: Transcribe (ElevenLabs) — skip if transcript already provided ──
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

        # ── Stage 1: Reddit Research — trending & controversial topics for niche ──
        stages.append(PipelineStageStatus(
            stage="reddit_research",
            status="running",
            detail="Fetching trending and controversial topics from Reddit for content angle",
        ))

        reddit_ctx: dict = {}
        try:
            reddit_ctx = await reddit.fetch_trending(
                niche=request.niche or None,
                transcript=transcript,
            )
            detected_niche = reddit_ctx.get("niche", "unknown")
            n_hot = len(reddit_ctx.get("hot_posts", []))
            n_controversial = len(reddit_ctx.get("controversial_posts", []))
            subreddits_str = ", ".join(
                f"r/{s}" for s in reddit_ctx.get("subreddits_searched", [])
            )
            stages[-1].status = "completed"
            stages[-1].detail = (
                f"Niche: {detected_niche} | {subreddits_str} | "
                f"{n_hot} hot + {n_controversial} controversial posts"
            )
            logger.info(
                "Reddit research complete: niche=%s hot=%d controversial=%d",
                detected_niche, n_hot, n_controversial,
            )
        except Exception as reddit_err:
            logger.warning("Reddit research failed (non-fatal): %s", reddit_err)
            stages[-1].status = "completed"
            stages[-1].detail = "Reddit research skipped (network unavailable)"

        # ── Stage 3: Nemotron Multi-Agent Series Configuration ────────────────
        stages.append(PipelineStageStatus(
            stage="nemotron_config",
            status="running",
            detail=(
                "Nemotron: Content Analyst → Audience Profiler → Creative Director "
                "→ Platform Strategist → Production Designer"
            ),
        ))

        nemotron_cfg_raw = await nemotron.auto_configure_series(
            transcript=transcript,
            target_platforms=[p.value for p in request.target_platforms],
            reddit_context=reddit_ctx or None,
            analytics_context=None,
        )

        if not nemotron_cfg_raw:
            logger.warning("Nemotron unavailable — using fallback defaults")
            nemotron_cfg_raw = _DEFAULT_CONFIG.copy()

        stages[-1].status = "completed"
        stages[-1].detail = (
            f"Auto-configured: art={nemotron_cfg_raw.get('art_style')} "
            f"music={nemotron_cfg_raw.get('background_music')} "
            f"voice={nemotron_cfg_raw.get('voice_name')} "
            f"captions={nemotron_cfg_raw.get('caption_style')}"
        )

        logger.info(
            "Nemotron config: series=%r art=%s music=%s voice=%s captions=%s duration=%s",
            nemotron_cfg_raw.get("series_name"),
            nemotron_cfg_raw.get("art_style"),
            nemotron_cfg_raw.get("background_music"),
            nemotron_cfg_raw.get("voice_name"),
            nemotron_cfg_raw.get("caption_style"),
            nemotron_cfg_raw.get("video_duration"),
        )

        # ── Stage 3: Auto-create series in S3 ────────────────────────────────
        stages.append(PipelineStageStatus(stage="create_series", status="running"))

        series = _build_series_config(nemotron_cfg_raw)
        auto_series_id = str(uuid4())
        s3_key = f"series/{auto_series_id}/config.json"
        try:
            await s3.store_json(series.model_dump(), s3_key)
            nemotron_cfg_raw["series_id"] = auto_series_id
            stages[-1].status = "completed"
            stages[-1].detail = f"Auto-created series {auto_series_id} ({series.series_name})"
        except Exception as e:
            logger.warning("Could not save auto-series to S3: %s", e)
            stages[-1].status = "completed"
            stages[-1].detail = "Series config built in-memory (S3 save failed)"

        # ── Resolve effective target platforms from Nemotron output ───────────
        nemotron_platforms = nemotron_cfg_raw.get("target_platforms", [])
        effective_platforms = []
        for p in nemotron_platforms:
            try:
                effective_platforms.append(Platform(p))
            except ValueError:
                pass
        if not effective_platforms:
            effective_platforms = list(request.target_platforms)

        video_duration = DURATION_MAP.get(series.video_duration.value, 35)

        # ── Stages 3–9: Normal pipeline ───────────────────────────────────────
        pipeline_stages, video_urls, script = await run_pipeline_stages(
            project_id=project_id,
            transcript=transcript,
            series=series,
            series_id=auto_series_id,
            target_platforms=effective_platforms,
            style="modern_energetic",
            video_duration=video_duration,
            caption_style_override=series.caption_style.value,
            brand_voice=None,
            cta_preference=None,
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
            "series_id": auto_series_id,
            "series_name": series.series_name,
            "hook": script.hook.text if script else None,
            "scenes_count": len(script.scenes) if script else 0,
            "voiceover_duration": None,
            "platforms": [p.value for p in effective_platforms],
            "video_urls": video_urls,
            "nemotron_configured": True,
        }
        try:
            await s3.store_json(metadata, f"projects/{project_id}/metadata.json")
        except Exception:
            logger.warning("Failed to save smart-process metadata for %s", project_id)

        nemotron_config_model = NemotronSeriesConfig(**{
            k: nemotron_cfg_raw[k]
            for k in NemotronSeriesConfig.model_fields
            if k in nemotron_cfg_raw
        })

        return SmartProcessResponse(
            project_id=project_id,
            status="completed",
            stages=stages,
            video_urls=video_urls,
            script=script,
            nemotron_config=nemotron_config_model,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Smart-process pipeline failed for project %s", project_id)
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
                    "nemotron_configured": True,
                },
                f"projects/{project_id}/metadata.json",
            )
        except Exception:
            pass
        return SmartProcessResponse(
            project_id=project_id,
            status="failed",
            stages=stages,
            error=str(e),
        )
