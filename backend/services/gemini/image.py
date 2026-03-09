"""Gemini image generation — style-aware, character-consistent.

One image per scene (every 5 seconds). The selected art style drives:
  1. A curated cinematic style suffix appended to every prompt.
  2. A reference style image from assets/styles/<art_style>.png passed to Gemini
     for true visual style transfer (not just text guidance).
  3. Character consistency: first scene image is passed as a reference
     to all subsequent scene generations so characters stay visually
     cohesive across the entire video.

Output: native 9:16 portrait from Gemini image_config (target ~576×1024).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-image-preview"

# Art style reference images live here — one PNG per style
_STYLES_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "styles")

# ── Art style → cinematic prompt suffix ───────────────────────────────────────
# Used alongside the style reference image for double-strength style guidance.

_STYLE_SUFFIXES: dict[str, str] = {
    # ── Active styles (reference images in assets/styles/) ─────────────────────
    "cinematic":     (
        "anamorphic widescreen cinema, shallow depth of field bokeh, "
        "film grain, moody teal-and-orange colour grade, epic production value"
    ),
    "color_block":   (
        "bold geometric colour-blocking, flat saturated primary palette, "
        "contemporary minimal graphic design, clean crisp edges"
    ),
    "cyborg":        (
        "cyberpunk cyborg aesthetic, mechanical body enhancements and bioluminescent circuits, "
        "neon-lit urban dystopia, chrome and carbon-fibre textures, sci-fi augmented reality"
    ),
    "depth_of_field": (
        "professional shallow depth of field, subject in sharp focus against a softly blurred background, "
        "creamy bokeh, DSLR 85mm portrait lens, natural diffused lighting"
    ),
    "dynamite":      (
        "explosive action-movie cinematography, dramatic fire and debris, "
        "high-contrast lens flare, intense kinetic energy, smoke-filled atmosphere"
    ),
    "enamel_pin":    (
        "enamel pin badge illustration, bold flat colours with thick black outlines, "
        "simplified graphic shapes, collectible badge aesthetic, vibrant limited palette"
    ),
    "gothic_clay":   (
        "dark gothic claymation, textured clay characters and environments, "
        "warm amber candle-lit gothic architecture, stop-motion quality, eerie handcrafted look"
    ),
    "monochrome":    (
        "high-contrast black and white photography, dramatic chiaroscuro shadows, "
        "deep blacks and bright whites, silver gelatin darkroom aesthetic, no colour whatsoever"
    ),
    "moody":         (
        "dark atmospheric moody photography, deep brooding shadows, desaturated muted palette, "
        "low-key dramatic lighting, emotional tension, melancholic and introspective atmosphere"
    ),
    "mythic_fighter": (
        "epic fantasy warrior art, dramatic battle pose, mythological weaponry and armour, "
        "ancient gods aesthetic, heroic grandeur, divine light breaking through storm clouds"
    ),
    "oil_painting":  (
        "classical oil painting, visible impasto brushstrokes, rich chiaroscuro lighting, "
        "museum gallery quality, Old Masters technique"
    ),
    "old_cartoon":   (
        "vintage 1930s rubber-hose cartoon, Fleischer Studios aesthetic, "
        "exaggerated organic shapes, limited colour palette, film grain and vignette"
    ),
    "risograph":     (
        "risograph print art, limited two-colour halftone grain, "
        "indie zine texture, slightly misaligned ink layers, lo-fi printed aesthetic"
    ),
    "runway":        (
        "high-fashion editorial photography, sleek studio three-point lighting, "
        "Vogue magazine cover aesthetic, polished and modern"
    ),
    "salon":         (
        "soft Rembrandt portrait lighting, elegant neutral studio backdrop, "
        "fine-art photographic quality, refined and classical"
    ),
    "sketch":        (
        "detailed graphite pencil sketch on cream textured paper, "
        "expressive cross-hatching, gestural marks, monochromatic graphite tones"
    ),
    "steampunk":     (
        "Victorian steampunk aesthetic, ornate brass gears and copper pipes, "
        "sepia-toned gaslight industrial atmosphere, intricate mechanical detail"
    ),
    "sunrise":       (
        "golden-hour warm backlight, soft sun flare, sweeping open landscape, "
        "amber and rose tones, hopeful and expansive atmosphere"
    ),
    "surreal":       (
        "surrealist dreamscape art, impossible juxtapositions, melting reality, "
        "Dalí-inspired bizarre imagery, dreamlike hyper-detailed atmosphere"
    ),
    "technicolor":   (
        "vivid Technicolor film aesthetic, oversaturated warm cinema tones, "
        "1950s Hollywood glamour, lush jewel-toned palette"
    ),
}

_FALLBACK_SUFFIX = (
    "vertical 9:16 portrait, cinematic dramatic lighting, ultra-detailed, top quality"
)


def _style_suffix(art_style: str) -> str:
    return _STYLE_SUFFIXES.get(art_style.lower(), _FALLBACK_SUFFIX)


# Alternate filenames for styles whose enum key differs from the stored filename.
# All current assets/styles/ filenames match their enum keys directly — no aliases needed.
_STYLE_FILENAME_ALIASES: dict[str, list[str]] = {}


def _style_reference_image(art_style: str) -> Image.Image | None:
    """Load the backend reference image for this art style, if it exists.

    Tries the canonical name first, then any known aliases, then .jpg extension.
    """
    key = art_style.lower()
    candidates = _STYLE_FILENAME_ALIASES.get(key, [key])

    for name in candidates:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(_STYLES_DIR, f"{name}{ext}")
            if os.path.exists(path):
                try:
                    return Image.open(path).convert("RGB")
                except Exception as e:
                    logger.warning("Could not load style reference image %s: %s", path, e)
    return None


def _extract_image(response) -> Image.Image | None:
    """Pull the first image from a Gemini response."""
    for part in response.parts:
        # New SDK: part.as_image()
        try:
            img = part.as_image()
            if img is not None:
                return img.convert("RGB")
        except Exception:
            pass

        # Fallback: inline_data bytes
        import base64 as _b64
        import io
        blob = getattr(part, "inline_data", None)
        if blob is None:
            continue
        raw = getattr(blob, "data", None)
        if raw is None:
            continue
        try:
            if isinstance(raw, str):
                raw = _b64.b64decode(raw)
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            logger.debug("inline_data decode failed: %s", exc)

    return None


def _invoke(contents: list, api_key: str) -> object:
    """Synchronous Gemini call — run via asyncio.to_thread."""
    from google.genai import types

    from services.gemini.client import get_client
    client = get_client(force_api_key=True)
    return client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16",
                image_size="1K",
            ),
        ),
    )


async def generate_image(
    prompt: str,
    art_style: str = "realism",
    previous_image_path: str | None = None,
    character_reference_path: str | None = None,
    user_reference_path: str | None = None,
    user_character_role: str | None = None,
) -> str:
    """Generate a scene image with art-style reference, character consistency, and optional user photo.

    Args:
        prompt:                  Cinematic visual description from the script agent.
        art_style:               Gallery style name — maps to a style reference image + text suffix.
        previous_image_path:     If provided, Gemini edits this image (scene evolution).
        character_reference_path: First-scene image reused to maintain character
                                  consistency across all subsequent scenes.
        user_reference_path:     Optional user photo for appearance-based personalisation.
        user_character_role:     "main_character" | "side_character" | "audience".

    Returns:
        Absolute path to a 9:16 portrait PNG temp file.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    suffix = _style_suffix(art_style)

    # ── Load art style reference image (real visual style transfer) ───────────
    style_ref_img = _style_reference_image(art_style)
    style_transfer_instruction = (
        f"Apply the exact visual style shown in the style reference image: "
        f"match its colour palette, textures, rendering technique, and overall aesthetic. "
        f"Style description: {suffix}."
        if style_ref_img is not None
        else f"Style: {suffix}."
    )

    # ── Role-specific instruction for user photo ───────────────────────────────
    user_img: Image.Image | None = None
    user_role_instruction = ""
    if user_reference_path and os.path.exists(user_reference_path) and user_character_role:
        user_img = Image.open(user_reference_path).convert("RGB")
        if user_character_role == "main_character":
            user_role_instruction = (
                "CRITICAL: The main protagonist in this scene must look exactly like the person "
                "in the user reference photo — match their face, hair colour, facial features, "
                "and build precisely. They are the central subject of this image."
            )
        elif user_character_role == "side_character":
            user_role_instruction = (
                "Include a supporting character in the scene who closely resembles the person "
                "in the user reference photo — match their face and general appearance. "
                "They should be visible but not the primary focus."
            )
        elif user_character_role == "audience":
            user_role_instruction = (
                "Somewhere in the scene, include a person in the background or crowd who "
                "resembles the user reference photo as a natural bystander or audience member."
            )

    img: Image.Image | None = None

    # ── Build contents ────────────────────────────────────────────────────────
    if previous_image_path and os.path.exists(previous_image_path):
        prev_img = Image.open(previous_image_path).convert("RGB")

        if (
            character_reference_path
            and os.path.exists(character_reference_path)
            and character_reference_path != previous_image_path
        ):
            # Scenes 3+: character reference + previous scene + style
            char_img = Image.open(character_reference_path).convert("RGB")
            edit_prompt = (
                f"Create a new 2-second scene image continuing this visual story. "
                f"New scene: {prompt}. "
                f"CRITICAL CONSISTENCY RULES — violating these will break the video:\n"
                f"1. CHARACTER: The main character must look IDENTICAL to the character reference image — "
                f"same face, hair colour, skin tone, facial features, body type, and costume. Zero deviation.\n"
                f"2. ART STYLE: Match the exact visual style of the reference image — same colour palette, "
                f"rendering technique, textures, and aesthetic. {style_transfer_instruction}\n"
                f"3. COMPOSITION: Change only the camera angle, action, and scene environment to match the new scene.\n"
                f"{user_role_instruction} "
                f"Vertical 9:16 portrait format. Ultra-consistent, top-quality render."
            )
            # Order: prompt → style ref → character ref → previous scene → user photo
            contents: list = [edit_prompt]
            if style_ref_img is not None:
                contents.append(style_ref_img)
            contents.extend([char_img, prev_img])
            if user_img and user_character_role != "main_character":
                contents.append(user_img)
            mode = "consistent-scene"

        else:
            # Scene 2: evolve the previous scene
            edit_prompt = (
                f"Transform this image into a new 2-second scene: {prompt}. "
                f"CRITICAL CONSISTENCY RULES:\n"
                f"1. CHARACTER: Keep the same characters and faces — identical features, hair, skin tone, and costume.\n"
                f"2. ART STYLE: Maintain the exact same visual style — colour palette, rendering, and aesthetic. "
                f"{style_transfer_instruction}\n"
                f"3. Change only the composition, action, and camera angle to match the new scene.\n"
                f"{user_role_instruction} "
                f"Vertical 9:16 portrait format. Ultra-consistent, top-quality render."
            )
            contents = [edit_prompt]
            if style_ref_img is not None:
                contents.append(style_ref_img)
            contents.append(prev_img)
            if user_img:
                contents.append(user_img)
            mode = "scene-evolution"

    else:
        # Scene 1: generate from scratch
        full_prompt = (
            f"{prompt}. "
            f"{user_role_instruction} "
            f"{style_transfer_instruction} "
            f"Vertical 9:16 portrait composition optimised for short-form video. "
            f"Ultra-detailed, cinematic lighting, top-quality render. No text or watermarks."
        )
        contents = [full_prompt]
        if style_ref_img is not None:
            contents.append(style_ref_img)
        if user_img:
            contents.append(user_img)
        mode = "generation"

    logger.info(
        "Gemini image [%s | %s | style_ref=%s] → %s",
        mode, art_style, "yes" if style_ref_img else "no", prompt[:80],
    )

    # ── First attempt ─────────────────────────────────────────────────────────
    try:
        response = await asyncio.to_thread(_invoke, contents, api_key)
        img = _extract_image(response)
    except Exception as exc:
        logger.warning("Gemini image %s failed: %s — retrying with simple prompt", mode, exc)

    # ── Fallback: text-only prompt (no reference images) ──────────────────────
    if img is None:
        try:
            fallback_contents: list = [
                f"Cinematic portrait scene: {prompt}. {suffix}. Vertical 9:16 format."
            ]
            if style_ref_img is not None:
                fallback_contents.append(style_ref_img)
            response = await asyncio.to_thread(_invoke, fallback_contents, api_key)
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


async def generate_character_sheet(
    character_description: str,
    art_style: str = "cinematic",
    user_reference_path: str | None = None,
) -> str:
    """Generate a neutral full-body character sheet image for use as a stable reference.

    A plain-background, neutral-pose image anchors all scene generations so
    the character stays visually consistent. Generated once before the scene loop.

    Args:
        character_description: Physical description from script.metadata.character_description.
        art_style:             Art style enum value.
        user_reference_path:   Optional user photo — if provided, the character sheet
                               will incorporate their likeness.

    Returns:
        Absolute path to a 9:16 PNG temp file.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    suffix = _style_suffix(art_style)
    style_ref_img = _style_reference_image(art_style)

    user_clause = ""
    user_img: object | None = None
    if user_reference_path and os.path.exists(user_reference_path):
        user_img = Image.open(user_reference_path).convert("RGB")
        user_clause = (
            "The character must look exactly like the person in the user reference photo — "
            "match their face, hair colour, skin tone, and build precisely. "
        )

    prompt = (
        f"Full-body character reference sheet. Neutral standing pose, arms at sides. "
        f"Plain white or very light neutral background with no scenery or props. "
        f"{user_clause}"
        f"Character description: {character_description}. "
        f"Art style: {suffix}. "
        f"Vertical 9:16 portrait. Single character centred. "
        f"High detail, clean render. No text, no watermarks."
    )

    contents: list = [prompt]
    if style_ref_img is not None:
        contents.append(style_ref_img)
    if user_img is not None:
        contents.append(user_img)

    logger.info("Generating character sheet (art_style=%s, user_ref=%s)", art_style, "yes" if user_img else "no")

    img: Image.Image | None = None
    try:
        response = await asyncio.to_thread(_invoke, contents, api_key)
        img = _extract_image(response)
    except Exception as exc:
        logger.warning("Character sheet generation failed: %s — retrying text-only", exc)

    if img is None:
        fallback = [f"Character reference sheet, neutral pose, plain background. {character_description}. {suffix}. Vertical 9:16."]
        if style_ref_img is not None:
            fallback.append(style_ref_img)
        try:
            response = await asyncio.to_thread(_invoke, fallback, api_key)
            img = _extract_image(response)
        except Exception as exc2:
            raise RuntimeError(f"Character sheet generation failed: {exc2}") from exc2

    if img is None:
        raise RuntimeError("Character sheet generation returned no image data.")

    tmp_path = tempfile.mktemp(suffix=".png", prefix="voicevid_charsheet_")
    img.save(tmp_path, "PNG")
    logger.info("Character sheet saved → %s", tmp_path)
    return tmp_path


def _build_thumbnail_prompt(
    hook_text: str,
    scene_visual_prompt: str,
    character_description: str | None,
    art_style: str,
) -> str:
    """Build a scroll-stopping thumbnail generation prompt."""
    char_clause = (
        f"Character: {character_description}. "
        if character_description
        else ""
    )
    suffix = _style_suffix(art_style)
    return (
        f"Create a visually striking social media video thumbnail.\n"
        f"Hook concept: {hook_text}\n"
        f"Scene visual: {scene_visual_prompt}\n"
        f"{char_clause}"
        f"Art style: {suffix}\n\n"
        f"Make it dramatic, high-contrast, and bold. "
        f"Clear focal point, vibrant colours, strong lighting. "
        f"The image must make someone stop scrolling — cinematic intensity, "
        f"compelling subject, professional quality. "
        f"Vertical 9:16 portrait format. No text or watermarks."
    )


async def generate_thumbnail(
    hook_text: str,
    scene_visual_prompt: str,
    character_description: str | None,
    art_style: str = "cinematic",
) -> str:
    """Generate a catchy thumbnail image for the video.

    Uses Gemini image generation with a scroll-stopping prompt based on the
    hook concept and first scene visual. No reference images needed — this is
    a fresh, thumbnail-optimised generation.

    Args:
        hook_text:            The video's hook text (from script.hook.text).
        scene_visual_prompt:  First scene's visual prompt for visual context.
        character_description: Optional character description for consistency.
        art_style:            Art style enum value (e.g. "cinematic", "realism").

    Returns:
        Absolute path to a 9:16 JPEG temp file.

    Raises:
        RuntimeError: if Gemini returns no image data.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    prompt = _build_thumbnail_prompt(hook_text, scene_visual_prompt, character_description, art_style)

    style_ref_img = _style_reference_image(art_style)
    contents: list = [prompt]
    if style_ref_img is not None:
        contents.append(style_ref_img)

    logger.info("Generating thumbnail (hook=%s…, art_style=%s)", hook_text[:60], art_style)

    img: Image.Image | None = None
    try:
        response = await asyncio.to_thread(_invoke, contents, api_key)
        img = _extract_image(response)
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s — retrying with text-only prompt", exc)

    if img is None:
        try:
            response = await asyncio.to_thread(
                _invoke, [f"Scroll-stopping video thumbnail: {hook_text}. {_style_suffix(art_style)}. Vertical 9:16."], api_key
            )
            img = _extract_image(response)
        except Exception as exc2:
            logger.warning("Thumbnail fallback also failed: %s", exc2)

    if img is None:
        raise RuntimeError("Gemini thumbnail generation returned no image data.")

    tmp_path = tempfile.mktemp(suffix=".jpg", prefix="voicevid_thumb_")
    img.save(tmp_path, "JPEG", quality=92)
    logger.info("Thumbnail saved → %s", tmp_path)
    return tmp_path
