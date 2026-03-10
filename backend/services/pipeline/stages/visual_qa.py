"""Stage 4c: Visual Quality Director — review and fix low-quality scene images."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus, ScriptGenerationResponse

logger = logging.getLogger(__name__)


async def run_visual_qa_stage(
    stages: list[PipelineStageStatus],
    all_image_paths: list[str],
    script: ScriptGenerationResponse,
    char_desc: str,
    art_style: str,
    user_reference_path: str | None,
    character_ref_path: str | None,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> tuple[list[str], list[dict]]:
    """Run VQD review; falls back to original images on failure.

    Returns (reviewed_image_paths, qa_report).
    """
    if on_progress:
        try:
            await on_progress("visual_qa", "Reviewing visual quality", 65)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(
        stage="visual_qa",
        status="running",
        detail="Visual Quality Director: reviewing scene images",
    ))

    try:
        from services.content import visual_quality_director
        reviewed_image_paths, qa_report = await visual_quality_director.review_and_fix_scenes(
            scene_images=all_image_paths,
            scenes=script.scenes,
            character_description=char_desc,
            art_style=art_style,
            user_reference_path=user_reference_path,
            character_ref_path=character_ref_path,
        )
        improved = sum(1 for r in qa_report if r.get("regenerated"))
        stages[-1].status = "completed"
        stages[-1].detail = f"VQD reviewed {len(qa_report)} scenes; {improved} improved"
        return reviewed_image_paths, qa_report
    except Exception as _vqd_exc:
        logger.warning("VQD failed (non-fatal, using original images): %s", _vqd_exc)
        stages[-1].status = "failed"
        stages[-1].detail = str(_vqd_exc)
        return all_image_paths, []
