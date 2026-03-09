"""Worker orchestration — runs the full video generation pipeline.

Called by the worker router after receiving a Cloud Tasks callback.
Responsibilities:
  1. Update Firestore: status="in_progress", started_at
  2. Run run_pipeline_stages() — writes per-stage progress to Firestore
  3. On success: update Firestore with completed status + video_urls, send email
  4. On failure: update Firestore with failed status + error, send failure email

This module is the single place that translates pipeline stage completion events
into Firestore progress updates, ensuring the status endpoint always reflects
the live state of the job.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from uuid import UUID

from models.schemas import (
    ArtStyle,
    CaptionStyleEnum,
    GenerateVideoRequest,
    MusicPreset,
    SeriesConfig,
    VideoFormat,
    VideoDurationRange,
)
from routers.catalog import DURATION_MAP
from services.storage import firestore_db, gcs

logger = logging.getLogger(__name__)

# Stage name → progress percentage mapping (rough estimate)
_STAGE_PROGRESS: dict[str, int] = {
    "script_generation": 5,
    "voiceover":         15,
    "video_generation":  25,
    "visual_qa":         65,
    "thumbnail":         70,
    "captions":          75,
    "composition":       85,
    "export_upload":     95,
}


async def _update_status(project_id: str, **fields) -> None:
    """Patch Firestore project document with new fields (best-effort)."""
    try:
        existing = await firestore_db.get_project(project_id) or {}
        existing.update(fields)
        await firestore_db.save_project(project_id, existing)
    except Exception as exc:
        logger.warning("Failed to update Firestore status for %s: %s", project_id, exc)


async def run_generation(project_id: UUID, request: GenerateVideoRequest) -> None:
    """Execute the full video generation pipeline for an async job.

    Updates Firestore throughout so clients polling /status always see live state.
    Sends email notification on completion or failure.
    """
    import base64
    from services.pipeline_runner import run_pipeline_stages

    pid = str(project_id)
    started_at = datetime.now(timezone.utc).isoformat()
    await _update_status(
        pid,
        status="generating_video",
        started_at=started_at,
        current_stage="initialising",
        progress_pct=1,
    )

    work_dir = tempfile.mkdtemp(prefix=f"voicevid_worker_{project_id}_")
    user_ref_path: str | None = None

    try:
        # ── Resolve series ────────────────────────────────────────────────────
        series: SeriesConfig | None = None

        if request.series_id:
            try:
                config_data = await gcs.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
            except Exception as e:
                raise RuntimeError(f"Series '{request.series_id}' not found: {e}") from e

        elif request.voice_id or request.art_style_override or request.music_preset_override:
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

        # ── Decode user reference photo ───────────────────────────────────────
        if request.user_reference_image_b64 and request.user_character_role:
            try:
                img_bytes = base64.b64decode(request.user_reference_image_b64)
                ref_fd, user_ref_path = tempfile.mkstemp(suffix=".png", prefix="voicevid_userref_")
                with os.fdopen(ref_fd, "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                logger.warning("Failed to decode user_reference_image_b64: %s — ignoring", e)
                user_ref_path = None

        # ── Run pipeline (pipeline_runner writes per-stage Firestore updates) ─
        await _update_status(pid, current_stage="pipeline", progress_pct=5)

        async def _on_progress(stage: str, label: str, pct: int) -> None:
            await _update_status(
                pid,
                status="generating_video",
                current_stage=label,
                progress_pct=pct,
            )

        pipeline_stages, video_urls, script, thumbnail_url, visual_qa_report, project_json = await run_pipeline_stages(
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
            user_reference_path=user_ref_path,
            user_character_role=request.user_character_role.value if request.user_character_role else None,
            on_progress=_on_progress,
        )

        # ── Save completion state ─────────────────────────────────────────────
        completed_at = datetime.now(timezone.utc).isoformat()
        stages_data = [s.model_dump() for s in pipeline_stages]
        await _update_status(
            pid,
            status="completed",
            current_stage=None,
            progress_pct=100,
            completed_at=completed_at,
            video_urls=video_urls,
            stages=stages_data,
            hook=script.hook.text if script else None,
            scenes_count=len(script.scenes) if script else 0,
            thumbnail_url=thumbnail_url,
            voiceover_full_script=script.voiceover_full_script if script else None,
            caption_style=request.caption_style.value,
            background_music=series.background_music.value if series else "none",
            video_duration=video_duration,
            series_id=request.series_id,
            series_name=series.series_name if series else None,
            project_json=project_json if project_json else None,
        )

        logger.info("Worker: project %s completed. video_urls=%s", pid, list(video_urls.keys()))

        # ── Send success email ────────────────────────────────────────────────
        if request.user_email:
            try:
                from services.integrations import email_notifier
                await email_notifier.send_video_ready(
                    to_email=request.user_email,
                    project_id=pid,
                    video_urls=video_urls,
                    thumbnail_url=thumbnail_url,
                )
            except Exception as mail_exc:
                logger.warning("Email notification failed (non-fatal): %s", mail_exc)

        # ── Record feedback ───────────────────────────────────────────────────
        if script and script.hook:
            try:
                from services.storage import feedback_store
                await feedback_store.record_project_outcome(
                    project_id=pid,
                    hook_text=script.hook.text,
                    niche=series.niche if series and series.niche else "default",
                    art_style=series.art_style.value if series else "realism",
                    quality_score=float(script.metadata.get("agent_quality_score", 0)),
                    platforms=[p.value for p in request.target_platforms],
                    scenes_count=len(script.scenes),
                )
            except Exception:
                pass

    except Exception as exc:
        logger.exception("Worker: project %s FAILED", pid)
        failed_at = datetime.now(timezone.utc).isoformat()
        await _update_status(
            pid,
            status="failed",
            current_stage=None,
            progress_pct=None,
            completed_at=failed_at,
            error=str(exc),
        )

        if request.user_email:
            try:
                from services.integrations import email_notifier
                await email_notifier.send_generation_failed(
                    to_email=request.user_email,
                    project_id=pid,
                    error=str(exc),
                )
            except Exception as mail_exc:
                logger.warning("Failure email also failed: %s", mail_exc)

        raise  # re-raise so Cloud Tasks retries if applicable

    finally:
        if user_ref_path:
            try:
                os.unlink(user_ref_path)
            except OSError:
                pass
