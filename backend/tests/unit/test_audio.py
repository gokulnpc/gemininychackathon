"""Unit tests for services/gemini/audio.py — mocked paths only.

No real Gemini API calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_audio.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.audio import (
    ALLOWED_TONES,
    _extract_json,
    _normalize_tone,
    _resolve_mime_type,
    _validate_audio_input,
    transcribe_with_tone,
)


# ── Fake data ─────────────────────────────────────────────────────────────────

_VALID_AUDIO = base64.b64encode(b"\x00" * 100).decode()  # 100-byte dummy audio
_VALID_JSON_RESPONSE = '{"transcript": "hello world", "detected_tone": "excited", "language": "en-US"}'


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Gemini response with the given text."""
    resp = MagicMock()
    resp.text = text
    return resp


# ── Input validation ─────────────────────────────────────────────────────────

def test_empty_audio_raises():
    """Empty base64 → ValueError."""
    try:
        _validate_audio_input("")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "empty" in str(e).lower()
    try:
        _validate_audio_input("   ")
        assert False, "Should have raised ValueError for whitespace"
    except ValueError:
        pass
    print("  ✓ empty audio → ValueError")


def test_invalid_base64_raises():
    """Corrupt base64 → ValueError."""
    try:
        _validate_audio_input("!!!not-valid-base64!!!")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid" in str(e).lower() or "base64" in str(e).lower()
    print("  ✓ invalid base64 → ValueError")


def test_oversized_audio_raises():
    """Audio > 20MB → ValueError."""
    from services.gemini.audio import MAX_AUDIO_BYTES
    big_audio = base64.b64encode(b"\x00" * (MAX_AUDIO_BYTES + 1)).decode()
    try:
        _validate_audio_input(big_audio)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "too large" in str(e).lower()
    print("  ✓ oversized audio → ValueError")


# ── Format resolution ────────────────────────────────────────────────────────

def test_known_formats_correct_mime():
    """Known formats → correct MIME types."""
    assert _resolve_mime_type("webm") == "audio/webm"
    assert _resolve_mime_type("mp3") == "audio/mp3"
    assert _resolve_mime_type("wav") == "audio/wav"
    assert _resolve_mime_type("m4a") == "audio/mp4"
    assert _resolve_mime_type("ogg") == "audio/ogg"
    assert _resolve_mime_type("flac") == "audio/flac"
    # Case insensitive
    assert _resolve_mime_type("WAV") == "audio/wav"
    # With leading dot
    assert _resolve_mime_type(".mp3") == "audio/mp3"
    print("  ✓ known formats → correct MIME types")


def test_unknown_format_logs_warning():
    """Unknown format → logs warning, defaults to audio/webm."""
    import logging
    with patch.object(logging.getLogger("services.gemini.audio"), "warning") as mock_warn:
        result = _resolve_mime_type("xyz123")
    assert result == "audio/webm"
    mock_warn.assert_called_once()
    print("  ✓ unknown format → warning + default MIME")


# ── JSON extraction ──────────────────────────────────────────────────────────

def test_valid_json_response_parsed():
    """Clean JSON response → correct extraction."""
    result = _extract_json(_VALID_JSON_RESPONSE)
    assert result is not None
    assert result["transcript"] == "hello world"
    assert result["detected_tone"] == "excited"
    assert result["language"] == "en-US"
    print("  ✓ clean JSON → parsed correctly")


def test_json_in_markdown_fences_parsed():
    """JSON wrapped in markdown fences → correctly extracted."""
    text = '```json\n{"transcript": "fenced text", "detected_tone": "calm", "language": "fr-FR"}\n```'
    result = _extract_json(text)
    assert result is not None
    assert result["transcript"] == "fenced text"
    assert result["detected_tone"] == "calm"
    print("  ✓ markdown-fenced JSON → parsed correctly")


def test_invalid_json_returns_none():
    """Garbled response → None."""
    result = _extract_json("This is just plain text with no JSON at all")
    assert result is None
    print("  ✓ garbled text → None")


# ── Tone normalization ───────────────────────────────────────────────────────

def test_tone_normalized_to_enum():
    """Unknown tone → 'conversational'."""
    assert _normalize_tone("weird_tone") == "conversational"
    assert _normalize_tone("UNKNOWN") == "conversational"
    assert _normalize_tone(None) == "conversational"
    assert _normalize_tone("") == "conversational"
    print("  ✓ unknown tone → 'conversational'")


def test_valid_tone_preserved():
    """Valid tones → preserved (case-insensitive)."""
    for tone in ALLOWED_TONES:
        assert _normalize_tone(tone) == tone
        assert _normalize_tone(tone.upper()) == tone
    print(f"  ✓ all {len(ALLOWED_TONES)} valid tones preserved")


# ── transcribe_with_tone (mocked) ────────────────────────────────────────────

async def test_full_flow_success():
    """Full flow: valid audio → transcript + tone + language."""
    mock_resp = _make_mock_response(_VALID_JSON_RESPONSE)

    with patch("services.gemini.audio.asyncio.to_thread", new=AsyncMock(return_value=mock_resp)), \
         patch("services.gemini.client.get_client"):
        result = await transcribe_with_tone(_VALID_AUDIO, "webm")

    assert result["transcript"] == "hello world"
    assert result["detected_tone"] == "excited"
    assert result["language"] == "en-US"
    print("  ✓ full flow → correct transcript/tone/language")


async def test_retry_on_transient_error():
    """429 on first try → retries and succeeds."""
    call_count = {"n": 0}
    mock_resp = _make_mock_response(_VALID_JSON_RESPONSE)

    async def fake_to_thread(fn, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("429 Resource exhausted")
        return mock_resp

    with patch("services.gemini.audio.asyncio.to_thread", side_effect=fake_to_thread), \
         patch("services.gemini.client.get_client"), \
         patch("services.gemini.audio.asyncio.sleep", new=AsyncMock()):
        result = await transcribe_with_tone(_VALID_AUDIO, "webm")

    assert call_count["n"] == 2
    assert result["transcript"] == "hello world"
    print("  ✓ 429 → retried and succeeded")


async def test_non_transient_error_raises():
    """400 Bad Request → raises immediately (no retry)."""
    async def fake_to_thread(fn, *args, **kwargs):
        raise RuntimeError("400 Bad Request: invalid audio")

    with patch("services.gemini.audio.asyncio.to_thread", side_effect=fake_to_thread), \
         patch("services.gemini.client.get_client"):
        try:
            await transcribe_with_tone(_VALID_AUDIO, "webm")
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "400" in str(e)
    print("  ✓ 400 → raises immediately")


async def test_empty_transcript_handled():
    """Empty transcript in JSON → empty string (not None)."""
    mock_resp = _make_mock_response('{"transcript": "", "detected_tone": "calm", "language": "en-US"}')

    with patch("services.gemini.audio.asyncio.to_thread", new=AsyncMock(return_value=mock_resp)), \
         patch("services.gemini.client.get_client"):
        result = await transcribe_with_tone(_VALID_AUDIO)

    assert result["transcript"] == ""
    assert result["detected_tone"] == "calm"
    print("  ✓ empty transcript → '' (not None)")


async def test_missing_fields_use_defaults():
    """Partial JSON → defaults for missing fields."""
    mock_resp = _make_mock_response('{"transcript": "just this"}')

    with patch("services.gemini.audio.asyncio.to_thread", new=AsyncMock(return_value=mock_resp)), \
         patch("services.gemini.client.get_client"):
        result = await transcribe_with_tone(_VALID_AUDIO)

    assert result["transcript"] == "just this"
    assert result["detected_tone"] == "conversational"  # default
    assert result["language"] == "en-US"  # default
    print("  ✓ missing fields → defaults applied")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_empty_audio_raises,
        test_invalid_base64_raises,
        test_oversized_audio_raises,
        test_known_formats_correct_mime,
        test_unknown_format_logs_warning,
        test_valid_json_response_parsed,
        test_json_in_markdown_fences_parsed,
        test_invalid_json_returns_none,
        test_tone_normalized_to_enum,
        test_valid_tone_preserved,
    ]
    async_tests = [
        test_full_flow_success,
        test_retry_on_transient_error,
        test_non_transient_error_raises,
        test_empty_transcript_handled,
        test_missing_fields_use_defaults,
    ]

    passed = failed = 0

    print("\n── Input validation + helpers ──")
    for fn in sync_tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── transcribe_with_tone (mocked) ──")
    for fn in async_tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
