"""Unit tests for services/content/document_ai.py — mocked paths only.

No real API calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_document_ai.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.content.document_ai import (
    _extract_with_document_ai,
    _extract_with_gemini,
    extract_text_from_pdf,
)

_FAKE_PDF_B64 = "AAAA"  # valid enough for mocked paths


def _settings(processor_id: str = "", project: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        document_ai_processor_id=processor_id,
        google_cloud_project=project,
        document_ai_location="us",
    )


# ── routing tests ─────────────────────────────────────────────────────────────

async def test_routes_to_gemini_when_no_processor_id():
    """No processor_id → Gemini path is taken."""
    called = {}

    async def fake_gemini(pdf_base64):
        called["gemini"] = True
        return "gemini text"

    with patch("config.get_settings", return_value=_settings()), \
         patch("services.content.document_ai._extract_with_gemini", side_effect=fake_gemini):
        result = await extract_text_from_pdf(_FAKE_PDF_B64)

    assert called.get("gemini"), "Expected Gemini path to be called"
    assert result == "gemini text"
    print("  ✓ no processor_id → Gemini path")


async def test_routes_to_document_ai_when_processor_id_set():
    """processor_id + project set → Document AI path is taken."""
    called = {}

    async def fake_docai(pdf_base64, settings):
        called["docai"] = True
        return "docai text"

    with patch("config.get_settings", return_value=_settings("proc-123", "my-project")), \
         patch("services.content.document_ai._extract_with_document_ai", side_effect=fake_docai):
        result = await extract_text_from_pdf(_FAKE_PDF_B64)

    assert called.get("docai"), "Expected Document AI path to be called"
    assert result == "docai text"
    print("  ✓ processor_id + project → Document AI path")


async def test_routes_to_gemini_when_only_processor_id_no_project():
    """processor_id set but project missing → falls back to Gemini."""
    called = {}

    async def fake_gemini(pdf_base64):
        called["gemini"] = True
        return "gemini fallback"

    with patch("config.get_settings", return_value=_settings("proc-123", "")), \
         patch("services.content.document_ai._extract_with_gemini", side_effect=fake_gemini):
        result = await extract_text_from_pdf(_FAKE_PDF_B64)

    assert called.get("gemini"), "Expected Gemini fallback when project missing"
    print("  ✓ processor_id without project → Gemini path")


# ── Gemini extraction tests ───────────────────────────────────────────────────

async def test_gemini_returns_extracted_text():
    """_extract_with_gemini returns string from asyncio.to_thread."""
    with patch("services.content.document_ai.asyncio.to_thread", new=AsyncMock(return_value="hello pdf")), \
         patch("services.content.document_ai.base64.b64decode", return_value=b"fakebytes"), \
         patch("services.gemini.client.get_client", return_value=MagicMock()):
        result = await _extract_with_gemini(_FAKE_PDF_B64)

    assert result == "hello pdf"
    print("  ✓ Gemini path returns extracted text")


async def test_gemini_empty_response_returns_empty_string():
    """Empty response from asyncio.to_thread → returns ''."""
    with patch("services.content.document_ai.asyncio.to_thread", new=AsyncMock(return_value="")), \
         patch("services.content.document_ai.base64.b64decode", return_value=b"fakebytes"), \
         patch("services.gemini.client.get_client", return_value=MagicMock()):
        result = await _extract_with_gemini(_FAKE_PDF_B64)

    assert result == ""
    print("  ✓ empty Gemini response → ''")


# ── Document AI ImportError fallback ─────────────────────────────────────────

async def test_document_ai_falls_back_to_gemini_on_import_error():
    """`google-cloud-documentai` not installed → falls back to Gemini."""
    called = {}

    async def fake_gemini(pdf_base64):
        called["gemini"] = True
        return "gemini fallback text"

    settings = _settings("proc-123", "my-project")

    import builtins
    real_import = builtins.__import__

    def import_raiser(name, *args, **kwargs):
        if name == "google.cloud.documentai_v1":
            raise ImportError("google-cloud-documentai not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=import_raiser), \
         patch("services.content.document_ai._extract_with_gemini", side_effect=fake_gemini):
        result = await _extract_with_document_ai(_FAKE_PDF_B64, settings)

    assert called.get("gemini"), "Expected Gemini fallback on ImportError"
    assert result == "gemini fallback text"
    print("  ✓ ImportError for google-cloud-documentai → Gemini fallback")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    tests = [
        test_routes_to_gemini_when_no_processor_id,
        test_routes_to_document_ai_when_processor_id_set,
        test_routes_to_gemini_when_only_processor_id_no_project,
        test_gemini_returns_extracted_text,
        test_gemini_empty_response_returns_empty_string,
        test_document_ai_falls_back_to_gemini_on_import_error,
    ]
    passed = failed = 0

    for fn in tests:
        print(f"[{fn.__name__}]")
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
