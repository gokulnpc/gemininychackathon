"""Gemini multimodal audio transcription + tone detection for Content Factory.

Replaces the ElevenLabs Scribe transcription path.
Uses Gemini 2.5 Pro's native audio understanding — no separate STT model needed.

Returns transcript + detected emotional tone so the script agent can use the
creator's natural energy as a style signal.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-pro"

# Maps audio file extensions to MIME types accepted by Gemini
_MIME_MAP: dict[str, str] = {
    "webm": "audio/webm",
    "mp3":  "audio/mp3",
    "wav":  "audio/wav",
    "m4a":  "audio/mp4",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
}


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
        ValueError: if GEMINI_API_KEY is not set.
        RuntimeError: if Gemini returns an unusable response.
    """
    from google.genai import types

    from services.gemini.client import get_client
    client = get_client(force_api_key=True)
    mime_type = _MIME_MAP.get(audio_format.lower(), "audio/webm")
    audio_bytes = base64.b64decode(audio_b64)

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

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL,
        contents=[
            types.Content(parts=[
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
                types.Part(text=prompt),
            ])
        ],
    )

    text = response.text or ""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            logger.info(
                "Gemini audio: %d chars transcribed, tone=%s lang=%s",
                len(result.get("transcript", "")),
                result.get("detected_tone"),
                result.get("language"),
            )
            return {
                "transcript":    result.get("transcript", "").strip(),
                "detected_tone": result.get("detected_tone", "conversational"),
                "language":      result.get("language", "en-US"),
            }
        except json.JSONDecodeError:
            pass

    # Fallback: treat the whole response as the transcript
    logger.warning("Gemini audio: could not parse JSON — using raw text as transcript")
    return {
        "transcript":    text.strip(),
        "detected_tone": "conversational",
        "language":      "en-US",
    }
