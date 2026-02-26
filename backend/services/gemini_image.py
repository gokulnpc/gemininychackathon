"""Gemini image generation — style-aware, character-consistent.

One image per scene (every 5 seconds). The selected art style drives:
  1. A curated cinematic style suffix appended to every prompt.
  2. Character consistency: first scene image is passed as a reference
     to all subsequent scene generations so characters stay visually
     cohesive across the entire video.

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

# ── Art style → cinematic prompt suffix ───────────────────────────────────────
# Each suffix steers the model's visual output without needing a reference image.

_STYLE_SUFFIXES: dict[str, str] = {
    "monochrome":    (
        "high-contrast black and white photography, dramatic chiaroscuro shadows, "
        "deep blacks and bright whites, silver gelatin darkroom aesthetic, no colour whatsoever"
    ),
    "colour_block":  (
        "bold geometric colour-blocking, flat saturated primary palette, "
        "contemporary minimal graphic design, clean crisp edges"
    ),
    "runway":        (
        "high-fashion editorial photography, sleek studio three-point lighting, "
        "Vogue magazine cover aesthetic, polished and modern"
    ),
    "risograph":     (
        "risograph print art, limited two-colour halftone grain, "
        "indie zine texture, slightly misaligned ink layers, lo-fi printed aesthetic"
    ),
    "technicolour":  (
        "vivid Technicolor film aesthetic, oversaturated warm cinema tones, "
        "1950s Hollywood glamour, lush jewel-toned palette"
    ),
    "gothic_clay":   (
        "dark gothic claymation, textured clay characters and environments, "
        "warm amber candle-lit gothic architecture, stop-motion quality, eerie handcrafted look"
    ),
    "dynamite":      (
        "explosive action-movie cinematography, dramatic fire and debris, "
        "high-contrast lens flare, intense kinetic energy, smoke-filled atmosphere"
    ),
    "salon":         (
        "soft Rembrandt portrait lighting, elegant neutral studio backdrop, "
        "fine-art photographic quality, refined and classical"
    ),
    "sketch":        (
        "detailed graphite pencil sketch on cream textured paper, "
        "expressive cross-hatching, gestural marks, monochromatic graphite tones"
    ),
    "cinematic":     (
        "anamorphic widescreen cinema, shallow depth of field bokeh, "
        "film grain, moody teal-and-orange colour grade, epic production value"
    ),
    "steampunk":     (
        "Victorian steampunk aesthetic, ornate brass gears and copper pipes, "
        "sepia-toned gaslight industrial atmosphere, intricate mechanical detail"
    ),
    "sunrise":       (
        "golden-hour warm backlight, soft sun flare, sweeping open landscape, "
        "amber and rose tones, hopeful and expansive atmosphere"
    ),
    # Legacy styles
    "comic":         (
        "bold comic-book illustration, strong black outlines, "
        "flat vivid CMYK colours, halftone dot texture, dynamic panel energy"
    ),
    "creepy_comic":  (
        "dark horror comic art, heavy black ink shadows, visceral unsettling detail, "
        "off-kilter dutch-angle compositions, dread and unease"
    ),
    "painting":      (
        "classical oil painting, visible impasto brushstrokes, rich chiaroscuro lighting, "
        "museum gallery quality, Old Masters technique"
    ),
    "ghibli":        (
        "Studio Ghibli anime, soft hand-painted watercolour backgrounds, "
        "expressive wide-eyed characters, magical warm light, lush nature detail"
    ),
    "polaroid":      (
        "vintage Polaroid photograph, warm faded chemical tones, "
        "light-leak vignette, nostalgic bokeh, intimate personal feel"
    ),
    "disney":        (
        "Disney 3D animation, bright joyful colour palette, "
        "appealing expressive characters, clean fluid rendering, family warmth"
    ),
    "realism":       (
        "photorealistic ultra-detailed 8K, hyperreal textures, "
        "professional DSLR photography, perfect natural lighting"
    ),
}

_FALLBACK_SUFFIX = (
    "vertical 9:16 portrait, cinematic dramatic lighting, ultra-detailed, top quality"
)


def _style_suffix(art_style: str) -> str:
    return _STYLE_SUFFIXES.get(art_style.lower(), _FALLBACK_SUFFIX)


def _extract_image(response) -> Image.Image | None:
    """Pull the first image from a Gemini response and resize to 9:16 portrait."""
    import base64 as _b64

    for part in response.parts:
        blob = getattr(part, "inline_data", None)
        if blob is None:
            continue
        raw = getattr(blob, "data", None)
        if raw is None:
            continue
        try:
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
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key or None)
    return client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )


async def generate_image(
    prompt: str,
    art_style: str = "realism",
    previous_image_path: str | None = None,
    character_reference_path: str | None = None,
) -> str:
    """Generate a scene image with art-style consistency and character reference.

    Args:
        prompt:                  Cinematic visual description from the script agent.
        art_style:               Gallery style name — maps to a cinematic style suffix.
        previous_image_path:     If provided, Gemini edits this image (scene evolution).
        character_reference_path: First-scene image reused to maintain character
                                  consistency across all subsequent scenes.

    Returns:
        Absolute path to a 576×1024 PNG temp file.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    suffix = _style_suffix(art_style)

    img: Image.Image | None = None

    # ── Build contents ────────────────────────────────────────────────────────
    if previous_image_path and os.path.exists(previous_image_path):
        prev_img = Image.open(previous_image_path).convert("RGB")

        if (
            character_reference_path
            and os.path.exists(character_reference_path)
            and character_reference_path != previous_image_path
        ):
            # Scenes 3+: reference both the first-scene character AND the previous scene
            char_img = Image.open(character_reference_path).convert("RGB")
            edit_prompt = (
                f"Create a new scene image continuing this visual story. "
                f"New scene: {prompt}. "
                f"CRITICAL: preserve the exact same characters, faces, costume, and visual identity "
                f"from the first reference image. Change the composition, camera angle, and action "
                f"to match the new scene. "
                f"Visual style: {suffix}. Vertical 9:16 portrait format. Top-quality render."
            )
            contents: list = [edit_prompt, char_img, prev_img]
            mode = "consistent-scene"
        else:
            # Scene 2: evolve the previous scene, maintaining style and characters
            edit_prompt = (
                f"Transform this image into a new scene: {prompt}. "
                f"Keep the same characters and faces. "
                f"Change the composition, action, and camera angle to match the new scene. "
                f"Maintain {suffix}. Vertical 9:16 portrait format. Top-quality render."
            )
            contents = [edit_prompt, prev_img]
            mode = "scene-evolution"

    else:
        # Scene 1: generate the opening image from scratch with full style guidance
        full_prompt = (
            f"{prompt}. "
            f"Style: {suffix}. "
            f"Vertical 9:16 portrait composition optimised for short-form video. "
            f"Ultra-detailed, cinematic lighting, top-quality render. "
            f"No text or watermarks."
        )
        contents = [full_prompt]
        mode = "generation"

    logger.info(
        "Gemini image [%s | %s] %dx%d → %s",
        mode, art_style, PORTRAIT_WIDTH, PORTRAIT_HEIGHT, prompt[:80],
    )

    # ── First attempt ─────────────────────────────────────────────────────────
    try:
        response = await asyncio.to_thread(_invoke, contents, api_key)
        img = _extract_image(response)
    except Exception as exc:
        logger.warning("Gemini image %s failed: %s — retrying with simple prompt", mode, exc)

    # ── Fallback: simple text-only prompt ─────────────────────────────────────
    if img is None:
        try:
            response = await asyncio.to_thread(
                _invoke,
                [f"Cinematic portrait scene. {suffix}. Vertical 9:16 format."],
                api_key,
            )
            img = _extract_image(response)
        except Exception as exc2:
            logger.warning("Gemini fallback also failed: %s", exc2)

    if img is None:
        raise RuntimeError(
            "Gemini image generation returned no image data. "
            "Check GEMINI_API_KEY and model availability."
        )

    tmp_path = tempfile.mktemp(suffix=".png", prefix="voicevid_gemini_")
    img.save(tmp_path, "PNG")
    logger.info("Gemini image saved → %s", tmp_path)
    return tmp_path
