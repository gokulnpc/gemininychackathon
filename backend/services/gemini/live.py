"""Gemini Live API — real-time audio transcription with tone detection.

Model: Gemini Live native-audio model from `services.gemini.models`
Uses bidirectional streaming: audio in → transcript text out.
Tone classification is a follow-up turn after transcription completes.

The browser should send raw PCM16 mono audio at 16000 Hz (no container).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from collections.abc import AsyncIterator, Callable, Coroutine

logger = logging.getLogger(__name__)

from services.gemini.models import MODELS

MODEL = MODELS.live_audio

_TRANSCRIPTION_SYSTEM = (
    "You are a real-time transcription service. "
    "Transcribe every word spoken exactly as heard, in the original language. "
    "Output only the spoken words — no commentary, labels, or punctuation beyond commas and periods."
)

_LIVE_CONFIG = {
    "response_modalities": ["AUDIO"],
    "input_audio_transcription": {},
    "system_instruction": {"parts": [{"text": _TRANSCRIPTION_SYSTEM}]}
}

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
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)

    full_transcript = ""
    async with client.aio.live.connect(model=MODEL, config=_LIVE_CONFIG) as session:

        # ── Send audio chunks concurrently with receiving ──────────────────
        async def _send_audio() -> None:
            try:
                async for chunk in audio_chunks:
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                    )
                await session.send_realtime_input(audio_stream_end=True)
            except Exception as e:
                logger.warning("Live audio send task aborted: %s", e)

        send_task = asyncio.create_task(_send_audio())

        # ── Collect transcript as text chunks arrive ───────────────────────
        completed_text = ""
        current_turn_parts: list[str] = []

        async for response in session.receive():
            server_content = getattr(response, "server_content", None)
            
            it = getattr(server_content, "input_transcription", None) if server_content else None
            if it and getattr(it, "text", None):
                t = it.text.strip()
                if t:
                    current_turn_parts.append(t)
                    combined = f"{completed_text} {' '.join(current_turn_parts)}".strip()
                    logger.info("LIVE_TRANSCRIPT: input chunk='%s', combined='%s'", t, combined)
                    await on_transcript_chunk(combined)
            
            await asyncio.sleep(0)
            
            turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
            if turn_complete:
                if current_turn_parts:
                    completed_text = f"{completed_text} {' '.join(current_turn_parts)}".strip()
                    logger.info("LIVE_TRANSCRIPT: turn_complete. completed_text='%s'", completed_text)
                    current_turn_parts = []
                
                if send_task.done():
                    break

        await send_task
        if current_turn_parts:
            completed_text = f"{completed_text} {' '.join(current_turn_parts)}".strip()
        full_transcript = completed_text

        # ── Tone classification: follow-up turn in the same session ────────
        detected_tone = "conversational"
        try:
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": _TONE_PROMPT}]}],
                turn_complete=True
            )
            async for response in session.receive():
                server_content = getattr(response, "server_content", None)
                if server_content and server_content.output_transcription:
                    tone_text = server_content.output_transcription.text
                    if tone_text:
                        candidate = tone_text.strip().lower()
                        # Some punctuation might sneak in
                        for t in _VALID_TONES:
                            if t in candidate:
                                detected_tone = t
                                break
                
                turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
                if turn_complete:
                    break
        except Exception as _tone_exc:
            logger.warning("Tone detection failed: %s — defaulting to conversational", _tone_exc)

    logger.info(
        "Live transcription complete: %d chars, tone=%s",
        len(full_transcript), detected_tone,
    )
    return {
        "transcript":    full_transcript.strip(),
        "detected_tone": detected_tone,
        "language":      "en-US",
    }


# ── REST wrapper ──────────────────────────────────────────────────────────────

# Max decoded audio size in bytes (inherited from audio.py logic)
MAX_AUDIO_BYTES = 20 * 1024 * 1024  # 20 MB

def _validate_audio_input(audio_b64: str) -> bytes:
    """Validate and decode base64 audio. Returns raw bytes."""
    if not audio_b64 or not audio_b64.strip():
        raise ValueError("audio_b64 is required and cannot be empty")

    try:
        audio_bytes = base64.b64decode(audio_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"Invalid base64 audio data: {exc}") from exc

    if len(audio_bytes) == 0:
        raise ValueError("Decoded audio is empty (0 bytes)")

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        size_mb = len(audio_bytes) / (1024 * 1024)
        raise ValueError(
            f"Audio too large ({size_mb:.1f} MB) — max {MAX_AUDIO_BYTES // (1024*1024)} MB"
        )

    return audio_bytes


async def transcribe_base64_audio_live(audio_b64: str, audio_format: str = "webm") -> dict:
    """Wrapper for the Live API that handles standard base64 audio uploads.
    
    1. Decodes base64 and validates size.
    2. Runs FFmpeg to convert to PCM16 at 16000Hz mono.
    3. Streams the PCM file through the Live API.
    
    Args:
        audio_b64:    Base64-encoded audio bytes.
        audio_format: File extension hint.
        
    Returns:
        {"transcript": str, "detected_tone": str, "language": str}
        
    Raises:
        ValueError: If audio is invalid/too large.
        RuntimeError: On FFmpeg or API failure.
    """
    audio_bytes = _validate_audio_input(audio_b64)
    
    # ── 1. Write original file ──
    fd_in, path_in = tempfile.mkstemp(suffix=f".{audio_format.lstrip('.')}", prefix="live_in_")
    try:
        os.write(fd_in, audio_bytes)
    finally:
        os.close(fd_in)
        
    path_out = f"/tmp/live_out_{os.getpid()}_{id(audio_bytes)}.pcm"
    
    try:
        # ── 2. Convert to PCM16 16000Hz mono ──
        from services.media.ffmpeg import _run_ffmpeg
        # -f s16le: 16-bit signed little-endian PCM
        # -ac 1: mono
        # -ar 16000: 16kHz
        await _run_ffmpeg(
            ["ffmpeg", "-y", "-i", path_in, "-f", "s16le", "-ac", "1", "-ar", "16000", path_out],
            "convert to PCM16 for Live API",
        )
        
        # ── 3. Stream to Live API ──
        async def _pcm_chunk_generator() -> AsyncIterator[bytes]:
            with open(path_out, "rb") as f:
                while True:
                    # Read 1MB at a time
                    chunk = await asyncio.to_thread(f.read, 1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
                    await asyncio.sleep(0.01)  # tiny yield
                    
        async def _discard_transcript_chunk(text: str) -> None:
            pass  # We only care about the final aggregated result
            
        result = await transcribe_live(
            audio_chunks=_pcm_chunk_generator(),
            on_transcript_chunk=_discard_transcript_chunk,
        )
        
        # ── 4. Apply tone normalization ──
        if result["detected_tone"] not in _VALID_TONES:
            logger.info("Normalizing tone '%s' to 'conversational'", result["detected_tone"])
            result["detected_tone"] = "conversational"
            
        return result
        
    finally:
        # ── 5. Cleanup ──
        if os.path.exists(path_in):
            os.unlink(path_in)
        if os.path.exists(path_out):
            os.unlink(path_out)
