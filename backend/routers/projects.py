"""Project management endpoints — powers the frontend dashboard.

GET    /api/v1/projects              — list all projects (newest first)
GET    /api/v1/projects/{id}         — get a single project's metadata + video URLs
GET    /api/v1/projects/{id}/status  — lightweight job status for async polling
GET    /api/v1/projects/{id}/stream  — 302 redirect to a signed GCS video URL
GET    /api/v1/projects/{id}/thumbnail — 302 redirect to a JPEG thumbnail
DELETE /api/v1/projects/{id}         — remove a project from the dashboard
"""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from config import get_settings
from models.schemas import JobStatusResponse, ProjectListResponse, ProjectMetadata, ScriptEditRequest
from services.storage import firestore_db, gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects")
async def list_projects():
    """List all projects for the Projects tab, newest first.

    Returns ALL projects regardless of status (queued, generating_script,
    script_ready, generating_video, completed, failed).
    """
    try:
        items = await firestore_db.list_projects(limit=100)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

    return {"projects": items, "total": len(items)}


@router.get("/projects/{project_id}", response_model=ProjectMetadata)
async def get_project(project_id: UUID):
    """Get metadata and video URLs for a single project."""
    data = await firestore_db.get_project(str(project_id))
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found. Run the pipeline first.",
        )
    try:
        return ProjectMetadata(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Malformed project metadata: {e}")


@router.get("/projects/{project_id}/status", response_model=JobStatusResponse)
async def get_project_status(project_id: UUID):
    """Lightweight job status endpoint for async polling during video generation.

    Returns current status, active pipeline stage, % progress, and video URLs once done.
    Poll this endpoint every 5–10 seconds until status is "completed" or "failed".
    """
    data = await firestore_db.get_project(str(project_id))
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )

    # Reconstruct stages list from stored data (stored as list of dicts)
    stages_raw = data.get("stages", [])
    from models.schemas import PipelineStageStatus
    stages = []
    for s in stages_raw:
        try:
            stages.append(PipelineStageStatus(**s))
        except Exception:
            pass

    return JobStatusResponse(
        project_id=str(project_id),
        status=data.get("status", "unknown"),
        current_stage=data.get("current_stage"),
        progress_pct=data.get("progress_pct"),
        stages=stages,
        queued_at=data.get("queued_at"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        video_urls=data.get("video_urls", {}),
        thumbnail_url=data.get("thumbnail_url"),
        error=data.get("error"),
    )


@router.get("/projects/{project_id}/stream/{platform}")
async def stream_project_video(project_id: UUID, platform: str):
    """Redirect to the public GCS video URL (bucket is publicly readable).

    platform: instagram_reels | tiktok | master
    """
    from fastapi.responses import RedirectResponse
    settings = get_settings()
    gcs_key = (
        f"projects/{project_id}/master/composed.mp4"
        if platform == "master"
        else f"projects/{project_id}/{platform}/final.mp4"
    )
    public_url = f"https://storage.googleapis.com/{settings.gcs_bucket}/{gcs_key}"
    return RedirectResponse(url=public_url, status_code=302)


def _gcs_key_from_url(url: str) -> str | None:
    """Extract GCS key from a public GCS URL, or return None if not a GCS URL."""
    settings = get_settings()
    if not settings.gcs_bucket:
        return None
    prefix = f"https://storage.googleapis.com/{settings.gcs_bucket}/"
    return url[len(prefix):] if url.startswith(prefix) else None



@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: UUID, platform: str = "instagram_reels"):
    """Redirect to the public GCS thumbnail URL (bucket is publicly readable).

    Priority:
      1. Pre-generated thumbnail URL stored in project metadata → redirect.
      2. Cached thumbnail.jpg in GCS → redirect.
      3. 404 (lazy ffmpeg extraction removed; thumbnails are generated during pipeline).
    """
    from fastapi.responses import RedirectResponse
    settings = get_settings()
    base = f"https://storage.googleapis.com/{settings.gcs_bucket}"
    thumb_key = f"projects/{project_id}/thumbnail.jpg"

    # Priority 1: thumbnail_url in Firestore metadata
    data = await firestore_db.get_project(str(project_id))
    if data and data.get("thumbnail_url"):
        url = data["thumbnail_url"]
        # If already a public GCS URL return it directly; otherwise build one from the key
        key = _gcs_key_from_url(url)
        return RedirectResponse(url=f"{base}/{key}" if key else url, status_code=302)

    # Priority 2: cached thumbnail.jpg
    if await gcs.key_exists(thumb_key):
        return RedirectResponse(url=f"{base}/{thumb_key}", status_code=302)

    raise HTTPException(status_code=404, detail="Thumbnail not available")


@router.put("/projects/{project_id}/script")
async def update_project_script(project_id: UUID, req: ScriptEditRequest):
    """Save user edits to a generated script.

    Only allowed when status == 'script_ready'.
    """
    doc = await firestore_db.get_project(str(project_id))
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if doc.get("status") != "script_ready":
        raise HTTPException(status_code=409, detail="Script can only be edited when status is script_ready")

    updated = {
        **doc,
        "script": req.script,
        "hook": req.script.get("hook", {}).get("text", ""),
        "voiceover_full_script": req.script.get("voiceover_full_script", ""),
        "scenes_count": len(req.script.get("scenes", [])),
    }
    try:
        await firestore_db.save_project(str(project_id), updated)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save script edits: {e}")

    return {"status": "ok"}


@router.post("/projects/{project_id}/approve-script", status_code=202)
async def approve_script(project_id: UUID):
    """Approve the generated script and kick off video generation.

    Reconstructs GenerateVideoRequest from stored script + pipeline_config,
    then enqueues the existing video generation Cloud Task.
    Only allowed when status == 'script_ready'.
    """
    doc = await firestore_db.get_project(str(project_id))
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if doc.get("status") != "script_ready":
        raise HTTPException(status_code=409, detail="Project must be in script_ready status to approve")

    cfg = doc.get("pipeline_config", {})
    script_data = doc.get("script")
    if not script_data:
        raise HTTPException(status_code=422, detail="No script found in project — regenerate first")

    # Reconstruct GenerateVideoRequest from stored data
    from models.schemas import GenerateVideoRequest, ScriptGenerationResponse, Platform, CaptionStyleEnum
    try:
        script = ScriptGenerationResponse(**script_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Stored script is malformed: {e}")

    try:
        gen_request = GenerateVideoRequest(
            script=script,
            target_platforms=[Platform(p) for p in cfg.get("target_platforms", ["instagram_reels"])],
            voice_id=cfg.get("voice_id", "Aoede"),
            art_style_override=cfg.get("art_style_override"),
            music_preset_override=cfg.get("music_preset_override"),
            caption_style=cfg.get("caption_style", "bold_stroke"),
            video_duration=cfg.get("video_duration", 30),
            user_reference_image_b64=cfg.get("user_reference_image_b64"),
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not build video request: {e}")

    # Update Firestore status to queued
    now = datetime.now(timezone.utc).isoformat()
    await firestore_db.save_project(str(project_id), {
        **doc,
        "status": "queued",
        "current_stage": "Queued for video generation",
        "progress_pct": 0,
        "queued_at": now,
    })

    # Enqueue video generation Cloud Task
    from services.infra import task_queue
    task_payload = json.loads(gen_request.model_dump_json())
    try:
        await task_queue.enqueue_video_generation(
            project_id=project_id,
            request_payload=task_payload,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue video generation: {e}")

    return JSONResponse(status_code=202, content={
        "project_id": str(project_id),
        "status": "queued",
        "poll_url": f"/api/v1/projects/{project_id}/status",
    })


@router.put("/projects/{project_id}/timeline")
async def save_project_timeline(project_id: UUID, body: dict):
    """Persist a user-edited Twick timeline JSON back to Firestore.

    Called by the frontend TwickStudio exportVideo callback after the user
    makes edits in the editor (rearranges clips, adjusts captions, etc.).
    """
    doc = await firestore_db.get_project(str(project_id))
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    try:
        await firestore_db.save_project(str(project_id), {**doc, "project_json": body})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save timeline: {e}")
    return {"status": "ok"}


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID):
    """Remove a project's metadata from the dashboard.

    Only deletes the metadata record — video files in GCS are retained.
    """
    existing = await firestore_db.get_project(str(project_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        await firestore_db.delete_project(str(project_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")
