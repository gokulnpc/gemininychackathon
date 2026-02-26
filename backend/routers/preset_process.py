"""Preset Process — Option C pipeline: pick a preset → Nemotron auto-configures → video.

Two-phase flow:

  PHASE 1 — Configure (returns config to frontend so wizard steps are pre-filled):
    POST /api/v1/presets/{preset}/configure
      Stage 0: Build transcript from preset + optional topic_hint
      Stage 1: Reddit Research
      Stage 2: Databricks Analytics
      Stage 3: Nemotron multi-agent reasoning → auto-generate series config
      Stage 4: Auto-create series in S3
      ↳ Returns: series_id, voice_id, art_style, caption_style, music, etc.
        Frontend pre-fills wizard steps 2–7 with these values.

  PHASE 2 — Run pipeline (user has confirmed/modified wizard steps):
    POST /api/v1/projects/{project_id}/preset-process
      Accepts series_id + transcript from Phase 1 (skips Nemotron)
      Runs the normal pipeline: Claude script → images → voiceover → compose → S3
      Returns SmartProcessResponse (same shape as smart-process).

No audio file required — the preset supplies the topic idea.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel  # noqa: E402

from models.schemas import (
    ArtStyle,
    CaptionStyleEnum,
    MusicPreset,
    NemotronSeriesConfig,
    Platform,
    PipelineStageStatus,
    PresetConfigureResponse,
    PresetKey,
    PresetProcessRequest,
    SeriesConfig,
    SmartProcessResponse,
    VideoFormat,
    VideoDurationRange,
)


from services import gemini_reasoning as nemotron, reddit, s3
from services.pipeline_runner import DURATION_MAP, run_pipeline_stages


class TextConfigureRequest(BaseModel):
    transcript: str
    target_platforms: list[Platform] = [Platform.instagram_reels]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["preset-process"])


# ── Preset definitions ────────────────────────────────────────────────────────

_PRESETS: dict[PresetKey, dict] = {
    PresetKey.scary_stories: {
        "name": "Scary Stories",
        "niche": "horror",
        "topic": (
            "Create a chilling scary story with atmospheric dread and suspense. "
            "Focus on psychological horror, the unknown, or supernatural elements "
            "that leave the viewer unsettled. Build tension slowly and deliver a "
            "shocking or haunting conclusion."
        ),
    },
    PresetKey.history: {
        "name": "History",
        "niche": "history",
        "topic": (
            "Share a fascinating, lesser-known historical event or story that most "
            "people don't know about. Choose something dramatic, surprising, or that "
            "changed the course of history. Span ancient to modern times."
        ),
    },
    PresetKey.true_crime: {
        "name": "True Crime",
        "niche": "true_crime",
        "topic": (
            "Tell a gripping true crime story about a real case — a mystery, "
            "unsolved disappearance, or notorious crime. Focus on the facts, "
            "the investigation, and the human drama. Keep it compelling and factual."
        ),
    },
    PresetKey.stoic_motivation: {
        "name": "Stoic Motivation",
        "niche": "motivation",
        "topic": (
            "Share powerful stoic philosophy wisdom and life lessons that can help "
            "people overcome adversity, build resilience, and live with purpose. "
            "Reference Marcus Aurelius, Epictetus, or Seneca. Make it actionable "
            "and deeply motivating."
        ),
    },
    PresetKey.marketing_business: {
        "name": "Marketing & Business",
        "niche": "business",
        "topic": (
            "Share a powerful marketing insight, business growth strategy, or "
            "entrepreneurship lesson. Include a real-world example or case study. "
            "Make it practical, data-driven, and immediately actionable for "
            "founders, marketers, and business owners."
        ),
    },
    PresetKey.tech_innovation: {
        "name": "Tech & Innovation",
        "niche": "technology",
        "topic": (
            "Explain a cutting-edge technology, AI breakthrough, or innovation "
            "that is changing the world right now. Break down complex concepts "
            "simply. Focus on the real-world impact and what it means for the future."
        ),
    },
}

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


async def _run_nemotron_configure(
    preset_key: PresetKey,
    target_platforms: list[str],
    topic_hint: str | None,
) -> tuple[str, str, SeriesConfig, dict, list[PipelineStageStatus]]:
    """Run Stages 0-4: build topic → Reddit → Analytics → Nemotron → S3 series.

    Returns (transcript, series_id, series_config, nemotron_cfg_raw, stages).
    Shared by both the /configure endpoint and the preset-process endpoint.
    """
    preset_def = _PRESETS[preset_key]
    stages: list[PipelineStageStatus] = []

    # Stage 0: build transcript
    stages.append(PipelineStageStatus(stage="build_topic", status="running"))
    base_topic = preset_def["topic"]
    if topic_hint:
        transcript = f"{base_topic}\n\nSpecific angle: {topic_hint}"
        stages[-1].detail = f"Preset: {preset_def['name']} | Angle: {topic_hint}"
    else:
        transcript = base_topic
        stages[-1].detail = f"Preset: {preset_def['name']} ({preset_def['niche']})"
    stages[-1].status = "completed"

    # Stage 1: Reddit research
    stages.append(PipelineStageStatus(
        stage="reddit_research",
        status="running",
        detail=f"Fetching trending {preset_def['niche']} posts from Reddit",
    ))
    reddit_ctx: dict = {}
    try:
        reddit_ctx = await reddit.fetch_trending(
            niche=preset_def["niche"],
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
    except Exception as reddit_err:
        logger.warning("Reddit research failed (non-fatal): %s", reddit_err)
        stages[-1].status = "completed"
        stages[-1].detail = "Reddit research skipped (network unavailable)"

    # Stage 3: Nemotron multi-agent config
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
        target_platforms=target_platforms,
        reddit_context=reddit_ctx or None,
        analytics_context=None,
    )
    if not nemotron_cfg_raw:
        logger.warning("Nemotron unavailable — using fallback defaults")
        nemotron_cfg_raw = _DEFAULT_CONFIG.copy()
        nemotron_cfg_raw["niche"] = preset_def["niche"]
        nemotron_cfg_raw["series_name"] = preset_def["name"]

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"Auto-configured: art={nemotron_cfg_raw.get('art_style')} "
        f"music={nemotron_cfg_raw.get('background_music')} "
        f"voice={nemotron_cfg_raw.get('voice_name')} "
        f"captions={nemotron_cfg_raw.get('caption_style')}"
    )

    # Stage 4: Save series to S3
    stages.append(PipelineStageStatus(stage="create_series", status="running"))
    series = _build_series_config(nemotron_cfg_raw)
    series_id = str(uuid4())
    try:
        await s3.store_json(series.model_dump(), f"series/{series_id}/config.json")
        nemotron_cfg_raw["series_id"] = series_id
        stages[-1].status = "completed"
        stages[-1].detail = f"Auto-created series {series_id} ({series.series_name})"
    except Exception as e:
        logger.warning("Could not save auto-series to S3: %s", e)
        stages[-1].status = "completed"
        stages[-1].detail = "Series config built in-memory (S3 save failed)"

    return transcript, series_id, series, nemotron_cfg_raw, stages


async def _run_text_configure(
    transcript: str,
    target_platforms: list[str],
) -> tuple[str, str, "SeriesConfig", dict, list["PipelineStageStatus"]]:
    """Run Reddit → Databricks → Nemotron on a free-form user transcript.

    Same as _run_nemotron_configure but uses the user's text directly (no preset).
    Returns (transcript, series_id, series_config, nemotron_cfg_raw, stages).
    """
    stages: list[PipelineStageStatus] = []

    # Stage 1: Reddit research based on the user's text
    stages.append(PipelineStageStatus(
        stage="reddit_research",
        status="running",
        detail="Fetching trending topics from Reddit based on your idea",
    ))
    reddit_ctx: dict = {}
    try:
        reddit_ctx = await reddit.fetch_trending(niche=None, transcript=transcript)
        detected_niche = reddit_ctx.get("niche", "unknown")
        n_hot = len(reddit_ctx.get("hot_posts", []))
        n_controversial = len(reddit_ctx.get("controversial_posts", []))
        subreddits_str = ", ".join(f"r/{s}" for s in reddit_ctx.get("subreddits_searched", []))
        stages[-1].status = "completed"
        stages[-1].detail = (
            f"Niche: {detected_niche} | {subreddits_str} | "
            f"{n_hot} hot + {n_controversial} controversial posts"
        )
    except Exception as reddit_err:
        logger.warning("Reddit research failed (non-fatal): %s", reddit_err)
        stages[-1].status = "completed"
        stages[-1].detail = "Reddit research skipped (network unavailable)"

    # Stage 2: Databricks analytics
    stages.append(PipelineStageStatus(
        stage="analytics_research",
        status="running",
        detail="Querying Databricks for historical performance data",
    ))
    analytics_ctx: dict = {}
    try:
        art_perf, niche_perf = await asyncio.gather(
            analytics.get_art_style_performance(),
            analytics.get_top_niches(),
            return_exceptions=False,
        )
        if art_perf or niche_perf:
            analytics_ctx = {
                "art_style_performance": art_perf[:5] if art_perf else [],
                "top_niches": niche_perf[:5] if niche_perf else [],
                "total_runs": sum(r.get("runs", 0) for r in art_perf) if art_perf else 0,
            }
            best_art = art_perf[0].get("art_style", "n/a") if art_perf else "n/a"
            best_niche = niche_perf[0].get("niche", "n/a") if niche_perf else "n/a"
            stages[-1].status = "completed"
            stages[-1].detail = (
                f"Best art style: {best_art} | Best niche: {best_niche} | "
                f"{analytics_ctx['total_runs']} historical runs"
            )
        else:
            stages[-1].status = "completed"
            stages[-1].detail = "No historical data yet — Nemotron using transcript + Reddit only"
    except Exception as analytics_err:
        logger.warning("Analytics research failed (non-fatal): %s", analytics_err)
        stages[-1].status = "completed"
        stages[-1].detail = "Analytics skipped (Databricks not configured)"

    # Stage 3: Nemotron multi-agent config
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
        target_platforms=target_platforms,
        reddit_context=reddit_ctx or None,
        analytics_context=analytics_ctx or None,
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

    # Stage 4: Save series to S3
    stages.append(PipelineStageStatus(stage="create_series", status="running"))
    series = _build_series_config(nemotron_cfg_raw)
    series_id = str(uuid4())
    try:
        await s3.store_json(series.model_dump(), f"series/{series_id}/config.json")
        nemotron_cfg_raw["series_id"] = series_id
        stages[-1].status = "completed"
        stages[-1].detail = f"Auto-created series {series_id} ({series.series_name})"
    except Exception as e:
        logger.warning("Could not save auto-series to S3: %s", e)
        stages[-1].status = "completed"
        stages[-1].detail = "Series config built in-memory (S3 save failed)"

    return transcript, series_id, series, nemotron_cfg_raw, stages


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/presets")
async def list_presets():
    """List all available content presets with their names, niches and descriptions."""
    return {
        "presets": [
            {
                "key": key.value,
                "name": cfg["name"],
                "niche": cfg["niche"],
                "description": cfg["topic"][:120] + "...",
            }
            for key, cfg in _PRESETS.items()
        ]
    }


@router.post("/presets/{preset}/configure", response_model=PresetConfigureResponse)
async def configure_preset(preset: PresetKey, request: PresetProcessRequest):
    """Phase 1 — Run Nemotron and return the auto-generated series config.

    The frontend calls this when the user selects a preset. It runs:
      Reddit research + Databricks analytics + Nemotron multi-agent config

    Returns the generated series_id, voice, music, art style, caption style, etc.
    so the frontend can pre-fill wizard steps 2–7. The user can then review/modify
    the choices and click Continue to trigger Phase 2 (the pipeline).
    """
    try:
        transcript, series_id, series, nemotron_cfg_raw, stages = await _run_nemotron_configure(
            preset_key=preset,
            target_platforms=[p.value for p in request.target_platforms],
            topic_hint=request.topic_hint,
        )
    except Exception as e:
        logger.exception("Preset configure failed for %s", preset)
        raise HTTPException(status_code=500, detail=f"Configuration failed: {e}")

    # Resolve effective platforms from Nemotron output
    effective_platforms = nemotron_cfg_raw.get("target_platforms", [p.value for p in request.target_platforms])

    return PresetConfigureResponse(
        series_id=series_id,
        series_name=series.series_name,
        transcript=transcript,
        voice_id=series.voice_id,
        voice_name=nemotron_cfg_raw.get("voice_name", "Rachel"),
        art_style=series.art_style.value,
        caption_style=series.caption_style.value,
        background_music=series.background_music.value,
        music_volume=series.music_volume,
        video_duration=series.video_duration.value,
        video_format=series.video_format.value,
        target_platforms=effective_platforms if isinstance(effective_platforms, list) else [str(effective_platforms)],
        nemotron_reasoning=nemotron_cfg_raw.get("reasoning", ""),
        configured_by=nemotron_cfg_raw.get("configured_by", "nemotron"),
        stages=stages,
    )


@router.post("/text/configure", response_model=PresetConfigureResponse)
async def configure_text(request: TextConfigureRequest):
    """Phase 1 for Text-to-Video — runs Reddit + Databricks + Nemotron on user's typed idea.

    Returns the same PresetConfigureResponse shape as /presets/{preset}/configure so the
    frontend can reuse the same ScriptReview + generate-video flow.
    """
    if not request.transcript or not request.transcript.strip():
        raise HTTPException(status_code=422, detail="transcript must not be empty")

    try:
        transcript, series_id, series, nemotron_cfg_raw, stages = await _run_text_configure(
            transcript=request.transcript,
            target_platforms=[p.value for p in request.target_platforms],
        )
    except Exception as e:
        logger.exception("Text configure failed")
        raise HTTPException(status_code=500, detail=f"Configuration failed: {e}")

    effective_platforms = nemotron_cfg_raw.get(
        "target_platforms", [p.value for p in request.target_platforms]
    )

    return PresetConfigureResponse(
        series_id=series_id,
        series_name=series.series_name,
        transcript=transcript,
        voice_id=series.voice_id,
        voice_name=nemotron_cfg_raw.get("voice_name", "Rachel"),
        art_style=series.art_style.value,
        caption_style=series.caption_style.value,
        background_music=series.background_music.value,
        music_volume=series.music_volume,
        video_duration=series.video_duration.value,
        video_format=series.video_format.value,
        target_platforms=effective_platforms if isinstance(effective_platforms, list) else [str(effective_platforms)],
        nemotron_reasoning=nemotron_cfg_raw.get("reasoning", ""),
        configured_by=nemotron_cfg_raw.get("configured_by", "nemotron"),
        stages=stages,
    )


@router.post("/projects/{project_id}/preset-process", response_model=SmartProcessResponse)
async def preset_process(project_id: UUID, request: PresetProcessRequest):
    """Phase 2 — Run the video pipeline for a preset.

    Two modes:
    a) Fast path (recommended): supply series_id + transcript from Phase 1
       (/presets/{preset}/configure). Nemotron stages are skipped.
    b) Full path: omit series_id + transcript — Nemotron runs inline before the pipeline.
    """
    stages: list[PipelineStageStatus] = []
    work_dir = tempfile.mkdtemp(prefix=f"voicevid_preset_{project_id}_")
    nemotron_cfg_raw: dict = {}

    try:
        # ── Decide whether to re-run Nemotron or use pre-built series ─────────
        if request.series_id and request.transcript:
            # Fast path: load the series config that was saved in Phase 1
            stages.append(PipelineStageStatus(
                stage="load_series",
                status="running",
                detail=f"Loading pre-configured series {request.series_id}",
            ))
            try:
                config_data = await s3.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
                auto_series_id = request.series_id
                transcript = request.transcript
                stages[-1].status = "completed"
                stages[-1].detail = f"Loaded series {auto_series_id} ({series.series_name})"
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

            # Resolve platforms from series (Nemotron's choice is in the saved config)
            effective_platforms = request.target_platforms

        else:
            # Full path: run Nemotron inline
            transcript, auto_series_id, series, nemotron_cfg_raw, config_stages = (
                await _run_nemotron_configure(
                    preset_key=request.preset,
                    target_platforms=[p.value for p in request.target_platforms],
                    topic_hint=request.topic_hint,
                )
            )
            stages.extend(config_stages)

            # Resolve effective platforms from Nemotron output
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

        # ── Normal pipeline (Claude script → images → voice → compose → S3) ──
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

        # ── Save project metadata ─────────────────────────────────────────────
        quality_score = script.metadata.get("agent_quality_score") if script else None
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "project_id":       str(project_id),
            "created_at":       created_at,
            "status":           "completed",
            "series_id":        auto_series_id,
            "series_name":      series.series_name,
            "hook":             script.hook.text if script else None,
            "scenes_count":     len(script.scenes) if script else 0,
            "voiceover_duration": None,
            "platforms":        [p.value for p in effective_platforms],
            "video_urls":       video_urls,
            "preset":           request.preset.value,
            "nemotron_configured": True,
        }
        try:
            await s3.store_json(metadata, f"projects/{project_id}/metadata.json")
        except Exception:
            logger.warning("Failed to save preset-process metadata for %s", project_id)

        nemotron_config_model = None
        if nemotron_cfg_raw:
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
        logger.exception("Preset-process pipeline failed for project %s", project_id)
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
                    "status":     "failed",
                    "platforms":  [p.value for p in request.target_platforms],
                    "video_urls": {},
                    "preset":     request.preset.value,
                    "error":      str(e),
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
