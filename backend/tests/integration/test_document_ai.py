"""Integration test for services/content/document_ai.py — real Gemini API call.

Reads backend/input/GINGER-THE-GIRAFFE.pdf, base64-encodes it, and calls the
real extract_text_from_pdf via the Gemini multimodal path.

Requires:
  - GEMINI_API_KEY in .env

Usage:
    cd backend && .venv/bin/python tests/integration/test_document_ai.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.content.document_ai import extract_text_from_pdf

SAMPLE_PDF = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "input", "GINGER-THE-GIRAFFE.pdf")
)


async def test_real_pdf_extraction():
    """Real Gemini call — extracts text from GINGER-THE-GIRAFFE.pdf."""
    if not os.path.exists(SAMPLE_PDF):
        raise FileNotFoundError(f"Sample PDF not found: {SAMPLE_PDF}")

    print(f"  input: {SAMPLE_PDF} ({os.path.getsize(SAMPLE_PDF):,} bytes)")

    with open(SAMPLE_PDF, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode()

    result = await extract_text_from_pdf(pdf_base64)

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 10, f"Extracted text too short: {repr(result)}"
    assert any(
        word in result.lower() for word in ("ginger", "giraffe")
    ), f"Expected 'ginger' or 'giraffe' in extracted text. Got: {repr(result[:200])}"

    print(f"  ✓ {len(result)} chars extracted")
    print(f"\n  {'─'*40}")
    print(f"  First 300 chars:")
    print(f"  {result[:300]}")


async def main() -> None:
    passed = failed = 0
    print(f"[{test_real_pdf_extraction.__name__}]")
    try:
        await test_real_pdf_extraction()
        passed += 1
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
