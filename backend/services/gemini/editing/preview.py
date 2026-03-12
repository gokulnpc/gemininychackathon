"""Fast single-image preview helpers for Scout edit flows."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable

from services.gemini.models import MODELS

logger = logging.getLogger(__name__)


def _quick_preview_prompt(brief: str, art_style: str | None) -> str:
    style_clause = f"Art style: {art_style}. " if art_style else ""
    return (
        f"{style_clause}Generate ONE striking vertical image (9:16 portrait) "
        f"that visually represents this concept: {brief}. "
        "Output ONLY the image — no text."
    )


def _invoke_quick_preview(prompt: str) -> list[dict]:
    """Synchronous single-image Gemini call — run via asyncio.to_thread."""
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    response = client.models.generate_content(
        model=MODELS.image_generation,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    blocks: list[dict] = []
    for part in response.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob is None:
            continue
        raw = getattr(blob, "data", None)
        mime = getattr(blob, "mime_type", "image/png")
        if not raw:
            continue
        if isinstance(raw, bytes):
            raw = base64.b64encode(raw).decode()
        blocks.append({"type": "image", "content": raw, "mime_type": mime})
    return blocks


async def _generate_quick_preview(
    brief: str,
    art_style: str | None = None,
    on_event: Callable[[dict], Awaitable[object]] | None = None,
) -> dict:
    """Generate ONE preview image and stream it to the browser via on_event."""
    try:
        prompt = _quick_preview_prompt(brief, art_style)
        logger.info("Quick style preview: art_style=%s", art_style)
        blocks = await asyncio.to_thread(_invoke_quick_preview, prompt)

        if on_event and blocks:
            try:
                await on_event({
                    "type": "creative_block",
                    "block": blocks[0],
                    "block_index": 0,
                    "total_blocks": 1,
                })
            except Exception:
                pass

        logger.info("Quick style preview done — %d image(s)", len(blocks))
        return {"status": "completed", "total_images": len(blocks)}
    except Exception as exc:
        logger.warning("generate_style_preview failed: %s", exc)
        return {"error": str(exc)}
