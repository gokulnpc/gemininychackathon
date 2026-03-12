"""Environment helpers for Gemini/ADK editing runtimes."""

from __future__ import annotations

import os


def settings_env() -> None:
    """Set ADK environment variables from app config."""
    from config import get_settings

    settings = get_settings()
    if settings.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.vertex_ai_location)
    elif settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)

