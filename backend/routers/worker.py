"""Internal worker endpoints — called by Cloud Tasks, not by end users.

POST /internal/worker/generate-video

Receives a Cloud Tasks HTTP callback containing the GenerateVideoRequest payload
and runs the full video generation pipeline via worker_runner.run_generation().

Security:
  - Validates the X-CloudTasks-QueueName header to reject spoofed requests
  - On Cloud Run, the OIDC token is verified automatically by the platform
  - Route is prefixed /internal/ — not included in the public OpenAPI docs

Cloud Tasks retry behaviour:
  - Returns 200 on success (task deleted from queue)
  - Returns 500 on failure (Cloud Tasks will retry up to MAX_ATTEMPTS)
  - Returns 400 for malformed payloads (no retry — bad tasks)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from config import get_settings
from models.schemas import GenerateVideoRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["worker"], include_in_schema=False)


@router.post("/worker/generate-video", status_code=200)
async def worker_generate_video(
    request: Request,
    x_cloudtasks_queuename: str | None = Header(default=None),
) -> dict:
    """Cloud Tasks callback: run the full video generation pipeline.

    The task body must be a JSON object containing:
      - project_id: str (UUID)
      - All fields of GenerateVideoRequest

    Returns {"status": "completed"} on success.
    Raises 500 on pipeline failure (triggers Cloud Tasks retry).
    """
    settings = get_settings()

    # ── Security: verify this came from our Cloud Tasks queue ─────────────────
    # On Cloud Run, OIDC is already verified at the platform level.
    # The header check provides a secondary guard against direct HTTP calls.
    if settings.cloud_tasks_queue and x_cloudtasks_queuename:
        if x_cloudtasks_queuename != settings.cloud_tasks_queue:
            logger.warning(
                "Worker received request from unexpected queue: %s", x_cloudtasks_queuename
            )
            raise HTTPException(status_code=403, detail="Forbidden: unexpected queue name")

    # ── Parse payload ─────────────────────────────────────────────────────────
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

    # ── Execute pipeline ───────────────────────────────────────────────────────
    from services import worker_runner
    try:
        await worker_runner.run_generation(project_id=project_id, request=gen_request)
    except Exception as exc:
        logger.exception("Worker pipeline failed for project %s", project_id)
        # Return 500 so Cloud Tasks retries the task
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}")

    return {"status": "completed", "project_id": str(project_id)}
