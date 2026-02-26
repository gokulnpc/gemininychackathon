import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.schemas import (
    PlatformPostResult,
    PublishRequest,
    PublishResponse,
)
from services import social_publish

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["publish"])


@router.post("/projects/{project_id}/publish", response_model=PublishResponse)
async def publish_project(project_id: UUID, request: PublishRequest):
    """Publish generated videos to social media platforms.

    Uses official platform APIs: YouTube Data API v3, Meta Graph API (Instagram),
    TikTok Content Posting API v2. Runs all platforms concurrently — partial
    success is reported if one platform fails.

    Requires that the pipeline has already been run for this project
    (videos must exist in S3 at projects/{id}/{platform}/final.mp4).
    """
    # Build social_copy dict from request or use empty defaults
    social_copy: dict[str, dict] = {}
    if request.social_copy:
        for key, copy in request.social_copy.items():
            social_copy[key] = copy.model_dump()

    platform_names = [p.value for p in request.platforms]

    results = await social_publish.publish_to_platforms(
        project_id=str(project_id),
        platforms=platform_names,
        social_copy=social_copy,
        schedule=request.schedule,
    )

    posts = [
        PlatformPostResult(
            platform=r["platform"],
            status=r["status"],
            post_url=r.get("post_url"),
            screenshot_url=r.get("screenshot_url"),
            error=r.get("error"),
        )
        for r in results
    ]

    # Determine overall status
    statuses = {p.status for p in posts}
    if all(s in ("published", "scheduled") for s in statuses):
        overall = "completed"
    elif any(s in ("published", "scheduled") for s in statuses):
        overall = "partial"
    else:
        overall = "failed"

    return PublishResponse(
        project_id=project_id,
        status=overall,
        posts=posts,
        completed_at=datetime.now(timezone.utc),
    )
