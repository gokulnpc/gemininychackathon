"""Stage 3: TTS voiceover generation and STT word timestamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Awaitable, Callable

from models.schemas import PipelineStageStatus, ScriptGenerationResponse
from services.media import captions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceoverStageResult:
    voiceover_path: str | None
    word_timestamps: list
    timing_source: str
    actual_duration: float | None


async def run_voiceover_stage(
    stages: list[PipelineStageStatus],
    script: ScriptGenerationResponse,
    voice_id: str,
    resolved_duration: int,
    on_progress: Callable[[str, str, int], Awaitable[None]] | None = None,
) -> VoiceoverStageResult:
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
    actual_duration: float | None = None
    try:
        from services.gemini import tts as gemini_tts
        voiceover_path = await gemini_tts.generate_voiceover(
            text=script.voiceover_full_script,
            voice_name=voice_id,
        )
        from services.media import ffmpeg as ffmpeg_svc
        actual_duration = await ffmpeg_svc._get_duration(voiceover_path)
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
            timing_source = "stt"
        except Exception as _stt_exc:
            logger.warning("STT word timestamps failed — falling back to estimated: %s", _stt_exc)
            word_timestamps = captions.generate_word_timestamps_from_script(
                voiceover_text=script.voiceover_full_script,
                total_duration=actual_duration or float(resolved_duration),
            )
            timing_source = "estimated"
    else:
        word_timestamps = captions.generate_word_timestamps_from_script(
            voiceover_text=script.voiceover_full_script,
            total_duration=resolved_duration,
        )
        timing_source = "estimated_no_audio"

    return VoiceoverStageResult(
        voiceover_path=voiceover_path,
        word_timestamps=word_timestamps,
        timing_source=timing_source,
        actual_duration=actual_duration,
    )
