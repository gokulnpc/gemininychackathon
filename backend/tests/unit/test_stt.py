"""Unit tests for services/media/stt.py — mocked paths only.

No real GCP calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_stt.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.stt import extract_word_timestamps


_FAKE_TIMESTAMPS = [
    {"word": "hello", "start": 0.0, "end": 0.4},
    {"word": "world", "start": 0.5, "end": 0.9},
]


async def test_returns_mocked_timestamps():
    """extract_word_timestamps passes through whatever _invoke_stt returns."""
    with patch("services.media.stt.asyncio.to_thread", new=AsyncMock(return_value=_FAKE_TIMESTAMPS)):
        result = await extract_word_timestamps("/fake/audio.wav", sample_rate=24000)
    assert result == _FAKE_TIMESTAMPS, f"got: {result}"
    print("  ✓ returns word timestamps from underlying STT call")


async def test_default_sample_rate():
    """Default sample rate is 24000 (matches Gemini TTS output)."""
    captured = {}

    async def fake_to_thread(fn, wav_path, sample_rate):
        captured["sample_rate"] = sample_rate
        return _FAKE_TIMESTAMPS

    with patch("services.media.stt.asyncio.to_thread", side_effect=fake_to_thread):
        await extract_word_timestamps("/fake/audio.wav")

    assert captured["sample_rate"] == 24000, f"got: {captured['sample_rate']}"
    print("  ✓ default sample rate is 24000")


async def test_custom_sample_rate_forwarded():
    """Custom sample rate is forwarded to the underlying STT call."""
    captured = {}

    async def fake_to_thread(fn, wav_path, sample_rate):
        captured["sample_rate"] = sample_rate
        return []

    with patch("services.media.stt.asyncio.to_thread", side_effect=fake_to_thread):
        await extract_word_timestamps("/fake/audio.wav", sample_rate=16000)

    assert captured["sample_rate"] == 16000, f"got: {captured['sample_rate']}"
    print("  ✓ custom sample_rate=16000 forwarded correctly")


async def test_empty_audio_returns_empty_list():
    """Empty STT result → empty list returned (not an error)."""
    with patch("services.media.stt.asyncio.to_thread", new=AsyncMock(return_value=[])):
        result = await extract_word_timestamps("/fake/silent.wav")
    assert result == [], f"got: {result}"
    print("  ✓ empty STT result → []")


async def test_gcp_error_propagates():
    """GCP errors propagate to the caller (no silent swallowing)."""
    async def fake_to_thread(fn, *args):
        raise RuntimeError("GCP Speech quota exceeded")

    with patch("services.media.stt.asyncio.to_thread", side_effect=fake_to_thread):
        try:
            await extract_word_timestamps("/fake/audio.wav")
            assert False, "Expected RuntimeError to propagate"
        except RuntimeError as e:
            assert "quota exceeded" in str(e)
    print("  ✓ GCP error propagates to caller")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    tests = [
        test_returns_mocked_timestamps,
        test_default_sample_rate,
        test_custom_sample_rate_forwarded,
        test_empty_audio_returns_empty_list,
        test_gcp_error_propagates,
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
