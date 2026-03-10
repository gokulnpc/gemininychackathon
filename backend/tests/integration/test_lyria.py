"""Integration test for generate_music — real Vertex AI Lyria call.

Requires: GCP credentials (ADC) and GOOGLE_CLOUD_PROJECT in .env.
Generates an actual ~32s WAV file via Lyria 002.

Usage:
    cd backend && .venv/bin/python tests/integration/test_lyria.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.lyria import generate_music


async def test_real_lyria():
    """Real Vertex AI call — generates an actual WAV file (~32s, ~6MB)."""
    from config import get_settings
    settings = get_settings()

    if not settings.google_cloud_project:
        print("  ⚠ SKIP: GOOGLE_CLOUD_PROJECT not set")
        return

    location = getattr(settings, "vertex_ai_location", "us-central1")
    path = await generate_music(
        music_preset="lyria",
        project_id=settings.google_cloud_project,
        location=location,
        style="modern_energetic",
        niche="fitness",
    )

    assert os.path.exists(path), f"WAV not written: {path}"
    size = os.path.getsize(path)
    assert size > 10_000, f"WAV too small ({size} bytes) — likely empty"
    print(f"  ✓ WAV generated → {path} ({size:,} bytes)")
    os.unlink(path)


async def main() -> None:
    passed = failed = 0
    print(f"[{test_real_lyria.__name__}]")
    try:
        await test_real_lyria()
        passed += 1
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
