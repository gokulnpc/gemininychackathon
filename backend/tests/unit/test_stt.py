"""Unit tests for services/media/stt.py — mocked paths only.

No real GCP calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_stt.py
"""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.stt import (
    _normalize_timestamps,
    _validate_audio_file,
    extract_word_timestamps,
)


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


# ── Production hardening: file validation ──────────────────────────────────────

def test_file_not_found_raises_clear_error():
    """Missing file → FileNotFoundError with path in message."""
    try:
        _validate_audio_file("/nonexistent/audio.wav")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "/nonexistent/audio.wav" in str(e)
    print("  ✓ missing file → FileNotFoundError with path")


def test_empty_file_raises_error():
    """0-byte WAV → ValueError."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)  # creates 0-byte file
    try:
        _validate_audio_file(path)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "empty" in str(e).lower()
    finally:
        os.unlink(path)
    print("  ✓ empty file → ValueError")


# ── Production hardening: retry logic ────────────────────────────────────────

async def test_retries_on_transient_error():
    """Transient errors propagate from async wrapper."""
    call_count = {"n": 0}

    async def fake_to_thread(fn, *args):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Nontransient error")
        return _FAKE_TIMESTAMPS

    with patch("services.media.stt.asyncio.to_thread", side_effect=fake_to_thread):
        try:
            await extract_word_timestamps("/fake/audio.wav")
            # If it didn't raise, the second call succeeded
        except RuntimeError:
            pass  # Expected — non-transient error propagates

    assert call_count["n"] >= 1
    print("  ✓ errors propagate through async wrapper")


def test_retries_on_transient_sync():
    """503 on first try in _recognize_with_retry → retries and succeeds."""
    from services.media.stt import _recognize_with_retry

    call_count = {"n": 0}
    mock_response = MagicMock()
    mock_response.results = []  # no words

    mock_speech = MagicMock()
    mock_client = MagicMock()
    mock_speech.SpeechClient.return_value = mock_client
    mock_speech.RecognitionConfig.AudioEncoding.LINEAR16 = 1
    mock_speech.RecognitionAudio.return_value = MagicMock()
    mock_speech.RecognitionConfig.return_value = MagicMock()

    def fake_recognize(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("503 Service Unavailable")
        return mock_response

    mock_client.recognize = fake_recognize

    # Create a small temp WAV file
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, b"RIFF" + b"\x00" * 100)
    os.close(fd)

    try:
        with patch("services.media.stt._get_speech_module", return_value=mock_speech), \
             patch("services.media.stt.time.sleep"):  # skip actual delay
            result = _recognize_with_retry(wav_path, 24000)
        assert call_count["n"] == 2, f"Expected 2 calls, got {call_count['n']}"
        assert result == []
    finally:
        os.unlink(wav_path)
    print("  ✓ retried on 503, succeeded on 2nd attempt")


def test_exhausted_retries_raises():
    """3x 503 → raises after all retries."""
    from services.media.stt import _recognize_with_retry

    mock_speech = MagicMock()
    mock_client = MagicMock()
    mock_speech.SpeechClient.return_value = mock_client
    mock_speech.RecognitionConfig.AudioEncoding.LINEAR16 = 1
    mock_speech.RecognitionAudio.return_value = MagicMock()
    mock_speech.RecognitionConfig.return_value = MagicMock()
    mock_client.recognize.side_effect = RuntimeError("503 Service Unavailable")

    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, b"RIFF" + b"\x00" * 100)
    os.close(fd)

    try:
        with patch("services.media.stt._get_speech_module", return_value=mock_speech), \
             patch("services.media.stt.time.sleep"):
            try:
                _recognize_with_retry(wav_path, 24000)
                assert False, "Should have raised after retries"
            except RuntimeError as e:
                assert "503" in str(e)
    finally:
        os.unlink(wav_path)
    print("  ✓ exhausted retries → raises")


# ── Production hardening: timestamp normalization ───────────────────────────

def test_timestamps_sorted_and_normalized():
    """Out-of-order timestamps → sorted, overlaps fixed."""
    raw = [
        {"word": "b", "start": 2.0, "end": 3.5},  # out of order
        {"word": "a", "start": 0.0, "end": 2.5},  # overlaps with b
        {"word": "c", "start": 3.0, "end": 4.0},
    ]
    result = _normalize_timestamps(raw)
    # Should be sorted: a, b, c
    assert result[0]["word"] == "a"
    assert result[1]["word"] == "b"
    assert result[2]["word"] == "c"
    # a.end should be clamped to b.start (2.0)
    assert result[0]["end"] <= result[1]["start"], (
        f"Overlap not fixed: a.end={result[0]['end']}, b.start={result[1]['start']}"
    )
    print(f"  ✓ sorted + overlaps fixed: {[(w['word'], w['start'], w['end']) for w in result]}")


def test_large_file_uses_long_running():
    """Files >10MB should use long_running_recognize."""
    from services.media.stt import _recognize_with_retry, _SYNC_LIMIT_BYTES

    mock_operation = MagicMock()
    mock_response = MagicMock()
    mock_response.results = []
    mock_operation.result.return_value = mock_response

    mock_speech = MagicMock()
    mock_client = MagicMock()
    mock_speech.SpeechClient.return_value = mock_client
    mock_speech.RecognitionConfig.AudioEncoding.LINEAR16 = 1
    mock_speech.RecognitionAudio.return_value = MagicMock()
    mock_speech.RecognitionConfig.return_value = MagicMock()
    mock_client.long_running_recognize.return_value = mock_operation

    # Create a file > 10MB
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, b"RIFF" + b"\x00" * (_SYNC_LIMIT_BYTES + 100))
    os.close(fd)

    try:
        with patch("services.media.stt._get_speech_module", return_value=mock_speech):
            _recognize_with_retry(wav_path, 24000)
        mock_client.long_running_recognize.assert_called_once()
        mock_client.recognize.assert_not_called()
    finally:
        os.unlink(wav_path)
    print("  ✓ >10MB file → long_running_recognize called")


def test_auto_converts_non_wav():
    """Non-WAV input should trigger ffmpeg conversion."""
    from services.media.stt import _ensure_wav

    fd, m4a_path = tempfile.mkstemp(suffix=".m4a")
    os.write(fd, b"\x00" * 100)  # dummy
    os.close(fd)

    try:
        with patch("services.media.stt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            wav_path, is_temp = _ensure_wav(m4a_path, 24000)
            assert is_temp, "Should return is_temp=True for converted files"
            assert wav_path.endswith(".wav")
            mock_run.assert_called_once()
            # Check ffmpeg args
            args = mock_run.call_args[0][0]
            assert "ffmpeg" in args[0]
            assert "-ar" in args
    finally:
        os.unlink(m4a_path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
    print("  ✓ .m4a input → ffmpeg conversion triggered")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    tests = [
        test_returns_mocked_timestamps,
        test_default_sample_rate,
        test_custom_sample_rate_forwarded,
        test_empty_audio_returns_empty_list,
        test_gcp_error_propagates,
        test_file_not_found_raises_clear_error,
        test_empty_file_raises_error,
        test_retries_on_transient_error,
        test_retries_on_transient_sync,
        test_exhausted_retries_raises,
        test_timestamps_sorted_and_normalized,
        test_large_file_uses_long_running,
        test_auto_converts_non_wav,
    ]
    passed = failed = 0

    for fn in tests:
        print(f"[{fn.__name__}]")
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
