"""Project management endpoints — powers the frontend dashboard.

GET    /api/v1/projects              — list all projects (newest first)
GET    /api/v1/projects/{id}         — get a single project's metadata + video URLs
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

from models.schemas import ProjectListResponse, ProjectMetadata
from services import gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["projects"])


async def _load_project_metadata(project_id: str) -> ProjectMetadata | None:
    """Load a single project's metadata.json from GCS. Returns None on miss."""
    try:
        data = await gcs.load_json(f"projects/{project_id}/metadata.json")
        return ProjectMetadata(**data)
    except Exception:
        return None


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects():
    """List all generated projects for the dashboard, newest first.

    Scans GCS for projects/{id}/metadata.json files saved by the pipeline.
    """
    try:
        all_keys = await gcs.list_keys("projects/")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

    project_ids = {
        key.split("/")[1]
        for key in all_keys
        if key.endswith("/metadata.json") and len(key.split("/")) == 3
    }

    if not project_ids:
        return ProjectListResponse(projects=[], total=0)

    results = await asyncio.gather(
        *[_load_project_metadata(pid) for pid in project_ids],
        return_exceptions=False,
    )

    projects = [p for p in results if p is not None]
    projects.sort(key=lambda p: p.created_at, reverse=True)

    return ProjectListResponse(projects=projects, total=len(projects))


@router.get("/projects/{project_id}", response_model=ProjectMetadata)
async def get_project(project_id: UUID):
    """Get metadata and video URLs for a single project."""
    project = await _load_project_metadata(str(project_id))
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found. Run the pipeline first.",
        )
    return project


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
    """Return a JPEG thumbnail (302 → signed GCS URL) for a project video.

    On first call: extracts frame at t=1s via ffmpeg and caches it in GCS.
    Subsequent calls: immediate redirect to cached thumbnail.
    """
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

    Only deletes the metadata.json index entry — video files in GCS are retained.
    """
    existing = await _load_project_metadata(str(project_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        await gcs.delete_object(f"projects/{project_id}/metadata.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")
