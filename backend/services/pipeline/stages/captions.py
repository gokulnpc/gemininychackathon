"""Stage 5: SRT caption generation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus
from services.media import captions as captions_svc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptionsStageResult:
    path: str
    format: str
    render_mode: str
    style_requested: str
    style_effective: str
    degraded: bool


async def run_captions_stage(
    stages: list[PipelineStageStatus],
    word_timestamps: list,
    caption_style: str,
    work_dir: str,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> CaptionsStageResult:
    """Generate a caption asset for video rendering and return its metadata."""
    if on_progress:
        try:
            await on_progress("captions", "Generating captions", 75)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(stage="captions", status="running"))

    caption_artifact = captions_svc.generate_caption_asset(
        word_timestamps=word_timestamps,
        style=caption_style,
        output_path=os.path.join(work_dir, "captions"),
    )

    stages[-1].status = "completed"
    stages[-1].detail = (
        f"Generated {caption_artifact.style_effective} captions "
        f"({caption_artifact.render_mode})"
    )

    return CaptionsStageResult(
        path=caption_artifact.path,
        format=caption_artifact.format,
        render_mode=caption_artifact.render_mode,
        style_requested=caption_artifact.style_requested,
        style_effective=caption_artifact.style_effective,
        degraded=caption_artifact.degraded,
    )
