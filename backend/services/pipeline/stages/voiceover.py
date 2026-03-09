"""Stage 3: TTS voiceover generation and STT word timestamps."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus, ScriptGenerationResponse
from services.media import captions

logger = logging.getLogger(__name__)


async def run_voiceover_stage(
    stages: list[PipelineStageStatus],
    script: ScriptGenerationResponse,
    voice_id: str,
    resolved_duration: int,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> tuple[str | None, list]:
    """Generate TTS audio and word-level timestamps.

    Returns (voiceover_path, word_timestamps).
    """
    if on_progress:
        try:
            await on_progress("voiceover", "Generating voiceover", 15)
        except Exception as _e:
            logger.debug("Progress callback error: %s", _e)

    stages.append(PipelineStageStatus(
        stage="voiceover",
        status="running",
        detail=f"Gemini TTS: voice={voice_id}",
    ))

    voiceover_path: str | None = None
    try:
        from services.gemini import tts as gemini_tts
        voiceover_path = await gemini_tts.generate_voiceover(
            text=script.voiceover_full_script,
            voice_name=voice_id,
        )
        stages[-1].status = "completed"
        stages[-1].detail = f"Gemini TTS: voice={voice_id}"
    except Exception as _tts_exc:
        logger.warning("TTS generation failed (video will have no voiceover): %s", _tts_exc)
        stages[-1].status = "failed"
        stages[-1].detail = str(_tts_exc)

    if voiceover_path:
        try:
            from services.media import stt as stt_svc
            word_timestamps = await stt_svc.extract_word_timestamps(voiceover_path)
        except Exception as _stt_exc:
            logger.warning("STT word timestamps failed — falling back to estimated: %s", _stt_exc)
            word_timestamps = captions.generate_word_timestamps_from_script(
                voiceover_text=script.voiceover_full_script,
                total_duration=resolved_duration,
            )
    else:
        word_timestamps = captions.generate_word_timestamps_from_script(
            voiceover_text=script.voiceover_full_script,
            total_duration=resolved_duration,
        )

    return voiceover_path, word_timestamps
