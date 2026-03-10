"""Gemini Interleaved — Creative Director agent with mixed text+image output.

Uses Gemini's native interleaved output capability to generate rich, mixed-media
content in a single fluid API call. The model weaves together narrative text and
generated images based on the creative mode selected.

Supported modes:
  storybook        — alternating story paragraphs + inline illustrations
  marketing        — headline + hero image + body copy + CTA visual + hashtags
  educational      — narration sections + concept/diagram images
  social_content   — caption + post image + hashtag cloud

Model: gemini-2.0-flash-preview-image-generation
  response_modalities=["TEXT", "IMAGE"] enables native interleaved output.
  A single prompt yields alternating text blocks and generated images.
"""

from __future__ import annotations

import asyncio
import base64
import logging

logger = logging.getLogger(__name__)

MODEL = "gemini-2.0-flash-preview-image-generation"

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
    return f"{system}{style_clause}\n\n---\nCreative brief:\n{brief}"


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


async def generate_creative_package(
    brief: str,
    mode: str = "social_content",
    art_style: str | None = None,
    include_narration: bool = False,
    voice_id: str = "Aoede",
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

    logger.info("Creative Director starting (mode=%s, art_style=%s)", mode, art_style)
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
