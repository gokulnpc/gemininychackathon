"""Integration test for services/media/captions.py — real audio → STT → captions.

Uses backend/input/weather_caudio.m4a, converts to WAV via ffmpeg, runs real
GCP Speech-to-Text for word timestamps, then exercises the full captions pipeline.

Requires:
  - GCP credentials (ADC): gcloud auth application-default login
  - speech.googleapis.com enabled on your project
  - ffmpeg installed and on PATH

Usage:
    cd backend && RUN_LIVE_INTEGRATION_TESTS=1 .venv/bin/python -m pytest tests/integration/test_captions.py -v
    # or as a standalone script:
    cd backend && .venv/bin/python tests/integration/test_captions.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.media.captions import (
    build_track,
    cues_to_srt,
    cues_to_twick,
    cues_to_webvtt,
    generate_srt,
)
from services.media.stt import extract_word_timestamps

import pytest

SAMPLE_M4A = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "input", "weather_caudio.m4a")
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() not in {"1", "true", "yes"},
    reason="Live integration test. Set RUN_LIVE_INTEGRATION_TESTS=1 to run.",
)


def _m4a_to_wav(m4a_path: str) -> str:
    """Convert m4a → LINEAR16 mono 24kHz WAV using ffmpeg. Returns temp WAV path."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="caption_test_")
    os.close(fd)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", m4a_path,
            "-ar", "24000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            wav_path,
        ],
        check=True,
        capture_output=True,
    )
    return wav_path


async def test_real_audio_to_captions():
    """Real GCP STT → caption pipeline: audio → timestamps → SRT + WebVTT + Twick."""
    if not os.path.exists(SAMPLE_M4A):
        raise FileNotFoundError(f"Sample audio not found: {SAMPLE_M4A}")

    print(f"  audio: {SAMPLE_M4A}")

    # Step 1: Convert to WAV
    wav_path = _m4a_to_wav(SAMPLE_M4A)
    print(f"  wav: {wav_path} ({os.path.getsize(wav_path):,} bytes)")

    try:
        # Step 2: Real GCP STT
        print("  Running GCP Speech-to-Text ...")
        timestamps = await extract_word_timestamps(wav_path, sample_rate=24000)
    finally:
        os.unlink(wav_path)

    assert isinstance(timestamps, list), f"Expected list, got {type(timestamps)}"
    assert len(timestamps) > 0, "Expected at least one word timestamp"
    print(f"  ✓ STT: {len(timestamps)} words ({timestamps[0]['start']:.1f}s → {timestamps[-1]['end']:.1f}s)")

    # Validate timestamp integrity (what captions.py now validates internally)
    for w in timestamps:
        assert w["end"] >= w["start"], f"STT returned invalid timestamp: {w}"

    # Step 3: Build caption track (multiple styles)
    for style in ["clean", "beast", "bold_stroke"]:
        track = build_track(timestamps, style)
        assert len(track.cues) > 0, f"No cues for style {style}"

        # Validate cue properties
        for cue in track.cues:
            assert cue.end > cue.start, f"Cue end <= start: {cue}"
            assert len(cue.text) > 0, f"Empty cue text"
            assert len(cue.words) > 0, f"Cue has no words"

        # Step 4: Export SRT
        srt = cues_to_srt(track.cues)
        assert "-->" in srt
        assert srt.endswith("\n")

        # Step 5: Export WebVTT
        vtt = cues_to_webvtt(track.cues)
        assert vtt.startswith("WEBVTT")

        # Step 6: Export Twick elements
        elements = cues_to_twick(track.cues, track_id="t-test")
        assert len(elements) == len(track.cues)
        for elem in elements:
            assert elem["type"] == "caption"
            assert isinstance(elem["t"], str) and len(elem["t"]) > 0

        print(f"  ✓ [{style:12s}] {len(track.cues)} cues | SRT: {len(srt)} chars | VTT: {len(vtt)} chars | Twick: {len(elements)} elems")

    # Step 7: Write SRT to file
    srt_path = generate_srt(timestamps, "bold_stroke")
    assert os.path.exists(srt_path)
    size = os.path.getsize(srt_path)
    assert size > 0, "SRT file is empty"
    print(f"\n  ✓ SRT file: {srt_path} ({size} bytes)")
    os.unlink(srt_path)

    # Summary
    print(f"\n  {'─'*40}")
    track = build_track(timestamps, "clean")
    print(f"  First cue: \"{track.cues[0].text}\" ({track.cues[0].start:.3f}s → {track.cues[0].end:.3f}s)")
    print(f"  Last cue:  \"{track.cues[-1].text}\" ({track.cues[-1].start:.3f}s → {track.cues[-1].end:.3f}s)")


async def test_multiple_styles_produce_different_grouping():
    """Different styles should produce different cue counts from real STT data."""
    if not os.path.exists(SAMPLE_M4A):
        raise FileNotFoundError(f"Sample audio not found: {SAMPLE_M4A}")

    wav_path = _m4a_to_wav(SAMPLE_M4A)
    try:
        timestamps = await extract_word_timestamps(wav_path, sample_rate=24000)
    finally:
        os.unlink(wav_path)

    beast_track = build_track(timestamps, "beast")
    clarity_track = build_track(timestamps, "clarity")

    assert len(beast_track.cues) > len(clarity_track.cues), (
        f"Beast ({len(beast_track.cues)} cues) should have more cues than "
        f"Clarity ({len(clarity_track.cues)} cues)"
    )
    print(f"  ✓ beast={len(beast_track.cues)} cues vs clarity={len(clarity_track.cues)} cues")


async def main() -> None:
    tests = [
        test_real_audio_to_captions,
        test_multiple_styles_produce_different_grouping,
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
