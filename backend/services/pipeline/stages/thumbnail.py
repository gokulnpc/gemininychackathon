"""Stage 4b: Thumbnail generation and upload."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from uuid import UUID

from models.schemas import PipelineStageStatus, ScriptGenerationResponse
from services.storage import gcs

logger = logging.getLogger(__name__)


async def run_thumbnail_stage(
    stages: list[PipelineStageStatus],
    script: ScriptGenerationResponse,
    char_desc: str,
    art_style: str,
    project_id: UUID,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> str | None:
    """Generate and upload a thumbnail. Returns GCS URL or None on failure."""
    if on_progress:
        try:
            await on_progress("thumbnail", "Creating thumbnail", 70)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(
        stage="thumbnail",
        status="running",
        detail="Generating catchy thumbnail with Gemini",
    ))

    try:
        from services.gemini import image as gemini_image_svc

        hook_text = script.hook.text if script.hook else script.voiceover_full_script[:120]
        scene_visual = script.scenes[0].visual_prompt if script.scenes else hook_text

        thumb_path = await gemini_image_svc.generate_thumbnail(
            hook_text=hook_text,
            scene_visual_prompt=scene_visual,
            character_description=char_desc or None,
            art_style=art_style,
        )
        thumbnail_url = await gcs.upload_file(
            local_path=thumb_path,
            gcs_key=f"projects/{project_id}/thumbnail.jpg",
            content_type="image/jpeg",
        )
        try:
            os.unlink(thumb_path)
        except OSError:
            pass

        stages[-1].status = "completed"
        stages[-1].detail = f"Thumbnail uploaded → {thumbnail_url}"
        return thumbnail_url
    except Exception as _thumb_exc:
        logger.warning("Thumbnail generation failed (non-fatal): %s", _thumb_exc)
        stages[-1].status = "failed"
        stages[-1].detail = str(_thumb_exc)
        return None
