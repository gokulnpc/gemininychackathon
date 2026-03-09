"""Recompose router — POST /api/v1/projects/{project_id}/recompose

Regenerates a project's caption style and/or background music without
re-running TTS, image generation, or FFmpeg animation.

Requirements:
  - The project must be in "completed" status.
  - generate-video must have been run at least once (persists with_audio.mp4).
  - Projects created before recompose support was added return HTTP 422 with
    an actionable error message.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.schemas import RecomposeRequest, RecomposeResponse
from services.storage import firestore_db
from services.infra.recompose import recompose_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["video"])


@router.post("/projects/{project_id}/recompose", response_model=RecomposeResponse)
async def recompose_project_video(project_id: UUID, request: RecomposeRequest):
    """Recompose a completed project with a new caption style and/or background music.

    Skips TTS, Gemini image generation, and FFmpeg animation — starts directly
    from the preserved `with_audio.mp4` (scenes + voiceover, no captions, no music).

    On success, the project's master and platform video files in storage are
    overwritten with the recomposed versions, and metadata.json is updated.

    **Error cases:**
    - 404 — project not found
    - 409 — project not in "completed" state
    - 422 — project predates recompose support (re-run generate-video first)
    """
    # ── Load project metadata ─────────────────────────────────────────────────

    metadata = await firestore_db.get_project(str(project_id))
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )

    if metadata.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project '{project_id}' has status '{metadata.get('status')}'. "
                "Only completed projects can be recomposed."
            ),
        )

    voiceover_full_script: str | None = metadata.get("voiceover_full_script")
    if not voiceover_full_script:
        raise HTTPException(
            status_code=422,
            detail=(
                "voiceover_full_script is missing from project metadata. "
                "This project was created before recompose support was added. "
                "Re-run generate-video once to enable recompose."
            ),
        )

    video_duration: int = int(metadata.get("video_duration") or 30)
    original_platforms: list[str] = metadata.get("platforms", ["instagram_reels"])

    # Default target_platforms to the original platforms if not overridden
    target_platforms = request.target_platforms
    if not target_platforms:
        from models.schemas import Platform
        target_platforms = [Platform(p) for p in original_platforms if p in {e.value for e in Platform}]

    # ── Run recompose ─────────────────────────────────────────────────────────

    try:
        stages, video_urls = await recompose_video(
            project_id=project_id,
            voiceover_full_script=voiceover_full_script,
            video_duration=video_duration,
            caption_style=request.caption_style.value,
            background_music=request.background_music.value,
            target_platforms=target_platforms,
            music_volume=request.music_volume,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Recompose failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Recompose failed: {e}")

    # ── Update metadata with new style settings ───────────────────────────────

    metadata["caption_style"]    = request.caption_style.value
    metadata["background_music"] = request.background_music.value
    metadata["video_urls"]       = video_urls
    metadata["recomposed_at"]    = datetime.now(timezone.utc).isoformat()

    try:
        await firestore_db.save_project(str(project_id), metadata)
    except Exception:
        logger.warning("Failed to update metadata for %s after recompose", project_id)

    return RecomposeResponse(
        project_id=project_id,
        status="completed",
        stages=stages,
        video_urls=video_urls,
        caption_style=request.caption_style.value,
        background_music=request.background_music.value,
    )
