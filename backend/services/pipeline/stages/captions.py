"""Stage 5: SRT caption generation."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus
from services.media import captions as captions_svc

logger = logging.getLogger(__name__)


async def run_captions_stage(
    stages: list[PipelineStageStatus],
    word_timestamps: list,
    caption_style: str,
    work_dir: str,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> str:
    """Generate SRT file. Returns path to the .srt file."""
    if on_progress:
        try:
            await on_progress("captions", "Generating captions", 75)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(stage="captions", status="running"))

    srt_path = captions_svc.generate_srt(
        word_timestamps=word_timestamps,
        style=caption_style,
        output_path=os.path.join(work_dir, "captions.srt"),
    )

    stages[-1].status = "completed"
    stages[-1].detail = f"Generated {caption_style} captions"

    return srt_path
