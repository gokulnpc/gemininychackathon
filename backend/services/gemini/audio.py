"""Gemini multimodal audio transcription + tone detection for Content Factory.

Replaces the ElevenLabs Scribe transcription path.
Uses Gemini 2.5 Pro's native audio understanding — no separate STT model needed.

Returns transcript + detected emotional tone so the script agent can use the
creator's natural energy as a style signal.

Production features:
    - Input validation (non-empty base64, valid encoding, size guard)
    - Audio size guard (rejects > 20 MB decoded)
    - Retry with exponential backoff on transient errors (429, 503, timeout)
    - Tone normalization to allowed enum values
    - Robust JSON extraction (direct parse → regex → markdown fence)
    - Unknown audio format warning
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-pro"

# ── Constants ─────────────────────────────────────────────────────────────────

# Max decoded audio size in bytes (Gemini inline data limit).
MAX_AUDIO_BYTES = 20 * 1024 * 1024  # 20 MB

# Retry configuration for transient Gemini errors.
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds — doubles each retry

# Allowed tone values.  Anything else from Gemini gets normalized to "conversational".
ALLOWED_TONES = frozenset({
    "excited", "calm", "urgent", "conversational",
    "authoritative", "storytelling", "dramatic",
})

# Maps audio file extensions to MIME types accepted by Gemini.
_MIME_MAP: dict[str, str] = {
    "webm": "audio/webm",
    "mp3":  "audio/mp3",
    "wav":  "audio/wav",
    "m4a":  "audio/mp4",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_audio_input(audio_b64: str) -> bytes:
    """Validate and decode base64 audio.  Returns raw bytes.

    Raises:
        ValueError: If input is empty, invalid base64, or exceeds size limit.
    """
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


def _resolve_mime_type(audio_format: str) -> str:
    """Resolve audio format to MIME type, warning on unknown formats."""
    fmt = audio_format.lower().lstrip(".")
    mime = _MIME_MAP.get(fmt)
    if mime is None:
        logger.warning(
            "Unknown audio format '%s' — defaulting to audio/webm. "
            "Supported formats: %s",
            audio_format,
            ", ".join(sorted(_MIME_MAP.keys())),
        )
        return "audio/webm"
    return mime


def _normalize_tone(tone: str | None) -> str:
    """Normalize detected_tone to an allowed enum value."""
    if tone and tone.lower().strip() in ALLOWED_TONES:
        return tone.lower().strip()
    if tone:
        logger.info("Unknown tone '%s' — normalizing to 'conversational'", tone)
    return "conversational"


def _extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from Gemini's response text.

    Tries in order:
    1. Direct json.loads() on the full text
    2. Extract from markdown ```json ... ``` fences
    3. Regex match for { ... } (non-greedy on newlines)
    """
    # 1. Direct parse
    try:
        result = json.loads(text.strip())
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Markdown fence extraction
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1))
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Regex for { ... }
    brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if brace_match:
        try:
            result = json.loads(brace_match.group())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _is_transient(exc: Exception) -> bool:
    """Check if a Gemini error is transient and worth retrying."""
    msg = str(exc).lower()
    transient_indicators = ("429", "503", "timeout", "unavailable", "resource exhausted", "deadline")
    return any(indicator in msg for indicator in transient_indicators)


# ── Core function ─────────────────────────────────────────────────────────────

async def transcribe_with_tone(audio_b64: str, audio_format: str = "webm") -> dict:
    """Transcribe audio and detect emotional tone using Gemini multimodal.

    Args:
        audio_b64:    Base64-encoded audio bytes.
        audio_format: File extension hint: webm, mp3, wav, m4a, ogg, flac.

    Returns:
        {
            "transcript":    str,   # word-for-word transcription
            "detected_tone": str,   # excited | calm | urgent | conversational |
                                    #   authoritative | storytelling | dramatic
            "language":      str,   # e.g. "en-US"
        }

    Raises:
        ValueError: If audio input is invalid or too large.
        RuntimeError: If Gemini returns an unusable response after retries.
    """
    # Validate input
    audio_bytes = _validate_audio_input(audio_b64)
    mime_type = _resolve_mime_type(audio_format)

    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)

    prompt = (
        "You are an expert audio transcriptionist and emotional tone analyst.\n\n"
        "Listen to this audio recording carefully and:\n"
        "1. Transcribe EVERY word spoken, exactly as said — do not summarise or paraphrase\n"
        "2. Detect the speaker's emotional/delivery tone\n"
        "3. Detect the spoken language\n\n"
        "Respond ONLY with a JSON object — no markdown fences:\n"
        "{\n"
        '  "transcript": "exact word-for-word transcription",\n'
        '  "detected_tone": "one of: excited|calm|urgent|conversational|authoritative|storytelling|dramatic",\n'
        '  "language": "BCP-47 code e.g. en-US"\n'
        "}"
    )

    # Retry loop for transient errors
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=[
                    types.Content(parts=[
                        types.Part(inline_data=types.Blob(
                            mime_type=mime_type, data=audio_bytes
                        )),
                        types.Part(text=prompt),
                    ])
                ],
            )
            break  # success
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES and _is_transient(exc):
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Gemini audio: transient error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise last_exc  # type: ignore[misc]

    text = response.text or ""

    # Extract and validate JSON
    parsed = _extract_json(text)
    if parsed:
        transcript = str(parsed.get("transcript", "")).strip()
        detected_tone = _normalize_tone(parsed.get("detected_tone"))
        language = str(parsed.get("language", "en-US")).strip() or "en-US"

        logger.info(
            "Gemini audio: %d chars transcribed, tone=%s lang=%s",
            len(transcript), detected_tone, language,
        )
        return {
            "transcript":    transcript,
            "detected_tone": detected_tone,
            "language":      language,
        }

    # Fallback: treat the whole response as the transcript
    logger.warning("Gemini audio: could not parse JSON — using raw text as transcript")
    return {
        "transcript":    text.strip(),
        "detected_tone": "conversational",
        "language":      "en-US",
    }
