"""Integration test for describe_reference_subject (services/gemini/image.py).

Makes a real Gemini Vision API call using the sample image at backend/input/gokul.jpeg.
Requires GEMINI_API_KEY (or Vertex AI ADC) to be configured in .env.

Usage:
    cd backend
    python tests/test_describe_subject.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure backend/ is on the path regardless of where this script is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini.image import describe_reference_subject

SAMPLE_IMAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "input", "gokul.jpeg")
)


# ── Test cases ────────────────────────────────────────────────────────────────

async def test_real_image():
    """Happy path: real image → non-empty descriptive sentence from Gemini Vision."""
    print(f"  image: {SAMPLE_IMAGE}")
    if not os.path.exists(SAMPLE_IMAGE):
        raise FileNotFoundError(f"Sample image not found: {SAMPLE_IMAGE}")

    result = await describe_reference_subject(SAMPLE_IMAGE)

    assert result, f"Expected non-empty description, got: {repr(result)}"
    assert len(result) > 10, f"Description too short: {repr(result)}"
    print(f"  ✓ inferred description: {result}")


async def test_missing_file():
    """Error path: non-existent file → returns '' without raising."""
    result = await describe_reference_subject("/tmp/no_such_file_xyzzy.jpg")
    assert result == "", f"Expected '' for missing file, got: {repr(result)}"
    print("  ✓ missing file → ''")


async def test_empty_path():
    """Error path: empty string → returns '' without raising."""
    result = await describe_reference_subject("")
    assert result == "", f"Expected '' for empty path, got: {repr(result)}"
    print("  ✓ empty path → ''")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    tests = [test_real_image, test_missing_file, test_empty_path]
    passed = failed = 0

    for fn in tests:
        print(f"\n[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
