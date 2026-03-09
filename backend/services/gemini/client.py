"""Shared Gemini client factory.

On GCP (USE_VERTEX_AI=true): uses Vertex AI ADC for stable models (2.5 Pro).
Locally / for preview models: uses GEMINI_API_KEY.

Usage:
    from services.gemini.client import get_client

    # Vertex AI on GCP, API key locally:
    client = get_client()

    # Always use API key (preview models not yet on Vertex AI GA):
    client = get_client(force_api_key=True)
"""

from __future__ import annotations

import logging

from config import get_settings

logger = logging.getLogger(__name__)


def get_client(force_api_key: bool = False):
    """Return a configured genai.Client.

    Args:
        force_api_key: If True, always use the GEMINI_API_KEY even on GCP.
                       Use this for preview models (image gen, TTS, interleaved)
                       that may not yet be available on Vertex AI GA.
    """
    from google import genai

    settings = get_settings()

    if not force_api_key and settings.use_vertex_ai and settings.google_cloud_project:
        logger.debug(
            "Gemini client: Vertex AI (project=%s, location=%s)",
            settings.google_cloud_project,
            settings.vertex_ai_location,
        )
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.vertex_ai_location,
        )

    logger.debug("Gemini client: API key")
    return genai.Client(vertexai=False, api_key=settings.gemini_api_key or None)
