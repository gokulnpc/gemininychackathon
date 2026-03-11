"""Central registry for Gemini model IDs used across the backend.

Use this module instead of hardcoding model strings in service modules.
Model selection is environment-configurable through `backend/config.py`.

Guidance:
- Live audio sessions use the native-audio preview model and currently require API-key routing.
- Stable text reasoning models can use Vertex AI when available.
- Image generation / mixed text+image output uses the image-capable model and currently
  stays on API-key routing in this codebase.
- TTS models stay on API-key routing.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import get_settings


@dataclass(frozen=True)
class GeminiModelRegistry:
    live_audio: str
    fast_text: str
    reasoning: str
    image_generation: str
    tts: str
    premium_tts: str


def get_gemini_models() -> GeminiModelRegistry:
    """Resolve model IDs from settings.

    This keeps the defaults centralized while allowing `.env` overrides for
    soft launches, demos, and emergency rollbacks.
    """
    settings = get_settings()
    return GeminiModelRegistry(
        live_audio=settings.gemini_live_model,
        fast_text=settings.gemini_fast_text_model,
        reasoning=settings.gemini_reasoning_model,
        image_generation=settings.gemini_image_model,
        tts=settings.gemini_tts_model,
        premium_tts=settings.gemini_premium_tts_model,
    )


MODELS = get_gemini_models()
