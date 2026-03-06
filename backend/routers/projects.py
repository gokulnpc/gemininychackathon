"""Project management endpoints — powers the frontend dashboard.

GET    /api/v1/projects              — list all projects (newest first)
GET    /api/v1/projects/{id}         — get a single project's metadata + video URLs
GET    /api/v1/projects/{id}/status  — lightweight job status for async polling
GET    /api/v1/projects/{id}/stream  — 302 redirect to a signed GCS video URL
GET    /api/v1/projects/{id}/thumbnail — 302 redirect to a JPEG thumbnail
DELETE /api/v1/projects/{id}         — remove a project from the dashboard
"""
import asyncio
import logging
import os
import subprocess
import tempfile
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from models.schemas import JobStatusResponse, ProjectListResponse, ProjectMetadata
from services import firestore_db, gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects():
    """List all generated projects for the dashboard, newest first."""
    try:
        items = await firestore_db.list_projects(limit=100)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

    projects = []
    for data in items:
        try:
            projects.append(ProjectMetadata(**data))
        except Exception:
            pass

    return ProjectListResponse(projects=projects, total=len(projects))


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
    """Return a short-lived signed URL (302 redirect) for playing a project video.

    platform: instagram_reels | tiktok | master
    """
    gcs_key = (
        f"projects/{project_id}/master/composed.mp4"
        if platform == "master"
        else f"projects/{project_id}/{platform}/final.mp4"
    )

    try:
        signed = await gcs.generate_presigned_url(gcs_key, expires_in=3600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate stream URL: {e}")

    return RedirectResponse(url=signed, status_code=302)


async def _extract_and_upload_thumbnail(video_url: str, thumb_key: str) -> str:
    """Run ffmpeg to grab frame at t=1s, upload JPEG to GCS, return signed URL."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name

    try:
        await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg", "-y",
                "-ss", "1",
                "-i", video_url,
                "-vframes", "1",
                "-vf", "scale=400:-2",
                "-q:v", "3",
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        await gcs.upload_file(tmp_path, thumb_key, content_type="image/jpeg")
        return await gcs.generate_presigned_url(thumb_key, expires_in=3600)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: UUID, platform: str = "instagram_reels"):
    """Return a JPEG thumbnail (302 → URL) for a project video.

    Priority:
      1. Pre-generated Gemini thumbnail stored in project metadata (thumbnail_url).
      2. Cached thumbnail.jpg in GCS (from previous lazy extraction or pipeline upload).
      3. Lazy: extract frame at t=1s via ffmpeg and cache it in GCS.
    """
    # Fast-path: use pre-generated thumbnail URL stored in Firestore metadata
    data = await firestore_db.get_project(str(project_id))
    if data and data.get("thumbnail_url"):
        return RedirectResponse(url=data["thumbnail_url"], status_code=302)

    thumb_key = f"projects/{project_id}/thumbnail.jpg"

    if await gcs.key_exists(thumb_key):
        signed = await gcs.generate_presigned_url(thumb_key, expires_in=3600)
        return RedirectResponse(url=signed, status_code=302)

    video_key = (
        f"projects/{project_id}/master/composed.mp4"
        if platform == "master"
        else f"projects/{project_id}/{platform}/final.mp4"
    )

    try:
        video_url = await gcs.generate_presigned_url(video_key, expires_in=600)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Video not found: {e}")

    try:
        signed = await _extract_and_upload_thumbnail(video_url, thumb_key)
    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {e}")

    return RedirectResponse(url=signed, status_code=302)


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
