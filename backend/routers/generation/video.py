"""Generate-video router — supports both async queue and synchronous execution.

POST /api/v1/projects/{project_id}/generate-video

ASYNC MODE (Cloud Run, WORKER_URL set):
  - Validates the request
  - Writes project status = "queued" to Firestore
  - Enqueues a Cloud Task to the Worker Service
  - Returns 202 Accepted immediately with {project_id, status, poll_url}
  - Client polls GET /api/v1/projects/{id}/status for progress

SYNC MODE (local dev, WORKER_URL not set):
  - Runs the full pipeline in-process (8-10 min blocking)
  - Returns 200 with PipelineResponse (backward compatible)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from config import get_settings
from deps.auth import get_current_user
from models.schemas import (
    GenerateVideoRequest,
    PipelineResponse,
    PipelineStageStatus,
)
from services.storage import firestore_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["video"])


@router.post("/projects/{project_id}/generate-video")
async def generate_video(project_id: UUID, request: GenerateVideoRequest, current_user: dict = Depends(get_current_user)):
    """Generate video from a user-confirmed script.

    When WORKER_URL is configured (production): returns 202 immediately and
    processes the job asynchronously. Poll GET /projects/{id}/status for updates.

    When WORKER_URL is not set (local dev): runs synchronously and returns
    the full PipelineResponse on completion (may take 8-10 minutes).
    """
    settings = get_settings()
    pid = str(project_id)
    uid = current_user["uid"]
    queued_at = datetime.now(timezone.utc).isoformat()

    # ── Guard: this route is execute-only for an existing owned project ───────
    # Missing project -> 404, non-owner -> 403.
    existing = await firestore_db.get_project_for_user(pid, uid)

    # Enforce the same idempotent credit policy used by approve-script.
    await firestore_db.deduct_credits(uid=uid, project_id=pid, amount=100)

    # ── Write initial Firestore record ────────────────────────────────────────
    initial_metadata = {
        **existing,
        "project_id":   pid,
        "uid":          uid,
        "created_at":   existing.get("created_at", queued_at),
        "queued_at":    queued_at,
        "status":       "queued",
        "platforms":    [p.value for p in request.target_platforms],
        "video_urls":   {},
        "user_email":   request.user_email,
        "series_id":    request.series_id,
    }
    try:
        await firestore_db.save_project(pid, initial_metadata)
    except Exception as e:
        logger.warning("Failed to write initial Firestore record for %s: %s", pid, e)

    # ── ASYNC MODE: enqueue Cloud Task and return 202 ─────────────────────────
    if settings.worker_url:
        try:
            from services.infra import task_queue
            task_payload = json.loads(request.model_dump_json())
            await task_queue.enqueue_video_generation(
                project_id=project_id,
                request_payload=task_payload,
            )
        except Exception as e:
            # Mark as failed and propagate — task could not be enqueued
            logger.exception("Failed to enqueue Cloud Task for project %s", project_id)
            try:
                await firestore_db.save_project(pid, {
                    **initial_metadata,
                    "status": "failed",
                    "error": f"Failed to enqueue generation job: {e}",
                })
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to queue generation job: {e}")

        poll_url = f"/api/v1/projects/{pid}/status"
        logger.info("Project %s queued → Cloud Task dispatched. Poll: %s", pid, poll_url)
        return JSONResponse(
            status_code=202,
            content={
                "project_id": pid,
                "status":     "queued",
                "poll_url":   poll_url,
                "message":    "Video generation queued. Poll poll_url for status updates.",
            },
        )

    # ── SYNC MODE: run in-process (local dev / no Cloud Tasks) ───────────────
    logger.info("WORKER_URL not set — running pipeline synchronously for project %s", pid)

    stages: list[PipelineStageStatus] = []
    import base64, os, tempfile
    from models.schemas import (ArtStyle, MusicPreset, SeriesConfig, VideoFormat, VideoDurationRange)
    from routers.projects.catalog import DURATION_MAP
    from services.storage import gcs
    from services.pipeline_runner import run_pipeline_stages

    try:
        await firestore_db.save_project(pid, {**initial_metadata, "status": "in_progress",
                                               "started_at": queued_at})

        series = None
        if request.series_id:
            try:
                config_data = await gcs.load_json(f"series/{request.series_id}/config.json")
                series = SeriesConfig(**config_data)
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")
        elif request.voice_id or request.art_style_override or request.music_preset_override:
            art_val = request.art_style_override or "realism"
            if art_val not in {e.value for e in ArtStyle}: art_val = "realism"
            music_val = request.music_preset_override or "none"
            if music_val not in {e.value for e in MusicPreset}: music_val = "none"
            series = SeriesConfig(
                series_name="Custom", video_format=VideoFormat.storytelling,
                voice_id=request.voice_id or "21m00Tcm4TlvDq8ikWAM",
                background_music=MusicPreset(music_val), art_style=ArtStyle(art_val),
                caption_style=request.caption_style, video_duration=VideoDurationRange.medium,
            )

        video_duration = (
            DURATION_MAP.get(series.video_duration.value, request.video_duration)
            if series else request.video_duration
        )

        user_ref_path = None
        if request.user_reference_image_b64 and request.user_character_role:
            try:
                img_bytes = base64.b64decode(request.user_reference_image_b64)
                ref_fd, user_ref_path = tempfile.mkstemp(suffix=".png", prefix="voicevid_userref_")
                with os.fdopen(ref_fd, "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                logger.warning("Failed to decode user_reference_image_b64: %s — ignoring", e)

        work_dir = tempfile.mkdtemp(prefix=f"voicevid_gv_{project_id}_")
        pipeline_stages, video_urls, script, thumbnail_url, visual_qa_report = await run_pipeline_stages(
            project_id=project_id,
            transcript=request.script.voiceover_full_script,
            series=series, series_id=request.series_id,
            target_platforms=request.target_platforms, style="modern_energetic",
            video_duration=video_duration, caption_style_override=request.caption_style.value,
            brand_voice=None, cta_preference=None, work_dir=work_dir,
            pre_generated_script=request.script, user_reference_path=user_ref_path,
            user_character_role=request.user_character_role.value if request.user_character_role else None,
        )
        stages.extend(pipeline_stages)

        completed_at = datetime.now(timezone.utc).isoformat()
        await firestore_db.save_project(pid, {
            **initial_metadata,
            "status":               "completed",
            "completed_at":         completed_at,
            "series_name":          series.series_name if series else None,
            "hook":                 script.hook.text if script else None,
            "scenes_count":         len(script.scenes) if script else 0,
            "video_urls":           video_urls,
            "voiceover_full_script": script.voiceover_full_script if script else None,
            "caption_style":        request.caption_style.value,
            "background_music":     series.background_music.value if series else "none",
            "video_duration":       video_duration,
            "thumbnail_url":        thumbnail_url,
            "stages":               [s.model_dump() for s in pipeline_stages],
        })

        # Email notification (sync mode)
        if request.user_email and script and script.hook:
            try:
                from services.integrations import email_notifier
                await email_notifier.send_video_ready(
                    to_email=request.user_email, project_id=pid,
                    video_urls=video_urls, thumbnail_url=thumbnail_url,
                )
            except Exception: pass

        # Feedback store
        if script and script.hook:
            try:
                from services.storage import feedback_store
                await feedback_store.record_project_outcome(
                    project_id=pid, hook_text=script.hook.text,
                    niche=series.niche if series and series.niche else "default",
                    art_style=series.art_style.value if series else "realism",
                    quality_score=float(script.metadata.get("agent_quality_score", 0)),
                    platforms=[p.value for p in request.target_platforms],
                    scenes_count=len(script.scenes),
                )
            except Exception: pass

        if user_ref_path:
            try: os.unlink(user_ref_path)
            except OSError: pass

        return PipelineResponse(
            project_id=project_id, status="completed", stages=stages,
            video_urls=video_urls, script=script, thumbnail_url=thumbnail_url,
            visual_qa_report=visual_qa_report or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Sync generate-video failed for project %s", project_id)
        for stage in stages:
            if stage.status == "running":
                stage.status = "failed"
                stage.detail = str(e)
        try:
            await firestore_db.save_project(pid, {
                **initial_metadata, "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(), "error": str(e),
            })
        except Exception: pass
        return PipelineResponse(project_id=project_id, status="failed", stages=stages, error=str(e))
