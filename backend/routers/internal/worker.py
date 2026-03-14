"""Internal worker endpoints — called by Cloud Tasks, not by end users.

POST /internal/worker/generate-video
POST /internal/worker/generate-script
POST /internal/worker/generate-export

Security:
  - Validates the X-CloudTasks-QueueName header to reject spoofed requests
  - On Cloud Run, the OIDC token is verified automatically by the platform
  - Route is prefixed /internal/ — not included in the public OpenAPI docs

Cloud Tasks retry behaviour:
  - Returns 200 on success (task deleted from queue)
  - Returns 500 on failure (Cloud Tasks will retry up to MAX_ATTEMPTS)
  - Returns 400 for malformed payloads (no retry — bad tasks)

Local dev:
  - _run_script_generation() and _run_video_generation() are called directly
    in-process via asyncio.create_task() from services/task_queue.py when
    WORKER_URL is not set.
"""

from __future__ import annotations

import copy
import logging
import os
import tempfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from config import get_settings
from models.schemas import GenerateVideoRequest
from services.infra.editor_export import (
    append_editor_export_history,
    build_editor_export_state,
    render_timeline_to_file,
    upload_rendered_export,
)
from services.storage import firestore_db, gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["worker"], include_in_schema=False)


# ── Core logic functions (reused by HTTP handlers and local in-process mode) ──


async def _run_video_generation(project_id: UUID, gen_request: GenerateVideoRequest) -> None:
    """Core video generation pipeline. Called by HTTP handler and local fallback."""
    from services.infra import worker_runner
    await worker_runner.run_generation(project_id=project_id, request=gen_request)


async def _run_script_generation(project_id: str) -> None:
    """Core script generation logic. Called by HTTP handler and local in-process fallback."""
    doc = await firestore_db.get_project(project_id)
    if doc is None:
        raise ValueError(f"Project {project_id} not found")

    project_doc = dict(doc)
    cfg = project_doc.get("pipeline_config", {})
    reddit_ctx: dict = {}

    async def _save_patch(**updates) -> None:
        nonlocal project_doc
        project_doc = {**project_doc, **updates}
        await firestore_db.save_project(project_id, project_doc)

    async def _update(stage: str, pct: int, **extra) -> None:
        await _save_patch(
            status="generating_script",
            current_stage=stage,
            progress_pct=pct,
            **extra,
        )

    try:
        attempt_count = int(project_doc.get("script_attempt_count") or 0) + 1
        await _save_patch(
            script_attempt_count=attempt_count,
            error=None,
            error_code=None,
            retryable=None,
            failure_stage=None,
            failed_at=None,
            last_error_code=None,
        )

        # ── Step 1: Resolve transcript ────────────────────────────────────────
        source = cfg.get("source", "text")

        if source == "voice":
            await _update("Transcribing audio", 5)
            audio_gcs_key = doc.get("audio_gcs_key")
            if not audio_gcs_key:
                raise ValueError("audio_gcs_key missing for voice source")
            import base64 as _b64
            import os as _os
            import tempfile as _tempfile
            audio_format = cfg.get("audio_format", "webm")
            with _tempfile.NamedTemporaryFile(delete=False, suffix=f".{audio_format}") as _tmp:
                tmp_audio_path = _tmp.name
            try:
                await gcs.download_file(audio_gcs_key, tmp_audio_path)
                with open(tmp_audio_path, "rb") as _f:
                    audio_b64 = _b64.b64encode(_f.read()).decode()
            finally:
                if _os.path.exists(tmp_audio_path):
                    _os.unlink(tmp_audio_path)
            from services.gemini import audio as gemini_audio
            result = await gemini_audio.transcribe_with_tone(
                audio_b64=audio_b64,
                audio_format=audio_format,
            )
            transcript = result["transcript"]
            detected_tone = result.get("detected_tone", "conversational")
        elif source == "text":
            transcript = cfg.get("transcript") or ""
            detected_tone = "conversational"
        elif source == "preset":
            from routers.generation.script import _PRESETS
            from models.schemas import PresetKey
            preset_value = cfg.get("preset")
            if not preset_value:
                raise ValueError("Preset source requires a preset key")
            preset_key = PresetKey(preset_value)
            preset_def = _PRESETS[preset_key]
            transcript = preset_def["topic"]
            if cfg.get("topic_hint"):
                transcript = f"{transcript}\n\nSpecific angle: {cfg['topic_hint']}"
            detected_tone = "storytelling"
            try:
                from services.integrations import reddit
                reddit_ctx = await reddit.fetch_trending(niche=preset_def["niche"], transcript=transcript)
            except Exception as reddit_err:
                logger.warning("Reddit context failed (non-fatal): %s", reddit_err)
        else:
            raise ValueError(f"Unsupported script source: {source}")

        # ── Step 2: Inject context preambles ─────────────────────────────────
        if cfg.get("plot_summary"):
            transcript = (
                f"User selected this story direction: {cfg['plot_summary']}\n\n"
                f"Content context: {transcript}"
            )
        if cfg.get("user_character_role"):
            transcript = (
                f"Character context: The user will appear as '{cfg['user_character_role']}' "
                f"in the video (they uploaded a reference photo of themselves). "
                f"Write scenes that portray this character consistently with their role.\n\n"
                f"{transcript}"
            )

        # ── Step 3: Generate script via ADK agent (with live Firestore progress) ─
        await _update("Generating script", 15)

        from services.gemini.agent import stream_script_agent
        from routers.generation.script import _TONE_TO_STYLE

        style = _TONE_TO_STYLE.get(detected_tone, "modern_energetic")
        art_style = cfg.get("art_style_override") or "realism"
        reddit_context = reddit_ctx if source == "preset" else None

        _STEP_PROGRESS = {
            "search_trending_hooks":   25,
            "analyze_brand_voice":     40,
            "optimize_for_platform":   55,
            "validate_script_quality": 70,
            "finalize_script":         85,
            "retry_script_generation": 18,
        }

        script_data = None
        async for event in stream_script_agent(
            transcript=transcript,
            target_platforms=cfg.get("target_platforms", ["instagram_reels"]),
            style=style,
            video_duration=cfg.get("video_duration", 30),
            niche=None,
            art_style=art_style,
            video_format="storytelling",
            reddit_context=reddit_context,
        ):
            if event["type"] == "agent_step":
                tool = event.get("tool", "")
                pct = _STEP_PROGRESS.get(tool, 50)
                await _update(event["message"], pct)
            elif event["type"] == "retry":
                attempt_count = int(event.get("attempt") or attempt_count)
                await _update(
                    event.get("message", "Retrying script generation"),
                    int(event.get("progress_pct") or 18),
                    script_attempt_count=attempt_count,
                    last_retry_at=datetime.now(timezone.utc).isoformat(),
                    last_error_code=event.get("error_code"),
                )
            elif event["type"] == "complete":
                script_data = event["script"]
            elif event["type"] == "error":
                from services.gemini.agent import ScriptAgentFailure

                raise ScriptAgentFailure(
                    message=event.get("message") or "Scout failed during script generation.",
                    error_code=event.get("error_code") or "unexpected_agent_error",
                    retryable=bool(event.get("retryable")),
                    debug_hint=event.get("debug_hint"),
                )

        if script_data is None:
            from services.gemini.agent import _classify_script_agent_failure

            raise _classify_script_agent_failure("Script agent completed without producing a script")

        # ── Step 4: Save script + mark script_ready ──────────────────────────
        await _save_patch(
            status="script_ready",
            current_stage="Script ready for review",
            progress_pct=100,
            script=script_data,
            hook=script_data.get("hook", {}).get("text", ""),
            scenes_count=len(script_data.get("scenes", [])),
            voiceover_full_script=script_data.get("voiceover_full_script", ""),
            error=None,
            error_code=None,
            retryable=None,
            failure_stage=None,
            failed_at=None,
            last_error_code=None,
        )
        logger.info("Script generation complete for project %s", project_id)

    except Exception as exc:
        from services.gemini.agent import _classify_script_agent_failure

        failure = _classify_script_agent_failure(exc)
        logger.exception("Script generation failed for project %s", project_id)
        await _save_patch(
            status="failed",
            current_stage="Script generation failed",
            progress_pct=None,
            error=str(failure),
            error_code=failure.error_code,
            retryable=failure.retryable,
            failed_at=datetime.now(timezone.utc).isoformat(),
            failure_stage="script_generation",
            last_error_code=failure.error_code,
        )
        raise failure


async def _run_editor_export(project_id: UUID, export_id: str) -> None:
    """Render the saved canonical timeline to a separate edited MP4 export."""
    project_key = str(project_id)
    doc = await firestore_db.get_project(project_key)
    if doc is None:
        raise ValueError(f"Project {project_key} not found")

    current_export = build_editor_export_state(doc.get("editor_export"))
    if current_export.get("export_id") != export_id:
        logger.info(
            "Skipping stale editor export task for %s (task export_id=%s, current export_id=%s)",
            project_key,
            export_id,
            current_export.get("export_id"),
        )
        return

    if doc.get("status") != "completed":
        raise ValueError("Project must be completed before editor export can run")

    project_json = doc.get("project_json")
    if not isinstance(project_json, dict):
        raise ValueError("Project timeline is missing or malformed")

    started_at = datetime.now(timezone.utc).isoformat()
    await firestore_db.save_project(project_key, {
        **doc,
        "editor_export": build_editor_export_state(
            current_export,
            export_id=export_id,
            status="in_progress",
            current_stage="Rendering export",
            progress_pct=20,
            started_at=started_at,
            completed_at=None,
            download_url=None,
            thumbnail_url=None,
            error=None,
        ),
    })

    temp_output_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output_file:
            temp_output_path = output_file.name

        await render_timeline_to_file(project_json=project_json, output_path=temp_output_path)

        refreshed_doc = await firestore_db.get_project(project_key)
        if refreshed_doc is None:
            raise ValueError(f"Project {project_key} disappeared during export")

        refreshed_export = build_editor_export_state(refreshed_doc.get("editor_export"))
        if refreshed_export.get("export_id") != export_id:
            logger.info(
                "Discarding stale editor export result for %s (task export_id=%s, current export_id=%s)",
                project_key,
                export_id,
                refreshed_export.get("export_id"),
            )
            return

        await firestore_db.save_project(project_key, {
            **refreshed_doc,
            "editor_export": build_editor_export_state(
                refreshed_export,
                export_id=export_id,
                status="in_progress",
                current_stage="Uploading export",
                progress_pct=90,
                error=None,
            ),
        })

        download_url = await upload_rendered_export(
            local_path=temp_output_path,
            project_id=project_key,
            export_id=export_id,
        )

        final_doc = await firestore_db.get_project(project_key)
        if final_doc is None:
            raise ValueError(f"Project {project_key} disappeared after export upload")

        final_export = build_editor_export_state(final_doc.get("editor_export"))
        if final_export.get("export_id") != export_id:
            logger.info(
                "Skipping stale editor export completion write for %s (task export_id=%s, current export_id=%s)",
                project_key,
                export_id,
                final_export.get("export_id"),
            )
            return

        completed_at = datetime.now(timezone.utc).isoformat()
        await firestore_db.save_project(project_key, {
            **final_doc,
            "editor_export": build_editor_export_state(
                final_export,
                export_id=export_id,
                status="completed",
                current_stage="Export ready",
                progress_pct=100,
                completed_at=completed_at,
                download_url=download_url,
                error=None,
            ),
            "editor_export_history": append_editor_export_history(
                final_doc.get("editor_export_history"),
                export_id=export_id,
                completed_at=completed_at,
                download_url=download_url,
                thumbnail_url=final_export.get("thumbnail_url"),
                project_json_snapshot=copy.deepcopy(project_json),
            ),
        })
    except Exception as exc:
        logger.exception("Editor export failed for project %s", project_key)

        failure_doc = await firestore_db.get_project(project_key)
        if failure_doc is not None:
            failure_export = build_editor_export_state(failure_doc.get("editor_export"))
            if failure_export.get("export_id") == export_id:
                await firestore_db.save_project(project_key, {
                    **failure_doc,
                    "editor_export": build_editor_export_state(
                        failure_export,
                        export_id=export_id,
                        status="failed",
                        current_stage="Export failed",
                        progress_pct=None,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        error=str(exc),
                    ),
                })
        raise
    finally:
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                os.unlink(temp_output_path)
            except OSError:
                logger.warning("Failed to remove temporary editor export file %s", temp_output_path)


# ── HTTP handlers (thin wrappers used by Cloud Tasks) ─────────────────────────


@router.post("/worker/generate-video", status_code=200)
async def worker_generate_video(
    request: Request,
    x_cloudtasks_queuename: str | None = Header(default=None),
) -> dict:
    """Cloud Tasks callback: run the full video generation pipeline."""
    settings = get_settings()

    if settings.cloud_tasks_queue and x_cloudtasks_queuename:
        if x_cloudtasks_queuename != settings.cloud_tasks_queue:
            logger.warning(
                "Worker received request from unexpected queue: %s", x_cloudtasks_queuename
            )
            raise HTTPException(status_code=403, detail="Forbidden: unexpected queue name")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        project_id = UUID(body.pop("project_id"))
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid or missing project_id: {e}")

    try:
        gen_request = GenerateVideoRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid GenerateVideoRequest payload: {e}")

    try:
        await _run_video_generation(project_id=project_id, gen_request=gen_request)
    except Exception as exc:
        logger.exception("Worker pipeline failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}")

    return {"status": "completed", "project_id": str(project_id)}


@router.post("/worker/generate-script", status_code=200)
async def worker_generate_script(
    request: Request,
    x_cloudtasks_queuename: str | None = Header(default=None),
) -> dict:
    """Cloud Tasks callback: generate script only, then set status=script_ready."""
    settings = get_settings()

    if settings.cloud_tasks_queue and x_cloudtasks_queuename:
        if x_cloudtasks_queuename != settings.cloud_tasks_queue:
            logger.warning("Script worker received request from unexpected queue: %s", x_cloudtasks_queuename)
            raise HTTPException(status_code=403, detail="Forbidden: unexpected queue name")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="Missing project_id")

    try:
        await _run_script_generation(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Script generation failed: {exc}")

    return {"status": "script_ready", "project_id": project_id}


@router.post("/worker/generate-export", status_code=200)
async def worker_generate_export(
    request: Request,
    x_cloudtasks_queuename: str | None = Header(default=None),
) -> dict:
    """Cloud Tasks callback: render a queued editor export."""
    settings = get_settings()

    if settings.cloud_tasks_queue and x_cloudtasks_queuename:
        if x_cloudtasks_queuename != settings.cloud_tasks_queue:
            logger.warning("Export worker received request from unexpected queue: %s", x_cloudtasks_queuename)
            raise HTTPException(status_code=403, detail="Forbidden: unexpected queue name")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        project_id = UUID(body["project_id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid or missing project_id: {exc}")

    export_id = body.get("export_id")
    if not export_id:
        raise HTTPException(status_code=400, detail="Missing export_id")

    try:
        await _run_editor_export(project_id=project_id, export_id=export_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Worker export failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Editor export failed: {exc}")

    return {"status": "completed", "project_id": str(project_id), "export_id": export_id}
