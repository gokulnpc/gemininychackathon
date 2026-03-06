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
from fastapi.responses import FileResponse, Response as FastAPIResponse
from starlette.background import BackgroundTask

from config import get_settings
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
        if data.get("status") != "completed" or not data.get("video_urls"):
            continue
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
    """Proxy video bytes from GCS to the client (supports Range requests for seeking).

    platform: instagram_reels | tiktok | master
    """
    gcs_key = (
        f"projects/{project_id}/master/composed.mp4"
        if platform == "master"
        else f"projects/{project_id}/{platform}/final.mp4"
    )

    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        await gcs.download_file(gcs_key, tmp)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Video not found: {e}")

    def _cleanup():
        try:
            os.unlink(tmp)
        except OSError:
            pass

    return FileResponse(tmp, media_type="video/mp4", background=BackgroundTask(_cleanup))


def _gcs_key_from_url(url: str) -> str | None:
    """Extract GCS key from a public GCS URL, or return None if not a GCS URL."""
    settings = get_settings()
    if not settings.gcs_bucket:
        return None
    prefix = f"https://storage.googleapis.com/{settings.gcs_bucket}/"
    return url[len(prefix):] if url.startswith(prefix) else None


async def _download_gcs_key_to_bytes(gcs_key: str, suffix: str = ".jpg") -> bytes | None:
    """Download a GCS key to a temp file, read bytes, clean up. Returns None on failure."""
    tmp = tempfile.mktemp(suffix=suffix)
    try:
        await gcs.download_file(gcs_key, tmp)
        with open(tmp, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: UUID, platform: str = "instagram_reels"):
    """Proxy JPEG thumbnail bytes from GCS to the client.

    Priority:
      1. Pre-generated thumbnail URL stored in project metadata → extract GCS key → proxy bytes.
      2. Cached thumbnail.jpg in GCS → proxy bytes.
      3. Lazy: download video → extract frame at t=1s via ffmpeg → cache → proxy bytes.
    """
    thumb_key = f"projects/{project_id}/thumbnail.jpg"

    # Priority 1: thumbnail_url in Firestore metadata
    data = await firestore_db.get_project(str(project_id))
    if data and data.get("thumbnail_url"):
        key = _gcs_key_from_url(data["thumbnail_url"])
        if key:
            content = await _download_gcs_key_to_bytes(key)
            if content:
                return FastAPIResponse(content=content, media_type="image/jpeg")

    # Priority 2: cached thumbnail.jpg
    if await gcs.key_exists(thumb_key):
        content = await _download_gcs_key_to_bytes(thumb_key)
        if content:
            return FastAPIResponse(content=content, media_type="image/jpeg")

    # Priority 3: lazy-extract from video
    video_key = (
        f"projects/{project_id}/master/composed.mp4"
        if platform == "master"
        else f"projects/{project_id}/{platform}/final.mp4"
    )
    tmp_video = tempfile.mktemp(suffix=".mp4")
    tmp_thumb = tempfile.mktemp(suffix=".jpg")
    try:
        await gcs.download_file(video_key, tmp_video)
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-ss", "1", "-i", tmp_video, "-vframes", "1", "-vf", "scale=400:-2", "-q:v", "3", tmp_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        with open(tmp_thumb, "rb") as f:
            content = f.read()
        # Cache to GCS (non-fatal if it fails)
        try:
            await gcs.upload_file(tmp_thumb, thumb_key, content_type="image/jpeg")
        except Exception:
            pass
        return FastAPIResponse(content=content, media_type="image/jpeg")
    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", project_id, e)
        raise HTTPException(status_code=404, detail=f"Thumbnail unavailable: {e}")
    finally:
        for p in [tmp_video, tmp_thumb]:
            try:
                os.unlink(p)
            except OSError:
                pass


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
