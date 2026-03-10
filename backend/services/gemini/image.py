"""Gemini image generation helpers.

This module keeps the public async entrypoints stable while separating prompt
construction, provider invocation, response parsing, and temp-file persistence.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-image-preview"
_TEXT_MODEL = "gemini-2.0-flash"

_STYLES_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "styles")

_STYLE_SUFFIXES: dict[str, str] = {
    "cinematic": (
        "anamorphic widescreen cinema, shallow depth of field bokeh, "
        "film grain, moody teal-and-orange colour grade, epic production value"
    ),
    "color_block": (
        "bold geometric colour-blocking, flat saturated primary palette, "
        "contemporary minimal graphic design, clean crisp edges"
    ),
    "cyborg": (
        "cyberpunk cyborg aesthetic, mechanical body enhancements and bioluminescent circuits, "
        "neon-lit urban dystopia, chrome and carbon-fibre textures, sci-fi augmented reality"
    ),
    "depth_of_field": (
        "professional shallow depth of field, subject in sharp focus against a softly blurred background, "
        "creamy bokeh, DSLR 85mm portrait lens, natural diffused lighting"
    ),
    "dynamite": (
        "explosive action-movie cinematography, dramatic fire and debris, "
        "high-contrast lens flare, intense kinetic energy, smoke-filled atmosphere"
    ),
    "enamel_pin": (
        "enamel pin badge illustration, bold flat colours with thick black outlines, "
        "simplified graphic shapes, collectible badge aesthetic, vibrant limited palette"
    ),
    "gothic_clay": (
        "dark gothic claymation, textured clay characters and environments, "
        "warm amber candle-lit gothic architecture, stop-motion quality, eerie handcrafted look"
    ),
    "monochrome": (
        "high-contrast black and white photography, dramatic chiaroscuro shadows, "
        "deep blacks and bright whites, silver gelatin darkroom aesthetic, no colour whatsoever"
    ),
    "moody": (
        "dark atmospheric moody photography, deep brooding shadows, desaturated muted palette, "
        "low-key dramatic lighting, emotional tension, melancholic and introspective atmosphere"
    ),
    "mythic_fighter": (
        "epic fantasy warrior art, dramatic battle pose, mythological weaponry and armour, "
        "ancient gods aesthetic, heroic grandeur, divine light breaking through storm clouds"
    ),
    "oil_painting": (
        "classical oil painting, visible impasto brushstrokes, rich chiaroscuro lighting, "
        "museum gallery quality, Old Masters technique"
    ),
    "old_cartoon": (
        "vintage 1930s rubber-hose cartoon, Fleischer Studios aesthetic, "
        "exaggerated organic shapes, limited colour palette, film grain and vignette"
    ),
    "risograph": (
        "risograph print art, limited two-colour halftone grain, "
        "indie zine texture, slightly misaligned ink layers, lo-fi printed aesthetic"
    ),
    "runway": (
        "high-fashion editorial photography, sleek studio three-point lighting, "
        "Vogue magazine cover aesthetic, polished and modern"
    ),
    "salon": (
        "soft Rembrandt portrait lighting, elegant neutral studio backdrop, "
        "fine-art photographic quality, refined and classical"
    ),
    "sketch": (
        "detailed graphite pencil sketch on cream textured paper, "
        "expressive cross-hatching, gestural marks, monochromatic graphite tones"
    ),
    "steampunk": (
        "Victorian steampunk aesthetic, ornate brass gears and copper pipes, "
        "sepia-toned gaslight industrial atmosphere, intricate mechanical detail"
    ),
    "sunrise": (
        "golden-hour warm backlight, soft sun flare, sweeping open landscape, "
        "amber and rose tones, hopeful and expansive atmosphere"
    ),
    "surreal": (
        "surrealist dreamscape art, impossible juxtapositions, melting reality, "
        "Dalí-inspired bizarre imagery, dreamlike hyper-detailed atmosphere"
    ),
    "technicolor": (
        "vivid Technicolor film aesthetic, oversaturated warm cinema tones, "
        "1950s Hollywood glamour, lush jewel-toned palette"
    ),
}

_FALLBACK_SUFFIX = (
    "vertical 9:16 portrait, cinematic dramatic lighting, ultra-detailed, top quality"
)

_STYLE_FILENAME_ALIASES: dict[str, list[str]] = {}

ImageProvider = Callable[[list[object]], Image.Image | asyncio.Future]
TextProvider = Callable[[str, Image.Image], str | asyncio.Future]


class GeminiImageServiceError(RuntimeError):
    """Base exception for Gemini image service failures."""


class GeminiImageProviderError(GeminiImageServiceError):
    """Raised when the Gemini provider call fails."""


class GeminiImageResponseError(GeminiImageServiceError):
    """Raised when Gemini returns no usable image payload."""


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    art_style: str = "realism"
    previous_image_path: str | None = None
    character_reference_path: str | None = None
    user_reference_path: str | None = None
    user_character_role: str | None = None


@dataclass(frozen=True)
class CharacterSheetRequest:
    character_description: str
    art_style: str = "cinematic"
    user_reference_path: str | None = None


@dataclass(frozen=True)
class ThumbnailRequest:
    hook_text: str
    scene_visual_prompt: str
    character_description: str | None
    art_style: str = "cinematic"


@dataclass(frozen=True)
class _GenerationPlan:
    mode: str
    art_style: str
    primary_contents: list[object]
    fallback_contents: list[object]
    output_prefix: str
    output_suffix: str
    output_format: str
    save_kwargs: dict[str, Any]
    log_target: str
    has_style_reference: bool


def _normalize_art_style(art_style: str) -> str:
    return (art_style or "").strip().lower()


def _require_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


def _style_suffix(art_style: str) -> str:
    return _STYLE_SUFFIXES.get(_normalize_art_style(art_style), _FALLBACK_SUFFIX)


def _open_rgb_image(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _optional_rgb_image(path: str | None) -> Image.Image | None:
    if not path or not os.path.exists(path):
        return None
    return _open_rgb_image(path)


def _style_reference_image(art_style: str) -> Image.Image | None:
    """Load the backend reference image for this art style, if it exists."""
    key = _normalize_art_style(art_style)
    candidates = _STYLE_FILENAME_ALIASES.get(key, [key])

    for name in candidates:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(_STYLES_DIR, f"{name}{ext}")
            if not os.path.exists(path):
                continue
            try:
                return _open_rgb_image(path)
            except Exception as exc:
                logger.warning("Could not load style reference image %s: %s", path, exc)

    return None


def _extract_image(response: object) -> Image.Image | None:
    """Pull the first image from a Gemini response."""
    parts = getattr(response, "parts", None) or []

    for part in parts:
        try:
            as_image = getattr(part, "as_image", None)
            if callable(as_image):
                img = as_image()
                if img is not None:
                    return img.convert("RGB")
        except Exception:
            pass

        blob = getattr(part, "inline_data", None)
        if blob is None:
            continue
        raw = getattr(blob, "data", None)
        if raw is None:
            continue

        try:
            if isinstance(raw, str):
                raw = base64.b64decode(raw)
            with Image.open(io.BytesIO(raw)) as image:
                return image.convert("RGB")
        except Exception as exc:
            logger.debug("inline_data decode failed: %s", exc)

    return None


def _default_image_client_factory():
    from services.gemini.client import get_client

    return get_client(force_api_key=True)


def _default_text_client_factory():
    from services.gemini.client import get_client

    return get_client()


def _generate_gemini_image_sync(
    contents: list[object],
    *,
    client_factory: Callable[[], object] | None = None,
) -> Image.Image:
    from google.genai import types

    client = (client_factory or _default_image_client_factory)()
    try:
        response = client.models.generate_content(
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
    except Exception as exc:
        raise GeminiImageProviderError(f"Gemini image request failed: {exc}") from exc

    image = _extract_image(response)
    if image is None:
        raise GeminiImageResponseError("Gemini returned no image data.")
    return image


async def _generate_gemini_image(
    contents: list[object],
    *,
    client_factory: Callable[[], object] | None = None,
) -> Image.Image:
    return await asyncio.to_thread(
        _generate_gemini_image_sync,
        contents,
        client_factory=client_factory,
    )


def _generate_gemini_text_sync(
    prompt: str,
    image: Image.Image,
    *,
    client_factory: Callable[[], object] | None = None,
) -> str:
    client = (client_factory or _default_text_client_factory)()
    try:
        response = client.models.generate_content(model=_TEXT_MODEL, contents=[prompt, image])
    except Exception as exc:
        raise GeminiImageProviderError(f"Gemini text request failed: {exc}") from exc
    return (getattr(response, "text", "") or "").strip()


async def _generate_gemini_text(
    prompt: str,
    image: Image.Image,
    *,
    client_factory: Callable[[], object] | None = None,
) -> str:
    return await asyncio.to_thread(
        _generate_gemini_text_sync,
        prompt,
        image,
        client_factory=client_factory,
    )


async def _call_image_provider(
    contents: list[object],
    *,
    image_provider: ImageProvider | None = None,
) -> Image.Image:
    if image_provider is None:
        return await _generate_gemini_image(contents)

    result = image_provider(contents)
    if asyncio.iscoroutine(result):
        result = await result
    return result


async def _call_text_provider(
    prompt: str,
    image: Image.Image,
    *,
    text_provider: TextProvider | None = None,
) -> str:
    if text_provider is None:
        return await _generate_gemini_text(prompt, image)

    result = text_provider(prompt, image)
    if asyncio.iscoroutine(result):
        result = await result
    return (result or "").strip()


def _save_temp_image(
    image: Image.Image,
    *,
    prefix: str,
    suffix: str,
    output_format: str,
    save_kwargs: dict[str, Any] | None = None,
) -> str:
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    image.save(tmp_path, output_format, **(save_kwargs or {}))
    return tmp_path


def _user_role_instruction(user_character_role: str | None) -> str:
    if user_character_role == "main_character":
        return (
            "CRITICAL: The main protagonist in this scene must look exactly like the person "
            "in the user reference photo — match their face, hair colour, facial features, "
            "and build precisely. They are the central subject of this image."
        )
    if user_character_role == "side_character":
        return (
            "Include a supporting character in the scene who closely resembles the person "
            "in the user reference photo — match their face and general appearance. "
            "They should be visible but not the primary focus."
        )
    if user_character_role == "audience":
        return (
            "Somewhere in the scene, include a person in the background or crowd who "
            "resembles the user reference photo as a natural bystander or audience member."
        )
    return ""


def _style_transfer_instruction(style_ref_img: Image.Image | None, art_style: str) -> str:
    suffix = _style_suffix(art_style)
    if style_ref_img is not None:
        return (
            "Apply the exact visual style shown in the style reference image: "
            "match its colour palette, textures, rendering technique, and overall aesthetic. "
            f"Style description: {suffix}."
        )
    return f"Style: {suffix}."


def _fallback_scene_prompt(prompt: str, art_style: str) -> str:
    return f"Cinematic portrait scene: {prompt}. {_style_suffix(art_style)}. Vertical 9:16 format."


def _thumbnail_fallback_prompt(hook_text: str, art_style: str) -> str:
    return f"Scroll-stopping video thumbnail: {hook_text}. {_style_suffix(art_style)}. Vertical 9:16."


def _build_scene_generation_prompt(
    prompt: str,
    style_instruction: str,
    user_role_instruction: str,
) -> str:
    return (
        f"{prompt}. "
        f"{user_role_instruction} "
        f"{style_instruction} "
        "Vertical 9:16 portrait composition optimised for short-form video. "
        "Ultra-detailed, cinematic lighting, top-quality render. No text or watermarks."
    )


def _build_scene_evolution_prompt(
    prompt: str,
    style_instruction: str,
    user_role_instruction: str,
) -> str:
    return (
        f"Transform this image into a new 2-second scene: {prompt}. "
        "CRITICAL CONSISTENCY RULES:\n"
        "1. CHARACTER: Keep the same characters and faces — identical features, hair, skin tone, and costume.\n"
        f"2. ART STYLE: Maintain the exact same visual style — colour palette, rendering, and aesthetic. {style_instruction}\n"
        "3. Change only the composition, action, and camera angle to match the new scene.\n"
        f"{user_role_instruction} "
        "Vertical 9:16 portrait format. Ultra-consistent, top-quality render."
    )


def _build_consistent_scene_prompt(
    prompt: str,
    style_instruction: str,
    user_role_instruction: str,
) -> str:
    return (
        "Create a new 2-second scene image continuing this visual story. "
        f"New scene: {prompt}. "
        "CRITICAL CONSISTENCY RULES — violating these will break the video:\n"
        "1. CHARACTER: The main character must look IDENTICAL to the character reference image — "
        "same face, hair colour, skin tone, facial features, body type, and costume. Zero deviation.\n"
        f"2. ART STYLE: Match the exact visual style of the reference image — same colour palette, rendering technique, textures, and aesthetic. {style_instruction}\n"
        "3. COMPOSITION: Change only the camera angle, action, and scene environment to match the new scene.\n"
        f"{user_role_instruction} "
        "Vertical 9:16 portrait format. Ultra-consistent, top-quality render."
    )


def _build_thumbnail_prompt(
    hook_text: str,
    scene_visual_prompt: str,
    character_description: str | None,
    art_style: str,
) -> str:
    char_clause = f"Character: {character_description}. " if character_description else ""
    suffix = _style_suffix(art_style)
    return (
        "Create a visually striking social media video thumbnail.\n"
        f"Hook concept: {hook_text}\n"
        f"Scene visual: {scene_visual_prompt}\n"
        f"{char_clause}"
        f"Art style: {suffix}\n\n"
        "Make it dramatic, high-contrast, and bold. "
        "Clear focal point, vibrant colours, strong lighting. "
        "The image must make someone stop scrolling — cinematic intensity, "
        "compelling subject, professional quality. "
        "Vertical 9:16 portrait format. No text or watermarks."
    )


def _build_character_sheet_prompt(
    character_description: str,
    art_style: str,
    has_user_reference: bool,
) -> str:
    user_clause = ""
    if has_user_reference:
        user_clause = (
            "The character must look exactly like the person in the user reference photo — "
            "match their face, hair colour, skin tone, and build precisely. "
        )
    return (
        "Full-body character reference sheet. Neutral standing pose, arms at sides. "
        "Plain white or very light neutral background with no scenery or props. "
        f"{user_clause}"
        f"Character description: {character_description}. "
        f"Art style: {_style_suffix(art_style)}. "
        "Vertical 9:16 portrait. Single character centred. "
        "High detail, clean render. No text, no watermarks."
    )


def _build_scene_generation_plan(request: ImageGenerationRequest) -> _GenerationPlan:
    prompt = _require_text(request.prompt, "prompt")
    art_style = _normalize_art_style(request.art_style) or "realism"
    style_ref_img = _style_reference_image(art_style)
    style_instruction = _style_transfer_instruction(style_ref_img, art_style)
    user_img = _optional_rgb_image(request.user_reference_path)
    user_instruction = _user_role_instruction(request.user_character_role if user_img else None)

    primary_contents: list[object]
    previous_image = _optional_rgb_image(request.previous_image_path)
    character_reference = _optional_rgb_image(request.character_reference_path)

    if previous_image is not None:
        if (
            character_reference is not None
            and request.character_reference_path != request.previous_image_path
        ):
            primary_contents = [
                _build_consistent_scene_prompt(prompt, style_instruction, user_instruction),
            ]
            if style_ref_img is not None:
                primary_contents.append(style_ref_img)
            primary_contents.extend([character_reference, previous_image])
            if user_img is not None and request.user_character_role != "main_character":
                primary_contents.append(user_img)
            mode = "consistent-scene"
        else:
            primary_contents = [
                _build_scene_evolution_prompt(prompt, style_instruction, user_instruction),
            ]
            if style_ref_img is not None:
                primary_contents.append(style_ref_img)
            primary_contents.append(previous_image)
            if user_img is not None:
                primary_contents.append(user_img)
            mode = "scene-evolution"
    else:
        primary_contents = [
            _build_scene_generation_prompt(prompt, style_instruction, user_instruction),
        ]
        if style_ref_img is not None:
            primary_contents.append(style_ref_img)
        if user_img is not None:
            primary_contents.append(user_img)
        mode = "generation"

    fallback_contents: list[object] = [_fallback_scene_prompt(prompt, art_style)]
    if style_ref_img is not None:
        fallback_contents.append(style_ref_img)

    return _GenerationPlan(
        mode=mode,
        art_style=art_style,
        primary_contents=primary_contents,
        fallback_contents=fallback_contents,
        output_prefix="storylabs_gemini_",
        output_suffix=".png",
        output_format="PNG",
        save_kwargs={},
        log_target=prompt[:80],
        has_style_reference=style_ref_img is not None,
    )


def _build_character_sheet_plan(request: CharacterSheetRequest) -> _GenerationPlan:
    character_description = _require_text(request.character_description, "character_description")
    art_style = _normalize_art_style(request.art_style) or "cinematic"
    style_ref_img = _style_reference_image(art_style)
    user_img = _optional_rgb_image(request.user_reference_path)

    primary_contents: list[object] = [
        _build_character_sheet_prompt(
            character_description=character_description,
            art_style=art_style,
            has_user_reference=user_img is not None,
        )
    ]
    if style_ref_img is not None:
        primary_contents.append(style_ref_img)
    if user_img is not None:
        primary_contents.append(user_img)

    fallback_contents: list[object] = [
        "Character reference sheet, neutral pose, plain background. "
        f"{character_description}. {_style_suffix(art_style)}. Vertical 9:16."
    ]
    if style_ref_img is not None:
        fallback_contents.append(style_ref_img)

    return _GenerationPlan(
        mode="character-sheet",
        art_style=art_style,
        primary_contents=primary_contents,
        fallback_contents=fallback_contents,
        output_prefix="storylabs_charsheet_",
        output_suffix=".png",
        output_format="PNG",
        save_kwargs={},
        log_target=character_description[:80],
        has_style_reference=style_ref_img is not None,
    )


def _build_thumbnail_plan(request: ThumbnailRequest) -> _GenerationPlan:
    hook_text = _require_text(request.hook_text, "hook_text")
    scene_visual_prompt = _require_text(request.scene_visual_prompt, "scene_visual_prompt")
    art_style = _normalize_art_style(request.art_style) or "cinematic"
    style_ref_img = _style_reference_image(art_style)

    primary_contents: list[object] = [
        _build_thumbnail_prompt(
            hook_text=hook_text,
            scene_visual_prompt=scene_visual_prompt,
            character_description=request.character_description,
            art_style=art_style,
        )
    ]
    if style_ref_img is not None:
        primary_contents.append(style_ref_img)

    fallback_contents: list[object] = [_thumbnail_fallback_prompt(hook_text, art_style)]

    return _GenerationPlan(
        mode="thumbnail",
        art_style=art_style,
        primary_contents=primary_contents,
        fallback_contents=fallback_contents,
        output_prefix="storylabs_thumb_",
        output_suffix=".jpg",
        output_format="JPEG",
        save_kwargs={"quality": 92},
        log_target=hook_text[:60],
        has_style_reference=style_ref_img is not None,
    )


async def _execute_generation_plan(
    plan: _GenerationPlan,
    *,
    image_provider: ImageProvider | None = None,
) -> str:
    logger.info(
        "Gemini image [%s | %s | style_ref=%s] → %s",
        plan.mode,
        plan.art_style,
        "yes" if plan.has_style_reference else "no",
        plan.log_target,
    )

    last_error: GeminiImageServiceError | None = None

    for label, contents in (
        ("primary", plan.primary_contents),
        ("fallback", plan.fallback_contents),
    ):
        try:
            image = await _call_image_provider(contents, image_provider=image_provider)
            tmp_path = _save_temp_image(
                image,
                prefix=plan.output_prefix,
                suffix=plan.output_suffix,
                output_format=plan.output_format,
                save_kwargs=plan.save_kwargs,
            )
            logger.info("Gemini image saved → %s", tmp_path)
            return tmp_path
        except GeminiImageServiceError as exc:
            last_error = exc
            logger.warning("%s %s attempt failed: %s", plan.mode, label, exc)
        except Exception as exc:
            last_error = GeminiImageProviderError(f"Unexpected image provider failure: {exc}")
            logger.warning("%s %s attempt failed: %s", plan.mode, label, exc)

    if last_error is not None:
        raise last_error
    raise GeminiImageResponseError("Gemini image generation produced no result.")


def _describe_subject_prompt() -> str:
    return (
        "Describe the person in this photo for use as context in a short-form video script. "
        "Provide a single sentence covering: apparent gender, approximate age range, "
        "clothing or style context, and expression or mood. "
        "Example: 'A woman in her early 30s, professional business attire, warm confident smile.' "
        "Do not identify or name the person — only describe visible visual attributes. "
        "Respond with only the descriptive sentence, no preamble."
    )


async def describe_reference_subject(
    image_path: str,
    *,
    text_provider: TextProvider | None = None,
) -> str:
    """Use Gemini Vision to extract brief subject context from a reference photo."""
    if not image_path or not os.path.exists(image_path):
        return ""

    try:
        image = _open_rgb_image(image_path)
        result = await _call_text_provider(
            _describe_subject_prompt(),
            image,
            text_provider=text_provider,
        )
        logger.info("Reference subject inferred: %s", result)
        return result
    except Exception as exc:
        logger.warning("Reference subject inference failed — skipping: %s", exc)
        return ""


async def generate_image(
    prompt: str,
    art_style: str = "realism",
    previous_image_path: str | None = None,
    character_reference_path: str | None = None,
    user_reference_path: str | None = None,
    user_character_role: str | None = None,
    *,
    image_provider: ImageProvider | None = None,
) -> str:
    """Generate a scene image with art-style and character-consistency support."""
    plan = _build_scene_generation_plan(
        ImageGenerationRequest(
            prompt=prompt,
            art_style=art_style,
            previous_image_path=previous_image_path,
            character_reference_path=character_reference_path,
            user_reference_path=user_reference_path,
            user_character_role=user_character_role,
        )
    )
    return await _execute_generation_plan(plan, image_provider=image_provider)


async def generate_character_sheet(
    character_description: str,
    art_style: str = "cinematic",
    user_reference_path: str | None = None,
    *,
    image_provider: ImageProvider | None = None,
) -> str:
    """Generate a neutral full-body character sheet image for use as a stable reference."""
    plan = _build_character_sheet_plan(
        CharacterSheetRequest(
            character_description=character_description,
            art_style=art_style,
            user_reference_path=user_reference_path,
        )
    )
    return await _execute_generation_plan(plan, image_provider=image_provider)


async def generate_thumbnail(
    hook_text: str,
    scene_visual_prompt: str,
    character_description: str | None,
    art_style: str = "cinematic",
    *,
    image_provider: ImageProvider | None = None,
) -> str:
    """Generate a catchy thumbnail image for the video."""
    plan = _build_thumbnail_plan(
        ThumbnailRequest(
            hook_text=hook_text,
            scene_visual_prompt=scene_visual_prompt,
            character_description=character_description,
            art_style=art_style,
        )
    )
    return await _execute_generation_plan(plan, image_provider=image_provider)
