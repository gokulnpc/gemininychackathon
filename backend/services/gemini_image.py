"""Gemini image generation for VoiceVid pipeline.

Uses google-genai SDK (gemini-2.5-flash-image):
  - Chunk 0:   text prompt → fresh image  (generation mode)
  - Chunk 1-N: previous image + new prompt → evolved image  (editing mode)

The chain-editing approach creates a "living painting" effect — each scene
morphs from the previous rather than cutting to a completely different image,
giving the video a continuous, cinematic feel.

Output: 576×1024 PNG (9:16 portrait for short-form video)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile

from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-image"
PORTRAIT_WIDTH = 576
PORTRAIT_HEIGHT = 1024

# Artistic style injected into every prompt so the whole video looks cohesive
_STYLE_SUFFIX = (
    "vertical 9:16 portrait composition, "
    "ultra-cinematic, dramatic directional lighting, "
    "rich vivid colors, hyper-detailed, artistic digital painting"
)


def _extract_image(response) -> Image.Image | None:
    """Pull the first image out of a Gemini response and resize to portrait.

    Uses inline_data.data (raw bytes) directly — avoids the google-genai
    Image wrapper which lacks PIL methods like .convert().
    """
    import base64 as _b64

    for part in response.parts:
        blob = getattr(part, "inline_data", None)
        if blob is None:
            continue
        raw = getattr(blob, "data", None)
        if raw is None:
            continue
        try:
            # SDK may deliver bytes or a base64 string depending on version
            if isinstance(raw, str):
                raw = _b64.b64decode(raw)
            img = Image.open(io.BytesIO(raw))
            return img.convert("RGB").resize(
                (PORTRAIT_WIDTH, PORTRAIT_HEIGHT), Image.LANCZOS
            )
        except Exception as exc:
            logger.debug("inline_data decode failed: %s", exc)

    return None


def _invoke(contents: list, api_key: str) -> object:
    """Synchronous Gemini call — run via asyncio.to_thread."""
    from google import genai  # lazy import keeps startup fast

    client = genai.Client(api_key=api_key or None)
    return client.models.generate_content(model=MODEL, contents=contents)


async def generate_image(
    prompt: str,
    previous_image_path: str | None = None,
) -> str:
    """Generate or evolve a scene image using Gemini.

    Args:
        prompt: Visual description of this scene chunk.
        previous_image_path: If provided, Gemini *edits* this image rather
            than generating from scratch — creating a smooth visual transition
            between consecutive chunks.

    Returns:
        Absolute path to a 576×1024 PNG temp file (caller is responsible for
        deleting it once it's no longer needed as a base for the next chunk).
    """
    settings = get_settings()
    api_key = settings.gemini_api_key

    # ── Build contents list ───────────────────────────────────────────────────
    if previous_image_path and os.path.exists(previous_image_path):
        # Editing mode: evolve the previous frame with a clearly distinct composition
        edit_prompt = (
            f"Significantly transform this image to depict a new scene: {prompt}. "
            f"The composition, subjects, camera angle, and focal point must change noticeably. "
            f"Keep only the overall art style and {_STYLE_SUFFIX}."
        )
        prev_img = Image.open(previous_image_path).convert("RGB")
        contents: list = [edit_prompt, prev_img]
        mode = "editing"
    else:
        # Generation mode: paint the opening scene from scratch
        contents = [f"{prompt}, {_STYLE_SUFFIX}"]
        mode = "generating"

    logger.info("Gemini [%s] %dx%d → %s", mode, PORTRAIT_WIDTH, PORTRAIT_HEIGHT, prompt[:80])

    # ── First attempt ─────────────────────────────────────────────────────────
    img: Image.Image | None = None
    try:
        response = await asyncio.to_thread(_invoke, contents, api_key)
        img = _extract_image(response)
    except Exception as exc:
        logger.warning("Gemini %s failed: %s — retrying with fallback", mode, exc)

    # ── Fallback: safe generic prompt, no chaining ────────────────────────────
    if img is None:
        fallback_contents = [
            f"Cinematic portrait scene, dramatic studio lighting, vivid, {_STYLE_SUFFIX}"
        ]
        try:
            response = await asyncio.to_thread(_invoke, fallback_contents, api_key)
            img = _extract_image(response)
        except Exception as exc2:
            logger.warning("Gemini fallback also failed: %s", exc2)

    if img is None:
        raise RuntimeError(
            "Gemini image generation returned no image data after fallback. "
            "Check GEMINI_API_KEY and model availability."
        )

    # ── Save to temp file ─────────────────────────────────────────────────────
    tmp_path = tempfile.mktemp(suffix=".png", prefix="voicevid_gemini_")
    img.save(tmp_path, "PNG")
    logger.info("Gemini image saved → %s", tmp_path)
    return tmp_path
