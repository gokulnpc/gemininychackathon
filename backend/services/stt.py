"""Google Cloud Speech-to-Text — word-level timestamp extraction.

Uses ADC (Application Default Credentials) — no extra config needed on Cloud Run
or locally after `gcloud auth application-default login`.

Prerequisite:
    gcloud services enable speech.googleapis.com --project=YOUR_PROJECT_ID
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _invoke_stt(wav_path: str, sample_rate: int = 24000) -> list[dict]:
    """Synchronous STT call — run via asyncio.to_thread.

    Returns list of {"word": str, "start": float, "end": float}.
    """
    from google.cloud import speech

    client = speech.SpeechClient()  # uses ADC

    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate,
        audio_channel_count=1,
        language_code="en-US",
        enable_word_time_offsets=True,
    )

    response = client.recognize(config=config, audio=audio)

    timestamps: list[dict] = []
    for result in response.results:
        for word_info in result.alternatives[0].words:
            timestamps.append({
                "word":  word_info.word,
                "start": word_info.start_time.total_seconds(),
                "end":   word_info.end_time.total_seconds(),
            })

    logger.info("STT: extracted %d word timestamps from %s", len(timestamps), wav_path)
    return timestamps


async def extract_word_timestamps(wav_path: str, sample_rate: int = 24000) -> list[dict]:
    """Extract word-level timestamps from a WAV file using GCP Speech-to-Text.

    Args:
        wav_path:    Path to a WAV file (LINEAR16, mono).
        sample_rate: Sample rate in Hz (default 24000 — matches Gemini TTS output).

    Returns:
        List of {"word": str, "start": float, "end": float} dicts.

    Raises:
        Exception: Propagates GCP errors — caller should catch and fall back.
    """
    return await asyncio.to_thread(_invoke_stt, wav_path, sample_rate)
