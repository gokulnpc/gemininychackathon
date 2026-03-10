"""Integration test for describe_reference_subject — real Gemini Vision API call.

Requires: GEMINI_API_KEY in .env (or Vertex AI ADC on GCP).
Uses: backend/input/gokul.jpeg as the sample reference image.

Usage:
    cd backend && .venv/bin/python tests/integration/test_describe_subject.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.image import describe_reference_subject

SAMPLE_IMAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "input", "gokul.jpeg")
)


async def test_real_image():
    """Real Gemini Vision call: reference image → non-empty descriptive sentence."""
    print(f"  image: {SAMPLE_IMAGE}")
    if not os.path.exists(SAMPLE_IMAGE):
        raise FileNotFoundError(f"Sample image not found: {SAMPLE_IMAGE}")

    result = await describe_reference_subject(SAMPLE_IMAGE)

    assert result, f"Expected non-empty description, got: {repr(result)}"
    assert len(result) > 10, f"Description too short: {repr(result)}"
    print(f"  ✓ inferred description: {result}")


async def main() -> None:
    passed = failed = 0
    print(f"[{test_real_image.__name__}]")
    try:
        await test_real_image()
        passed += 1
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
