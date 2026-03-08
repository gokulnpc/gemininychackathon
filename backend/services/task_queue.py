"""Cloud Tasks client — enqueue video generation jobs.

Wraps google-cloud-tasks to submit a Cloud Tasks HTTP task pointing at the
Worker Service (`POST /internal/worker/generate-video`). The task carries the
full GenerateVideoRequest payload as JSON in its body.

Falls back to synchronous in-process execution when `settings.worker_url` is
empty (local development without Cloud Tasks configured).

Queue:  video-generation  (created by deploy.sh)
Target: POST {WORKER_URL}/internal/worker/generate-video
Auth:   OIDC token — Cloud Run requires the service account to have
        roles/run.invoker on the worker service.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_TASK_TIMEOUT_SECONDS = 900    # 15 min — covers 10-min generation + overhead
_MAX_ATTEMPTS = 2              # generation is expensive; don't retry aggressively


def _tasks_available() -> bool:
    try:
        from google.cloud import tasks_v2  # noqa: F401
        return True
    except ImportError:
        return False


async def enqueue_video_generation(
    project_id: UUID,
    request_payload: dict,
) -> str:
    """Submit a video generation job to Cloud Tasks.

    Args:
        project_id:      The UUID of the project being generated.
        request_payload: Serialised GenerateVideoRequest dict (JSON-serialisable).

    Returns:
        Cloud Tasks task name (for logging/debugging) or "local" if running in-process.

    Raises:
        RuntimeError if Cloud Tasks is not available and worker_url is set.
    """
    from config import get_settings
    settings = get_settings()

    if not settings.worker_url:
        # Local dev — run in-process as a background task
        import asyncio
        from routers.worker import _run_video_generation
        from models.schemas import GenerateVideoRequest as _GVR
        gen_request = _GVR(**request_payload)
        asyncio.create_task(_run_video_generation(project_id=project_id, gen_request=gen_request))
        logger.info("Local mode — running video gen in-process for %s", project_id)
        return "local-inprocess"

    if not _tasks_available():
        # Cloud Tasks library not installed — fall back to in-process background task
        import asyncio
        from routers.worker import _run_video_generation
        from models.schemas import GenerateVideoRequest as _GVR
        gen_request = _GVR(**request_payload)
        asyncio.create_task(_run_video_generation(project_id=project_id, gen_request=gen_request))
        logger.info("Cloud Tasks unavailable — running video gen in-process for %s", project_id)
        return "local-inprocess"

    import asyncio
    from google.cloud import tasks_v2
    from google.protobuf import duration_pb2

    parent = (
        f"projects/{settings.google_cloud_project}"
        f"/locations/{settings.cloud_tasks_location}"
        f"/queues/{settings.cloud_tasks_queue}"
    )

    body = json.dumps({
        "project_id": str(project_id),
        **request_payload,
    }).encode()

    target_url = f"{settings.worker_url.rstrip('/')}/internal/worker/generate-video"

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": (
                    f"storylab-sa@{settings.google_cloud_project}.iam.gserviceaccount.com"
                ),
                "audience": settings.worker_url,
            },
        },
        "dispatch_deadline": duration_pb2.Duration(seconds=_TASK_TIMEOUT_SECONDS),
    }

    def _create():
        client = tasks_v2.CloudTasksClient()
        return client.create_task(
            request={
                "parent": parent,
                "task": task,
            }
        )

    response = await asyncio.to_thread(_create)
    logger.info("Cloud Task created: %s → %s", response.name, target_url)
    return response.name


async def enqueue_script_generation(project_id: str) -> str:
    """Submit a script-only generation job to Cloud Tasks.

    Args:
        project_id: The project ID (string UUID). Full config is loaded from Firestore by the worker.

    Returns:
        Cloud Tasks task name or "local" if running in-process.
    """
    from config import get_settings
    settings = get_settings()

    if not settings.worker_url:
        # Local dev — run in-process as a background task
        import asyncio
        from routers.worker import _run_script_generation
        asyncio.create_task(_run_script_generation(project_id))
        logger.info("Local mode — running script gen in-process for %s", project_id)
        return "local-inprocess"

    if not _tasks_available():
        # Cloud Tasks library not installed — fall back to in-process background task
        import asyncio
        from routers.worker import _run_script_generation
        asyncio.create_task(_run_script_generation(project_id))
        logger.info("Cloud Tasks unavailable — running script gen in-process for %s", project_id)
        return "local-inprocess"

    import asyncio
    from google.cloud import tasks_v2
    from google.protobuf import duration_pb2

    parent = (
        f"projects/{settings.google_cloud_project}"
        f"/locations/{settings.cloud_tasks_location}"
        f"/queues/{settings.cloud_tasks_queue}"
    )

    body = json.dumps({"project_id": project_id}).encode()
    target_url = f"{settings.worker_url.rstrip('/')}/internal/worker/generate-script"

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": (
                    f"storylab-sa@{settings.google_cloud_project}.iam.gserviceaccount.com"
                ),
                "audience": settings.worker_url,
            },
        },
        "dispatch_deadline": duration_pb2.Duration(seconds=_TASK_TIMEOUT_SECONDS),
    }

    def _create():
        client = tasks_v2.CloudTasksClient()
        return client.create_task(
            request={
                "parent": parent,
                "task": task,
            }
        )

    response = await asyncio.to_thread(_create)
    logger.info("Script-gen Cloud Task created: %s → %s", response.name, target_url)
    return response.name
