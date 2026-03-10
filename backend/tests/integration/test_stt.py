"""Integration test for services/media/stt.py — real GCP Speech-to-Text call.

Converts backend/input/weather_caudio.m4a → LINEAR16 mono WAV using ffmpeg,
then runs the actual GCP STT service to extract word-level timestamps.

Requires:
  - GCP credentials (ADC): gcloud auth application-default login
  - speech.googleapis.com enabled on your project
  - ffmpeg installed and on PATH

Usage:
    cd backend && .venv/bin/python tests/integration/test_stt.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.stt import extract_word_timestamps

SAMPLE_M4A = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "input", "weather_caudio.m4a")
)


def _m4a_to_wav(m4a_path: str) -> str:
    """Convert m4a → LINEAR16 mono 24kHz WAV using ffmpeg. Returns temp WAV path."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="stt_test_")
    os.close(fd)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", m4a_path,
            "-ar", "24000",   # 24kHz — matches Gemini TTS default
            "-ac", "1",       # mono
            "-c:a", "pcm_s16le",  # LINEAR16
            wav_path,
        ],
        check=True,
        capture_output=True,
    )
    return wav_path


async def test_real_stt():
    """Real GCP STT call — extracts word timestamps from weather_caudio.m4a."""
    if not os.path.exists(SAMPLE_M4A):
        raise FileNotFoundError(f"Sample audio not found: {SAMPLE_M4A}")

    print(f"  input: {SAMPLE_M4A}")

    # Convert to WAV
    wav_path = _m4a_to_wav(SAMPLE_M4A)
    print(f"  wav:   {wav_path} ({os.path.getsize(wav_path):,} bytes)")

    try:
        timestamps = await extract_word_timestamps(wav_path, sample_rate=24000)
    finally:
        os.unlink(wav_path)

    assert isinstance(timestamps, list), f"Expected list, got {type(timestamps)}"
    assert len(timestamps) > 0, "Expected at least one word timestamp — got empty list"

    # Validate shape of each entry
    for entry in timestamps:
        assert "word" in entry and isinstance(entry["word"], str)
        assert "start" in entry and isinstance(entry["start"], float)
        assert "end" in entry and isinstance(entry["end"], float)
        assert entry["end"] >= entry["start"], f"end < start: {entry}"

    duration = timestamps[-1]["end"] - timestamps[0]["start"]
    print(f"  ✓ {len(timestamps)} words extracted over {duration:.1f}s\n")
    print(f"  {'WORD':<20} {'START':>7}  {'END':>7}")
    print(f"  {'─'*20} {'─'*7}  {'─'*7}")
    for t in timestamps:
        print(f"  {t['word']:<20} {t['start']:>7.3f}  {t['end']:>7.3f}")


async def main() -> None:
    passed = failed = 0
    print(f"[{test_real_stt.__name__}]")
    try:
        await test_real_stt()
        passed += 1
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
