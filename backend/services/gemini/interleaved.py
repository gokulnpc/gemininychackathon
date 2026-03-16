"""Gemini Interleaved — Creative Director agent with mixed text+image output.

Uses Gemini's native interleaved output capability to generate rich, mixed-media
content in a single fluid API call. The model weaves together narrative text and
generated images based on the creative mode selected.

Supported modes:
  storybook        — alternating story paragraphs + inline illustrations
  marketing        — headline + hero image + body copy + CTA visual + hashtags
  educational      — narration sections + concept/diagram images
  social_content   — caption + post image + hashtag cloud

Model: Gemini image-capable model from `services.gemini.models`
  response_modalities=["TEXT", "IMAGE"] enables native interleaved output.
  A single prompt yields alternating text blocks and generated images.
"""

from __future__ import annotations

import asyncio
import base64
import logging

logger = logging.getLogger(__name__)

from services.gemini.models import MODELS

MODEL = MODELS.image_generation

# ── Mode-specific creative director prompts ────────────────────────────────────

_MODE_PROMPTS: dict[str, str] = {
    "storybook": (
        "You are Maya, Content Factory's creative director and illustrator. "
        "Create an engaging illustrated storybook with 4-6 scenes.\n\n"
        "Structure your output as alternating sections:\n"
        "1. Write 2-3 sentences of vivid narrative text for the scene.\n"
        "2. Generate a full illustration for that scene.\n"
        "3. Repeat for the next scene.\n\n"
        "Make the story emotionally resonant with clear character arcs. "
        "End with a compelling moral or takeaway message followed by a final illustration."
    ),
    "marketing": (
        "You are Maya, Content Factory's creative director. "
        "Build a complete marketing asset package.\n\n"
        "Generate content in this exact order:\n"
        "1. Write a punchy, benefit-led headline (1 sentence).\n"
        "2. Generate a hero image that captures the brand essence.\n"
        "3. Write 3-4 sentences of body copy highlighting key benefits.\n"
        "4. Generate a lifestyle image showing the product/service in real-world context.\n"
        "5. Write the call-to-action text (1 sentence, action-oriented).\n"
        "6. Generate a CTA visual (button or banner concept).\n"
        "7. Write 12-15 targeted hashtags.\n\n"
        "Keep all copy punchy, benefit-focused, and conversion-optimised."
    ),
    "educational": (
        "You are Maya, Content Factory's educational content director. "
        "Build a clear visual explainer.\n\n"
        "For each of 3-4 key concepts:\n"
        "1. Write a brief, jargon-free explanation (2-3 sentences).\n"
        "2. Generate a diagram or visual that illustrates the concept clearly.\n"
        "3. Add a one-sentence 'Key Takeaway' summary.\n\n"
        "End with a summary text connecting all concepts, "
        "followed by a final infographic-style visual showing how they relate. "
        "Assume zero prior knowledge — use analogies where helpful."
    ),
    "social_content": (
        "You are Maya, Content Factory's social media creative director. "
        "Generate a complete, ready-to-post social content package.\n\n"
        "Produce in this order:\n"
        "1. Write an attention-grabbing hook (1-2 sentences that stop the scroll).\n"
        "2. Generate the main post image — eye-catching, scroll-stopping, platform-native.\n"
        "3. Write the full caption with clear value, personality, and a soft CTA.\n"
        "4. Generate a secondary carousel/swipe image featuring a key stat or pull-quote.\n"
        "5. Write 15-20 targeted, trending hashtags.\n"
        "6. Write 2 alternative caption variations for A/B testing.\n\n"
        "Optimise everything for high engagement and shareability."
    ),
    "manga": (
        "You are a manga/manhwa artist and visual storyteller. "
        "Create a sequential visual story told panel by panel.\n\n"
        "Structure your output STRICTLY as:\n"
        "1. Write ONE short panel caption text (1–2 punchy sentences, present tense, dramatic). "
        "Output it as plain text first — one caption only, no extra paragraphs.\n"
        "2. Generate ONE vertical 9:16 panel illustration. "
        "CRITICAL: Render the caption text DIRECTLY INSIDE the image as a manga-style caption box "
        "at the bottom of the panel — white bold text on a solid black background bar. "
        "The text must be clearly legible and visually part of the artwork.\n"
        "3. Repeat for the next panel.\n\n"
        "Visual style requirements for EVERY panel:\n"
        "- Bold line art with high-contrast shadows and deep blacks\n"
        "- Cinematic framing: extreme close-ups, low angles, dynamic action poses\n"
        "- Expressive character emotions that carry the narrative\n"
        "- Speed lines, impact effects, and manga-style motion where appropriate\n"
        "- Consistent character design across ALL panels\n\n"
        "Story structure: strong hook → rising tension → climax → punchy ending. "
        "No filler — every panel must advance the story."
    ),
}


def _build_prompt(mode: str, brief: str, art_style: str | None) -> str:
    """Combine the mode system prompt with the user's creative brief."""
    system = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["social_content"])
    style_clause = (
        f"\n\nArt style for ALL generated images: {art_style}. "
        "Apply this style consistently across every image in the package."
        if art_style
        else ""
    )
    aspect_clause = (
        "\n\nIMPORTANT: ALL generated images must use a 9:16 portrait (vertical) aspect ratio — "
        "optimised for YouTube Shorts, Instagram Reels, and TikTok. Never generate landscape or square images."
    )
    return f"{system}{style_clause}{aspect_clause}\n\n---\nCreative brief:\n{brief}"


def _invoke_interleaved(prompt: str) -> list[dict]:
    """Synchronous Gemini interleaved call — run via asyncio.to_thread.

    Returns a list of ordered content blocks:
      {"type": "text",  "content": "..."}
      {"type": "image", "content": "<base64-string>", "mime_type": "image/png"}
    """
    from google.genai import types

    from services.gemini.client import get_client
    client = get_client(force_api_key=True)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    blocks: list[dict] = []
    if not response.candidates or not response.candidates[0].content:
        raise RuntimeError(
            "Image generation returned no content — the topic may be blocked by safety filters. "
            "Try rephrasing the brief (e.g. avoid trademarked character names)."
        )
    for part in response.candidates[0].content.parts:
        text = getattr(part, "text", None)
        blob = getattr(part, "inline_data", None)

        if text and text.strip():
            blocks.append({"type": "text", "content": text.strip()})
        elif blob is not None:
            raw = getattr(blob, "data", None)
            mime = getattr(blob, "mime_type", "image/png")
            if raw:
                if isinstance(raw, bytes):
                    raw = base64.b64encode(raw).decode()
                blocks.append({"type": "image", "content": raw, "mime_type": mime})

    return blocks


def _invoke_interleaved_with_image(prompt: str, reference_image_b64: str | None = None) -> list[dict]:
    """Like `_invoke_interleaved` but accepts an optional reference image as input."""
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    parts: list = []
    if reference_image_b64:
        image_bytes = base64.b64decode(reference_image_b64)
        parts.append(types.Part(inline_data=types.Blob(data=image_bytes, mime_type="image/jpeg")))
    parts.append(types.Part(text=prompt))

    response = client.models.generate_content(
        model=MODEL,
        contents=types.Content(parts=parts),
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )

    blocks: list[dict] = []
    if not response.candidates or not response.candidates[0].content:
        raise RuntimeError(
            "Image generation returned no content — the topic may be blocked by safety filters. "
            "Try rephrasing the brief (e.g. avoid trademarked character names)."
        )
    for part in response.candidates[0].content.parts:
        text = getattr(part, "text", None)
        blob = getattr(part, "inline_data", None)
        if text and text.strip():
            blocks.append({"type": "text", "content": text.strip()})
        elif blob is not None:
            raw = getattr(blob, "data", None)
            mime = getattr(blob, "mime_type", "image/jpeg")
            if raw:
                if isinstance(raw, bytes):
                    raw = base64.b64encode(raw).decode()
                blocks.append({"type": "image", "content": raw, "mime_type": mime})
    return blocks


_THUMBNAIL_PROMPT_TEMPLATE = (
    "You are a viral YouTube thumbnail designer. "
    "Generate {count} DIFFERENT ultra-clickbait thumbnail images for a short-form video titled: \"{hook}\".\n"
    "{brief_clause}"
    "{art_clause}"
    "\nRequirements for EACH thumbnail:\n"
    "- Bold, high-contrast colours that pop on mobile screens\n"
    "- Expressive faces or dramatic, eye-catching visuals that trigger curiosity\n"
    "- Optional short bold text overlay (3–5 words max) that teases without spoiling\n"
    "- Portrait 9:16 vertical composition — optimised for YouTube Shorts, Instagram Reels, and TikTok\n"
    "- Each option must look DISTINCTLY DIFFERENT (vary style, colour palette, and composition)\n\n"
    "Generate exactly {count} complete thumbnail images back-to-back. No commentary, just images."
)


async def generate_thumbnail_options(
    hook: str,
    brief: str = "",
    reference_image_b64: str | None = None,
    art_style: str = "realism",
    count: int = 2,
) -> list[dict]:
    """Generate N clickbait thumbnail images for a short-form video.

    Args:
        hook:                 The video's hook/title text (used in the thumbnail).
        brief:                Optional extra context about the video content.
        reference_image_b64:  Optional JPEG b64 of the current screen to reference.
        art_style:            Art style for generation.
        count:                How many thumbnail options to generate (default 2).

    Returns:
        List of {"image_b64": str, "mime_type": str} dicts (up to `count` items).
    """
    count = min(3, max(1, count))
    brief_clause = f"Video context: {brief}\n" if brief else ""
    art_clause = f"Art style: {art_style}. Apply this style consistently.\n" if art_style else ""
    prompt = _THUMBNAIL_PROMPT_TEMPLATE.format(
        count=count,
        hook=hook,
        brief_clause=brief_clause,
        art_clause=art_clause,
    )

    logger.info("Thumbnail generation starting (hook=%.40s, count=%d)", hook, count)
    blocks = await asyncio.to_thread(_invoke_interleaved_with_image, prompt, reference_image_b64)
    image_blocks = [
        {"image_b64": b["content"], "mime_type": b.get("mime_type", "image/jpeg")}
        for b in blocks if b.get("type") == "image"
    ]
    result = image_blocks[:count]
    logger.info("Thumbnail generation done — %d images returned", len(result))
    return result


async def generate_creative_package(
    brief: str,
    mode: str = "social_content",
    art_style: str | None = None,
    include_narration: bool = False,
    voice_id: str = "Aoede",
    reference_image_b64: str | None = None,
) -> tuple[list[dict], str | None]:
    """Generate a rich mixed-media creative package using Gemini interleaved output.

    Gemini's Creative Director thinks and creates like a human creative director,
    seamlessly weaving together text and images in a single, fluid output stream —
    all from one API call.

    Args:
        brief:              The creative brief — topic, audience, goals, tone.
        mode:               Creative mode: storybook | marketing | educational | social_content.
        art_style:          Optional art style hint applied to all generated images.
        include_narration:  If True, generate a TTS WAV narration of all text blocks.
        voice_id:           Gemini TTS voice name (e.g. Aoede, Charon, Fenrir).

    Returns:
        (blocks, narration_b64) — blocks is an ordered list of content dicts;
        narration_b64 is a base64-encoded WAV string or None.
    """
    prompt = _build_prompt(mode, brief, art_style)

    logger.info("Creative Director starting (mode=%s, art_style=%s, has_ref=%s)", mode, art_style, bool(reference_image_b64))
    if reference_image_b64:
        blocks = await asyncio.to_thread(_invoke_interleaved_with_image, prompt, reference_image_b64)
    else:
        blocks = await asyncio.to_thread(_invoke_interleaved, prompt)

    n_text = sum(1 for b in blocks if b["type"] == "text")
    n_img = sum(1 for b in blocks if b["type"] == "image")
    logger.info(
        "Creative Director done — %d blocks (%d text, %d images)",
        len(blocks), n_text, n_img,
    )

    narration_b64: str | None = None
    if include_narration and n_text > 0:
        from services.gemini import tts as gemini_tts
        full_text = " ".join(b["content"] for b in blocks if b["type"] == "text")
        try:
            wav_path = await gemini_tts.generate_voiceover(full_text, voice_id)
            with open(wav_path, "rb") as f:
                narration_b64 = base64.b64encode(f.read()).decode()
            logger.info("Narration generated (%d chars → WAV)", len(full_text))
        except Exception:
            logger.exception("Narration TTS failed — returning blocks without audio")

    return blocks, narration_b64
