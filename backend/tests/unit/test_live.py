"""Unit tests for services/gemini/live.py wrapper — mocked paths only.

No real Gemini API calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_live.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.live import transcribe_base64_audio_live, MAX_AUDIO_BYTES

# ── Test Data ──────────────────────────────────────────────────────────────────

_VALID_RAW = b"fake audio content"
_VALID_AUDIO = base64.b64encode(_VALID_RAW).decode()

# ── Input validation + helpers ─────────────────────────────────────────────────

async def test_empty_audio_raises():
    """Empty base64 strings should be rejected before parsing."""
    try:
        await transcribe_base64_audio_live("")
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "empty" in str(e).lower()
        
    try:
        await transcribe_base64_audio_live("   \n")
        assert False, "Should raise for whitespace"
    except ValueError:
        pass
    print("  ✓ empty audio → ValueError")


async def test_invalid_base64_raises():
    """Corrupt base64 should be rejected immediately."""
    try:
        await transcribe_base64_audio_live("not_base64_!")
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "invalid" in str(e).lower()
    print("  ✓ corrupt base64 → ValueError")


async def test_oversized_audio_raises():
    """Audio exceeding 20MB after decoding should be rejected."""
    oversized = b"a" * (MAX_AUDIO_BYTES + 1)
    b64_str = base64.b64encode(oversized).decode()
    
    try:
        await transcribe_base64_audio_live(b64_str)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "too large" in str(e).lower()
    print("  ✓ >20MB audio → ValueError")


async def test_tone_normalized_to_enum():
    """If Gemini returns a weird tone, it should snap to 'conversational'."""
    with patch("services.gemini.live.tempfile.mkstemp", return_value=(1, "/tmp/fake")), \
         patch("services.gemini.live.os.write"), \
         patch("services.gemini.live.os.close"), \
         patch("services.media.ffmpeg._run_ffmpeg"), \
         patch("services.gemini.live.os.path.exists", return_value=True), \
         patch("services.gemini.live.os.unlink"), \
         patch("services.gemini.live.transcribe_live", new=AsyncMock(return_value={
             "transcript": "hello",
             "detected_tone": "super_weird_alien_tone",
             "language": "en-US"
         })):
        result = await transcribe_base64_audio_live(_VALID_AUDIO)
        
    assert result["detected_tone"] == "conversational"
    print("  ✓ unknown tone → 'conversational'")


async def test_valid_tone_preserved():
    """A valid tone from Gemini should be preserved exactly."""
    valid_tones = {"excited", "calm", "urgent", "conversational", "authoritative", "storytelling", "dramatic"}
    
    for tone in valid_tones:
        with patch("services.gemini.live.tempfile.mkstemp", return_value=(1, "/tmp/fake")), \
             patch("services.gemini.live.os.write"), \
             patch("services.gemini.live.os.close"), \
             patch("services.media.ffmpeg._run_ffmpeg"), \
             patch("services.gemini.live.os.path.exists", return_value=True), \
             patch("services.gemini.live.os.unlink"), \
             patch("services.gemini.live.transcribe_live", new=AsyncMock(return_value={
                 "transcript": "test",
                 "detected_tone": tone,
                 "language": "en-US"
             })):
            result = await transcribe_base64_audio_live(_VALID_AUDIO)
            
        assert result["detected_tone"] == tone
    print("  ✓ valid tones → preserved exactly")


async def test_full_flow_success():
    """Mock out ffmpeg and transcribe_live to ensure the wrapper stitches them right."""
    with patch("services.gemini.live.tempfile.mkstemp", return_value=(1, "/tmp/fake")), \
         patch("services.gemini.live.os.write"), \
         patch("services.gemini.live.os.close"), \
         patch("services.media.ffmpeg._run_ffmpeg") as mock_ffmpeg, \
         patch("services.gemini.live.os.path.exists", return_value=True), \
         patch("services.gemini.live.os.unlink") as mock_unlink, \
         patch("services.gemini.live.transcribe_live", new=AsyncMock(return_value={
             "transcript": "this is a test",
             "detected_tone": "excited",
             "language": "en-US"
         })) as mock_transcribe:
        
        result = await transcribe_base64_audio_live(_VALID_AUDIO, "webm")
        
    assert result["transcript"] == "this is a test"
    assert result["detected_tone"] == "excited"
    
    mock_ffmpeg.assert_called_once()
    assert "-f" in mock_ffmpeg.call_args[0][0]
    assert "s16le" in mock_ffmpeg.call_args[0][0]
    assert "-ar" in mock_ffmpeg.call_args[0][0]
    assert "16000" in mock_ffmpeg.call_args[0][0]
    
    mock_transcribe.assert_called_once()
    assert mock_unlink.call_count == 2
    print("  ✓ full flow successfully orchestrates ffmpeg & transcribe_live")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    async_tests = [
        test_empty_audio_raises,
        test_invalid_base64_raises,
        test_oversized_audio_raises,
        test_tone_normalized_to_enum,
        test_valid_tone_preserved,
        test_full_flow_success,
    ]

    passed = failed = 0

    print("\n── transcribe_base64_audio_live Wrapper tests ──")
    for fn in async_tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*50}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    asyncio.run(main())
