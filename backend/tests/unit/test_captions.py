"""Unit tests for services/media/captions.py — pure functions, no API calls.

Tests token normalization, cue grouping, SRT/WebVTT serialization, Twick export,
and synthetic timestamp generation.

Usage:
    cd backend && .venv/bin/python tests/unit/test_captions.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pydantic import ValidationError

from services.media.captions import (
    CaptionCue,
    CaptionStyle,
    CaptionTrack,
    Word,
    _clean_token,
    _srt_ts,
    _webvtt_ts,
    build_track,
    cues_to_srt,
    cues_to_twick,
    cues_to_webvtt,
    generate_srt,
    generate_word_timestamps_from_script,
    words_to_cues,
)


# ── Fake data ─────────────────────────────────────────────────────────────────

_SAMPLE_WORDS = [
    {"word": "Hello", "start": 0.0, "end": 0.5},
    {"word": "world", "start": 0.5, "end": 1.0},
    {"word": "this",  "start": 1.0, "end": 1.4},
    {"word": "is",    "start": 1.4, "end": 1.6},
    {"word": "a",     "start": 1.6, "end": 1.7},
    {"word": "test",  "start": 1.7, "end": 2.0},
]


# ── _clean_token (token normalization) ────────────────────────────────────────

def test_clean_normal_word():
    result = _clean_token("Hello")
    assert result == "Hello", f"Expected 'Hello', got: {result}"
    print("  ✓ normal word → unchanged")


def test_clean_strips_trailing_punct():
    result = _clean_token("word,")
    assert result == "word", f"Expected 'word', got: {result}"
    print("  ✓ trailing comma stripped")


def test_clean_preserves_apostrophe():
    result = _clean_token("don't")
    assert result == "don't", f"Expected \"don't\", got: {result}"
    print("  ✓ apostrophe preserved in contractions")


def test_clean_skips_standalone_punct():
    result = _clean_token("--")
    assert result == "", f"Expected '', got: {result}"
    print("  ✓ standalone punct → ''")


def test_clean_skips_noise_tag():
    result = _clean_token("[uh]")
    assert result == "", f"Expected '', got: {result}"
    result2 = _clean_token("<unk>")
    assert result2 == "", f"Expected '' for <unk>, got: {result2}"
    print("  ✓ noise tags → ''")


# ── words_to_cues (core grouping) ────────────────────────────────────────────

def test_empty_input_returns_empty():
    result = words_to_cues([], "clean")
    assert result == [], f"Expected [], got: {result}"
    print("  ✓ empty input → []")


def test_single_word_becomes_one_cue():
    words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
    result = words_to_cues(words, "clean")
    assert len(result) == 1, f"Expected 1 cue, got {len(result)}"
    assert result[0].text == "Hello"
    assert result[0].start == 0.0
    # end may be extended by min_duration post-processing (0.5 → 1.0)
    assert result[0].end >= 0.5
    print("  ✓ single word → 1 cue")


def test_respects_max_duration_limit():
    # beast style: max 1.5s duration — these words span 3s, should split
    words = [
        {"word": "First",  "start": 0.0, "end": 0.5},
        {"word": "second", "start": 1.0, "end": 1.5},
        {"word": "third",  "start": 2.0, "end": 2.5},
        {"word": "fourth", "start": 3.0, "end": 3.5},
    ]
    result = words_to_cues(words, CaptionStyle.BEAST)
    assert len(result) >= 2, f"Expected ≥2 cues for duration split, got {len(result)}"
    print(f"  ✓ exceeding max duration → split into {len(result)} cues")


def test_respects_max_chars_limit():
    # beast style: max 20 chars — "supercalifragilistic" alone is 19 chars
    words = [
        {"word": "supercalifragilistic", "start": 0.0, "end": 0.5},
        {"word": "expialidocious",       "start": 0.5, "end": 1.0},
    ]
    result = words_to_cues(words, CaptionStyle.BEAST)
    assert len(result) == 2, f"Expected 2 cues for char limit, got {len(result)}"
    print("  ✓ exceeding max chars → split into separate cues")


def test_beast_style_uppercases():
    words = [{"word": "hello", "start": 0.0, "end": 0.5}]
    result = words_to_cues(words, CaptionStyle.BEAST)
    assert result[0].text == "HELLO", f"Expected 'HELLO', got: {result[0].text}"
    print("  ✓ beast style → UPPERCASE text")


def test_skips_noise_tokens():
    words = [
        {"word": "Hello", "start": 0.0, "end": 0.5},
        {"word": "[uh]",  "start": 0.5, "end": 0.7},
        {"word": "world", "start": 0.7, "end": 1.0},
    ]
    result = words_to_cues(words, "clean")
    all_text = " ".join(c.text for c in result)
    assert "[uh]" not in all_text, f"Noise token should be filtered: {all_text}"
    print("  ✓ noise tokens filtered out")


def test_handles_unsorted_timestamps():
    """Words with end < start should be skipped (bug fix validation)."""
    words = [
        {"word": "Good",   "start": 0.0,  "end": 0.5},
        {"word": "bad",    "start": 1.0,  "end": 0.2},  # end < start!
        {"word": "normal", "start": 1.5,  "end": 2.0},
    ]
    result = words_to_cues(words, "clean")
    all_text = " ".join(c.text for c in result)
    assert "bad" not in all_text, f"Word with end < start should be skipped: {all_text}"
    assert "Good" in all_text
    assert "normal" in all_text
    print("  ✓ unsorted timestamps → invalid word skipped")


# ── _srt_ts (timestamp formatting) ───────────────────────────────────────────

def test_srt_ts_zero():
    result = _srt_ts(0.0)
    assert result == "00:00:00,000", f"Expected '00:00:00,000', got: {result}"
    print("  ✓ 0.0 → '00:00:00,000'")


def test_srt_ts_complex():
    result = _srt_ts(3661.5)
    assert result == "01:01:01,500", f"Expected '01:01:01,500', got: {result}"
    print("  ✓ 3661.5 → '01:01:01,500'")


def test_srt_ts_subsecond():
    result = _srt_ts(0.123)
    assert result == "00:00:00,123", f"Expected '00:00:00,123', got: {result}"
    print("  ✓ 0.123 → '00:00:00,123'")


# ── cues_to_srt (SRT serialization) ──────────────────────────────────────────

def test_srt_format_correct():
    cues = [
        CaptionCue(start=0.0, end=1.0, text="Hello world", words=[]),
        CaptionCue(start=1.0, end=2.0, text="Test caption", words=[]),
    ]
    srt = cues_to_srt(cues)
    assert "1\n" in srt, "Missing index 1"
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "Hello world" in srt
    assert "2\n" in srt, "Missing index 2"
    assert srt.endswith("\n"), "SRT should end with newline"
    print("  ✓ SRT format matches spec")


def test_srt_empty_cues():
    result = cues_to_srt([])
    assert result == "", f"Expected '' for empty cues, got: {repr(result)}"
    print("  ✓ empty cues → ''")


# ── cues_to_webvtt (WebVTT export) ───────────────────────────────────────────

def test_webvtt_format_correct():
    cues = [
        CaptionCue(start=0.0, end=1.0, text="Hello world", words=[]),
    ]
    vtt = cues_to_webvtt(cues)
    assert vtt.startswith("WEBVTT\n"), "WebVTT must start with WEBVTT header"
    assert "00:00:00.000 --> 00:00:01.000" in vtt, "WebVTT uses dots not commas"
    assert "Hello world" in vtt
    print("  ✓ WebVTT format correct (header + dot timestamps)")


def test_webvtt_empty_cues():
    result = cues_to_webvtt([])
    assert result.startswith("WEBVTT"), "Empty WebVTT should still have header"
    print("  ✓ empty cues → 'WEBVTT' header only")


# ── cues_to_twick (Twick SDK export) ─────────────────────────────────────────

def test_twick_elements_have_required_fields():
    cues = [
        CaptionCue(start=0.0, end=1.0, text="Hello", words=[]),
        CaptionCue(start=1.0, end=2.0, text="World", words=[]),
    ]
    elements = cues_to_twick(cues, track_id="t-test")
    assert len(elements) == 2
    for elem in elements:
        assert "id" in elem
        assert elem["trackId"] == "t-test"
        assert elem["type"] == "caption"
        assert "s" in elem and "e" in elem
        assert "t" in elem
        assert "props" in elem
    print("  ✓ Twick elements have all required fields (id, trackId, type, s, e, t, props)")


def test_twick_elements_timing_matches_srt():
    cues = [
        CaptionCue(start=1.234, end=3.567, text="Test cue", words=[]),
    ]
    elements = cues_to_twick(cues)
    srt = cues_to_srt(cues)

    assert elements[0]["s"] == 1.234
    assert elements[0]["e"] == 3.567
    assert elements[0]["t"] == "Test cue"
    # SRT should have the same timestamps
    assert "00:00:01,234" in srt
    assert "00:00:03,567" in srt
    print("  ✓ Twick timing matches SRT timestamps exactly")


# ── generate_word_timestamps_from_script ─────────────────────────────────────

def test_even_distribution():
    result = generate_word_timestamps_from_script("one two three four", 4.0)
    assert len(result) == 4
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 1.0
    assert result[3]["start"] == 3.0
    assert result[3]["end"] == 4.0
    print("  ✓ 4 words, 4s → 1s per word")


def test_empty_text():
    result = generate_word_timestamps_from_script("", 5.0)
    assert result == [], f"Expected [], got: {result}"
    print("  ✓ empty text → []")


def test_zero_duration():
    result = generate_word_timestamps_from_script("hello world", 0.0)
    assert result == [], f"Expected [] for zero duration, got: {result}"
    result2 = generate_word_timestamps_from_script("hello world", -1.0)
    assert result2 == [], f"Expected [] for negative duration, got: {result2}"
    print("  ✓ zero/negative duration → [] (bug fix)")


# ── build_track + generate_srt (integration) ─────────────────────────────────

def test_build_track_returns_caption_track():
    track = build_track(_SAMPLE_WORDS, "clean")
    assert isinstance(track, CaptionTrack)
    assert track.style == "clean"
    assert len(track.cues) > 0
    for cue in track.cues:
        assert cue.start >= 0
        assert cue.end >= cue.start
        assert len(cue.text) > 0
    print(f"  ✓ build_track → CaptionTrack with {len(track.cues)} cues")


def test_generate_srt_writes_file():
    output_path = f"/tmp/test_captions_{os.getpid()}.srt"
    try:
        result_path = generate_srt(_SAMPLE_WORDS, "clean", output_path)
        assert os.path.exists(result_path), f"SRT file not created: {result_path}"
        with open(result_path) as f:
            content = f.read()
        assert "Hello" in content
        assert "-->" in content
        assert content.endswith("\n")
        print(f"  ✓ SRT file written to {result_path}")
    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


# ── Production hardening tests ────────────────────────────────────────────────

def test_prefers_sentence_boundary_break():
    """When hitting char/duration limit, prefer to break at sentence end."""
    words = [
        {"word": "Hello",    "start": 0.0, "end": 0.3},
        {"word": "world.",   "start": 0.3, "end": 0.6},
        {"word": "This",     "start": 0.6, "end": 0.9},
        {"word": "is",       "start": 0.9, "end": 1.1},
        {"word": "new.",     "start": 1.1, "end": 1.4},
    ]
    # Use clarity style (5s, 42 chars) to avoid char/duration splits —
    # sentence-end eager flush should still trigger
    result = words_to_cues(words, CaptionStyle.CLARITY)
    texts = [c.text for c in result]
    # Should flush at "world." (sentence end)
    assert any(t.endswith("world.") for t in texts), f"Should break at sentence end: {texts}"
    print(f"  ✓ sentence boundary split: {texts}")


def test_min_duration_extends_short_cue():
    """A 50ms cue should be extended to at least 1.0s."""
    words = [
        {"word": "Hi",    "start": 0.0, "end": 0.05},
        {"word": "there", "start": 5.0, "end": 6.0},  # big gap forces 2 cues
    ]
    result = words_to_cues(words, "clean")
    assert len(result) == 2, f"Expected 2 cues, got {len(result)}"
    first_duration = result[0].end - result[0].start
    assert first_duration >= 1.0, f"Min duration not enforced: {first_duration:.3f}s"
    print(f"  ✓ 50ms cue extended to {first_duration:.3f}s")


def test_min_duration_no_overlap():
    """Extended cue should not overlap the next cue."""
    words = [
        {"word": "Quick",  "start": 0.0,  "end": 0.05},
        {"word": "follow", "start": 0.3,  "end": 0.8},
    ]
    result = words_to_cues(words, "clean")
    if len(result) >= 2:
        assert result[0].end <= result[1].start, (
            f"Overlap: cue 0 end={result[0].end}, cue 1 start={result[1].start}"
        )
        print(f"  ✓ extended cue does not overlap (end={result[0].end} ≤ start={result[1].start})")
    else:
        # Both words grouped into one cue — no overlap possible
        print(f"  ✓ words grouped together, no overlap issue")


def test_gap_flushes_on_silence():
    """A >0.7s silence gap between words should flush the buffer."""
    words = [
        {"word": "Before",  "start": 0.0,  "end": 0.5},
        {"word": "pause",   "start": 0.5,  "end": 1.0},
        # 1.5s silence gap
        {"word": "After",   "start": 2.5,  "end": 3.0},
    ]
    result = words_to_cues(words, CaptionStyle.CLARITY)
    assert len(result) >= 2, f"Silence gap should force a split, got {len(result)} cues"
    # First cue should end before the gap
    texts = [c.text for c in result]
    assert any("Before" in t for t in texts[:1]), f"First cue should have 'Before': {texts}"
    assert any("After" in t for t in texts[-1:]), f"Last cue should have 'After': {texts}"
    print(f"  ✓ silence gap → buffer flushed ({len(result)} cues)")


def test_clean_preserves_sentence_punct():
    """Sentence-ending punctuation (.?!) should be preserved."""
    assert _clean_token("freezing.") == "freezing.", "Period should be preserved"
    assert _clean_token("really?") == "really?", "Question mark should be preserved"
    assert _clean_token("wow!") == "wow!", "Exclamation should be preserved"
    print("  ✓ sentence punctuation preserved (.?!)")


def test_clean_strips_non_sentence_punct():
    """Non-sentence punctuation (commas, semicolons) should still be stripped."""
    assert _clean_token("word,") == "word", "Comma should be stripped"
    assert _clean_token("so;") == "so", "Semicolon should be stripped"
    assert _clean_token("end:") == "end", "Colon should be stripped"
    print("  ✓ non-sentence punctuation stripped (,;:)")


def test_word_model_rejects_negative_start():
    """Word with start < 0 should raise ValidationError."""
    try:
        Word(word="bad", start=-1.0, end=0.5)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
    print("  ✓ Word(start=-1.0) → ValidationError")


def test_word_model_rejects_end_before_start():
    """Word with end < start should raise ValidationError."""
    try:
        Word(word="bad", start=2.0, end=1.0)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
    print("  ✓ Word(end < start) → ValidationError")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    test_groups = {
        "_clean_token (token normalization)": [
            test_clean_normal_word,
            test_clean_strips_trailing_punct,
            test_clean_preserves_apostrophe,
            test_clean_skips_standalone_punct,
            test_clean_skips_noise_tag,
        ],
        "words_to_cues (core grouping)": [
            test_empty_input_returns_empty,
            test_single_word_becomes_one_cue,
            test_respects_max_duration_limit,
            test_respects_max_chars_limit,
            test_beast_style_uppercases,
            test_skips_noise_tokens,
            test_handles_unsorted_timestamps,
        ],
        "_srt_ts (timestamp formatting)": [
            test_srt_ts_zero,
            test_srt_ts_complex,
            test_srt_ts_subsecond,
        ],
        "cues_to_srt (SRT serialization)": [
            test_srt_format_correct,
            test_srt_empty_cues,
        ],
        "cues_to_webvtt (WebVTT export)": [
            test_webvtt_format_correct,
            test_webvtt_empty_cues,
        ],
        "cues_to_twick (Twick SDK export)": [
            test_twick_elements_have_required_fields,
            test_twick_elements_timing_matches_srt,
        ],
        "generate_word_timestamps_from_script": [
            test_even_distribution,
            test_empty_text,
            test_zero_duration,
        ],
        "build_track + generate_srt": [
            test_build_track_returns_caption_track,
            test_generate_srt_writes_file,
        ],
        "production hardening": [
            test_prefers_sentence_boundary_break,
            test_min_duration_extends_short_cue,
            test_min_duration_no_overlap,
            test_gap_flushes_on_silence,
            test_clean_preserves_sentence_punct,
            test_clean_strips_non_sentence_punct,
            test_word_model_rejects_negative_start,
            test_word_model_rejects_end_before_start,
        ],
    }

    passed = failed = 0

    for group_name, tests in test_groups.items():
        print(f"\n── {group_name} ──")
        for fn in tests:
            print(f"[{fn.__name__}]")
            try:
                fn()
                passed += 1
            except Exception as exc:
                print(f"  ✗ FAILED: {exc}")
                failed += 1

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
