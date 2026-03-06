"""Gemini TTS — voiceover generation using Gemini 2.5 Flash native audio output.

Same GEMINI_API_KEY already in .env — no extra credentials needed.

Available voices:
  Narrative / dramatic : Aoede, Charon, Fenrir, Kore
  Calm / warm          : Orbit, Autonoe, Zephyr
  Upbeat / bright      : Puck, Laomedeia

Output: WAV file (24kHz, 16-bit mono PCM wrapped in WAV container)
"""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
import wave

from config import get_settings

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-preview-tts"

# Voice name → short description (used by GET /voices in catalog.py)
VOICE_CATALOGUE: dict[str, str] = {
    "Aoede":     "Warm female narrator — clear, engaging storytelling",
    "Charon":    "Deep dramatic male — authoritative and cinematic",
    "Fenrir":    "Bold intense male — high energy and commanding",
    "Kore":      "Soft female — gentle, conversational, friendly",
    "Orbit":     "Smooth calm male — soothing and measured",
    "Autonoe":   "Natural female — relaxed, down-to-earth",
    "Zephyr":    "Breezy upbeat female — light and enthusiastic",
    "Puck":      "Playful animated male — fun and expressive",
    "Laomedeia": "Bright cheerful female — energetic and warm",
}

DEFAULT_VOICE = "Aoede"


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Wrap raw PCM16 bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)       # 16-bit = 2 bytes per sample
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _invoke_tts(text: str, voice_name: str, api_key: str) -> bytes:
    """Synchronous Gemini TTS call — run via asyncio.to_thread."""
    import base64 as _b64

    from google.genai import types

    from services.gemini_client import get_client
    client = get_client(force_api_key=True)
    response = client.models.generate_content(
        model=MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        ),
    )

    for part in response.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob is not None:
            data = getattr(blob, "data", None)
            if data:
                if isinstance(data, str):
                    data = _b64.b64decode(data)
                return data

    raise RuntimeError("Gemini TTS returned no audio data")


async def generate_voiceover(
    text: str,
    voice_name: str = DEFAULT_VOICE,
) -> str:
    """Generate a voiceover WAV from text using Gemini TTS.

    Args:
        text:       Full voiceover script to synthesise.
        voice_name: Gemini voice name from VOICE_CATALOGUE.

    Returns:
        Absolute path to a temp WAV file.

    Raises:
        ValueError:   if GEMINI_API_KEY is not set.
        RuntimeError: if TTS fails.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in .env")

    voice = voice_name if voice_name in VOICE_CATALOGUE else DEFAULT_VOICE
    logger.info("Gemini TTS: voice=%s, %d chars", voice, len(text))

    pcm_data = await asyncio.to_thread(_invoke_tts, text, voice, api_key)

    wav_bytes = _pcm_to_wav(pcm_data)

    tmp_path = tempfile.mktemp(suffix=".wav", prefix="voicevid_tts_")
    with open(tmp_path, "wb") as f:
        f.write(wav_bytes)

    logger.info("Gemini TTS saved → %s (%d bytes)", tmp_path, len(wav_bytes))
    return tmp_path
