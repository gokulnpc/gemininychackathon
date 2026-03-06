"""Gemini Live API — real-time audio transcription with tone detection.

Model: gemini-2.0-flash-live-001
Uses bidirectional streaming: audio in → transcript text out.
Tone classification is a follow-up turn after transcription completes.

The browser should send raw PCM16 mono audio at 16000 Hz (no container).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine

logger = logging.getLogger(__name__)

MODEL = "gemini-2.0-flash-live-001"

_TRANSCRIPTION_SYSTEM = (
    "You are a real-time transcription service. "
    "Transcribe every word spoken exactly as heard, in the original language. "
    "Output only the spoken words — no commentary, labels, or punctuation beyond commas and periods."
)

_TONE_PROMPT = (
    "Based on the speech you just transcribed, classify the speaker's emotional tone. "
    "Reply with ONLY one word from this exact list: "
    "excited | calm | urgent | conversational | authoritative | storytelling | dramatic"
)

_VALID_TONES = {"excited", "calm", "urgent", "conversational", "authoritative", "storytelling", "dramatic"}


async def transcribe_live(
    audio_chunks: AsyncIterator[bytes],
    on_transcript_chunk: Callable[[str], Coroutine],
) -> dict:
    """Stream audio to Gemini Live and return full transcript + detected tone.

    Args:
        audio_chunks:         Async iterator yielding raw PCM16 audio bytes (16kHz mono).
        on_transcript_chunk:  Async callback called with each partial transcript string.

    Returns:
        {"transcript": str, "detected_tone": str, "language": str}

    Raises:
        Exception: Propagates Gemini Live API errors to the caller.
    """
    from google.genai import types
    from services.gemini_client import get_client

    client = get_client(force_api_key=True)

    live_config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=_TRANSCRIPTION_SYSTEM,
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=100_000,
            sliding_window=types.SlidingWindow(target_tokens=80_000),
        ),
    )

    transcript_parts: list[str] = []

    async with client.aio.live.connect(model=MODEL, config=live_config) as session:

        # ── Send audio chunks concurrently with receiving ──────────────────
        async def _send_audio() -> None:
            async for chunk in audio_chunks:
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

        send_task = asyncio.create_task(_send_audio())

        # ── Collect transcript as text chunks arrive ───────────────────────
        async for response in session.receive():
            text = getattr(response, "text", None)
            if text and text.strip():
                transcript_parts.append(text)
                await on_transcript_chunk(text)

            server_content = getattr(response, "server_content", None)
            turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
            if send_task.done() and turn_complete:
                break

        await send_task

        # ── Tone classification: follow-up turn in the same session ────────
        detected_tone = "conversational"
        try:
            await session.send_message(content=_TONE_PROMPT)
            async for response in session.receive():
                tone_text = getattr(response, "text", None)
                if tone_text:
                    candidate = tone_text.strip().lower()
                    if candidate in _VALID_TONES:
                        detected_tone = candidate
                        break
                server_content = getattr(response, "server_content", None)
                turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
                if turn_complete:
                    break
        except Exception as _tone_exc:
            logger.warning("Tone detection failed: %s — defaulting to conversational", _tone_exc)

    full_transcript = " ".join(transcript_parts).strip()
    logger.info(
        "Live transcription complete: %d chars, tone=%s",
        len(full_transcript), detected_tone,
    )
    return {
        "transcript":    full_transcript,
        "detected_tone": detected_tone,
        "language":      "en-US",
    }
