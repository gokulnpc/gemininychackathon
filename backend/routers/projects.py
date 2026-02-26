"""Project management endpoints — powers the frontend dashboard.

GET  /api/v1/projects              — list all projects (newest first)
GET  /api/v1/projects/{id}         — get a single project's metadata + video URLs
DELETE /api/v1/projects/{id}       — remove a project from the dashboard
"""
import asyncio
import logging
import os
import subprocess
import tempfile
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from config import get_settings
from models.schemas import ProjectListResponse, ProjectMetadata
from services import s3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["projects"])


async def _load_project_metadata(project_id: str) -> ProjectMetadata | None:
    """Load a single project's metadata.json from S3. Returns None on miss."""
    try:
        data = await s3.load_json(f"projects/{project_id}/metadata.json")
        return ProjectMetadata(**data)
    except Exception:
        return None


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects():
    """List all generated projects for the dashboard, newest first.

    Scans S3 for projects/{id}/metadata.json files saved by the pipeline.
    Loads them concurrently and returns a sorted list.
    """
    try:
        all_keys = await s3.list_keys("projects/")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

    # Collect unique project IDs from keys like projects/{id}/metadata.json
    project_ids = {
        key.split("/")[1]
        for key in all_keys
        if key.endswith("/metadata.json") and len(key.split("/")) == 3
    }

    if not project_ids:
        return ProjectListResponse(projects=[], total=0)

    # Load all metadata files concurrently
    results = await asyncio.gather(
        *[_load_project_metadata(pid) for pid in project_ids],
        return_exceptions=False,
    )

    projects = [p for p in results if p is not None]

    # Sort newest first
    projects.sort(key=lambda p: p.created_at, reverse=True)

    return ProjectListResponse(projects=projects, total=len(projects))


@router.get("/projects/{project_id}", response_model=ProjectMetadata)
async def get_project(project_id: UUID):
    """Get metadata and video URLs for a single project.

    Used by the dashboard to show project details and get publish-ready URLs.
    """
    project = await _load_project_metadata(str(project_id))
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found. Run the pipeline first.",
        )
    return project


@router.get("/projects/{project_id}/stream/{platform}")
async def stream_project_video(project_id: UUID, platform: str):
    """Return a short-lived presigned URL (302 redirect) for playing a project video.

    platform: instagram_reels | tiktok | master
    The browser follows the redirect and streams the video directly from S3.
    """
    s3_key = f"projects/{project_id}/{platform}/final.mp4"
    if platform == "master":
        s3_key = f"projects/{project_id}/master/composed.mp4"

    try:
        presigned = await s3.generate_presigned_url(s3_key, expires_in=3600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate stream URL: {e}")

    return RedirectResponse(url=presigned, status_code=302)


def _s3_key_exists(key: str) -> bool:
    """Return True if an S3 object exists (synchronous)."""
    settings = get_settings()
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    try:
        client.head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError:
        return False


def _extract_and_upload_thumbnail(video_presigned_url: str, thumb_s3_key: str) -> str:
    """Run ffmpeg to grab frame at t=1s, upload JPEG to S3, return presigned URL."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", "1",
                "-i", video_presigned_url,
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

        settings = get_settings()
        client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        client.upload_file(
            tmp_path,
            settings.s3_bucket,
            thumb_s3_key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )
        presigned = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": thumb_s3_key},
            ExpiresIn=3600,
        )
        return presigned
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: UUID, platform: str = "instagram_reels"):
    """Return a JPEG thumbnail (302 → presigned S3 URL) for a project video.

    On first call: extracts frame at t=1s via ffmpeg and caches it in S3.
    Subsequent calls: immediate redirect to cached thumbnail.
    """
    thumb_key = f"projects/{project_id}/thumbnail.jpg"

    # ── Serve cached thumbnail if available ───────────────────────────────────
    exists = await asyncio.to_thread(_s3_key_exists, thumb_key)
    if exists:
        presigned = await s3.generate_presigned_url(thumb_key, expires_in=3600)
        return RedirectResponse(url=presigned, status_code=302)

    # ── Generate thumbnail from video ─────────────────────────────────────────
    video_key = f"projects/{project_id}/{platform}/final.mp4"
    if platform == "master":
        video_key = f"projects/{project_id}/master/composed.mp4"

    try:
        video_presigned = await s3.generate_presigned_url(video_key, expires_in=600)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Video not found: {e}")

    try:
        presigned = await asyncio.to_thread(
            _extract_and_upload_thumbnail, video_presigned, thumb_key
        )
    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {e}")

    return RedirectResponse(url=presigned, status_code=302)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID):
    """Remove a project's metadata from the dashboard.

    Note: this only deletes the metadata.json index entry — the video files
    in S3 are retained. To fully purge, delete the S3 prefix manually.
    """
    existing = await _load_project_metadata(str(project_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        from config import get_settings
        import boto3

        settings = get_settings()
        client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        client.delete_object(
            Bucket=settings.s3_bucket,
            Key=f"projects/{project_id}/metadata.json",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")
