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


# ── 3-option multi-preview ─────────────────────────────────────────────────────

_STYLE_TRIADS: dict[str, list[tuple[str, str]]] = {
    "horror": [("Creepy comic", "creepy_comic"), ("Dark realism", "realism"), ("Gothic painting", "painting")],
    "upbeat": [("Vibrant comic", "comic"), ("Bright polaroid", "polaroid"), ("Disney pop", "disney")],
    "default": [("Cinematic realism", "realism"), ("Ghibli illustration", "ghibli"), ("Comic style", "comic")],
}


def _pick_style_triad(brief: str) -> list[tuple[str, str]]:
    """Pick a 3-way style set based on brief keywords."""
    b = brief.lower()
    if any(w in b for w in ("horror", "scary", "dark", "creepy", "thriller")):
        return _STYLE_TRIADS["horror"]
    if any(w in b for w in ("happy", "fun", "upbeat", "bright", "comedy")):
        return _STYLE_TRIADS["upbeat"]
    return _STYLE_TRIADS["default"]


async def _generate_multi_preview(
    brief: str,
    art_style: str | None = None,
    on_event: Callable[[dict], Awaitable[object]] | None = None,
    count: int = 3,
) -> dict:
    """Generate N preview images sequentially as structured option events.

    Emits: creative_preview_start → creative_preview_option (×count) → creative_preview_complete
    """
    import uuid as _uuid
    preview_id = _uuid.uuid4().hex[:12]
    styles: list[tuple[str, str]] = (
        _pick_style_triad(brief)
        if not art_style
        else [(art_style.replace("_", " ").title(), art_style)] * count
    )

    if on_event:
        await on_event({"type": "creative_preview_start", "preview_id": preview_id, "count": count})

    total_images = 0
    for i, (title, style) in enumerate(styles[:count]):
        try:
            prompt = _quick_preview_prompt(brief, style)
            blocks = await asyncio.to_thread(_invoke_quick_preview, prompt)
            if blocks and on_event:
                await on_event({
                    "type": "creative_preview_option",
                    "preview_id": preview_id,
                    "option_id": f"{preview_id}-{i}",
                    "index": i,
                    "total": count,
                    "title": title,
                    "style": style,
                    "image": blocks[0],
                })
                total_images += 1
        except Exception as exc:
            logger.warning("preview option %d failed: %s", i, exc)

    if on_event:
        await on_event({"type": "creative_preview_complete", "preview_id": preview_id, "total_images": total_images})

    return {"status": "completed", "preview_id": preview_id, "total_images": total_images}
