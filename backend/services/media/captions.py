"""Caption track model + SRT export.

Internal representation uses Pydantic models (Word, CaptionCue, CaptionTrack).
Cues are grouped by time/duration — not fixed word count.
SRT/WebVTT are export-only formats; karaoke highlighting is handled by the renderer
using the word-level timing stored in each CaptionCue.

Public API (backward compat):
    generate_srt(word_timestamps, style, output_path) -> str
    build_track(word_timestamps, style) -> CaptionTrack
    generate_word_timestamps_from_script(text, duration) -> list[dict]
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style enum
# ---------------------------------------------------------------------------


class CaptionStyle(str, Enum):
    # Legacy values (kept for backward compat)
    HORMOZI = "hormozi"
    CLEAN = "clean"
    KARAOKE = "karaoke"
    # Wizard styles
    BOLD_STROKE = "bold_stroke"
    RED_HIGHLIGHT = "red_highlight"
    SLEEK = "sleek"
    MAJESTIC = "majestic"
    BEAST = "beast"
    ELEGANT = "elegant"
    CLARITY = "clarity"


# ---------------------------------------------------------------------------
# Internal Pydantic models
# ---------------------------------------------------------------------------


class Word(BaseModel):
    word: str
    start: float  # seconds
    end: float    # seconds


class CaptionCue(BaseModel):
    start: float
    end: float
    text: str          # plain joined text (no markup)
    words: list[Word]  # word-level timing — used by renderer for karaoke


class CaptionTrack(BaseModel):
    style: str
    cues: list[CaptionCue]


# ---------------------------------------------------------------------------
# Token normalization
# ---------------------------------------------------------------------------

_PUNCT_ONLY = re.compile(r"^[^\w']+$")           # purely non-word chars: "-", ".", "?"
_BRACKET_TAG = re.compile(r"^\[.*]$|^<.*>$")    # noise tags: "[uh]", "<unk>", "[noise]"
_STRIP_EDGES = re.compile(r"^[^\w']+|[^\w']+$")  # leading/trailing non-word chars


def _clean_token(raw: str) -> str:
    """Return display text for an STT token, or '' if it should be skipped.

    - Standalone punctuation tokens ("-", ".", "?", "--") → ""
    - Bracket/angle-bracket noise tags ("[uh]", "<unk>", "[noise]") → ""
    - Trailing punctuation on real words ("Hello,", "really?") → stripped ("Hello", "really")
    - Internal apostrophes/hyphens ("don't", "well-known") → preserved
    """
    if _PUNCT_ONLY.match(raw) or _BRACKET_TAG.match(raw):
        return ""
    return _STRIP_EDGES.sub("", raw)


# ---------------------------------------------------------------------------
# Grouping limits per style
# ---------------------------------------------------------------------------

_STYLE_LIMITS: dict[str, tuple[float, int]] = {
    # style → (max_duration_secs, max_chars)
    CaptionStyle.BEAST:        (1.5,  20),   # one or two words max, fast cuts
    CaptionStyle.HORMOZI:      (2.0,  30),
    CaptionStyle.KARAOKE:      (3.0,  42),
    CaptionStyle.CLARITY:      (5.0,  80),   # longer, subtitle-style
    CaptionStyle.CLEAN:        (3.0,  42),
    CaptionStyle.BOLD_STROKE:  (3.0,  42),
    CaptionStyle.RED_HIGHLIGHT:(3.0,  42),
    CaptionStyle.SLEEK:        (3.0,  42),
    CaptionStyle.MAJESTIC:     (3.0,  42),
    CaptionStyle.ELEGANT:      (3.0,  42),
}
_DEFAULT_LIMITS = (3.0, 42)


def _limits(style: str) -> tuple[float, int]:
    return _STYLE_LIMITS.get(style, _DEFAULT_LIMITS)


# ---------------------------------------------------------------------------
# Core grouping
# ---------------------------------------------------------------------------


def words_to_cues(word_timestamps: list[dict], style: str) -> list[CaptionCue]:
    """Group word-level timestamps into CaptionCue objects using time/char limits.

    Args:
        word_timestamps: list of {"word": str, "start": float, "end": float}
        style: CaptionStyle value

    Returns:
        list of CaptionCue with plain text and per-word timing.
    """
    if not word_timestamps:
        return []

    max_duration, max_chars = _limits(style)
    upper_style = style in (CaptionStyle.BEAST, CaptionStyle.HORMOZI)

    cues: list[CaptionCue] = []
    buf: list[Word] = []

    def _flush(buf: list[Word]) -> None:
        if not buf:
            return
        joined = " ".join(w.word for w in buf)
        cues.append(CaptionCue(
            start=buf[0].start,
            end=buf[-1].end,
            text=joined.upper() if upper_style else joined,
            words=list(buf),
        ))

    for raw in word_timestamps:
        display = _clean_token(raw["word"])
        if not display:
            continue  # skip standalone punct / noise tokens
        w = Word(word=display, start=raw["start"], end=raw["end"])

        if not buf:
            buf.append(w)
            continue

        cue_duration = w.end - buf[0].start
        projected_chars = len(" ".join(x.word for x in buf)) + 1 + len(w.word)

        if cue_duration > max_duration or projected_chars > max_chars:
            _flush(buf)
            buf = [w]
        else:
            buf.append(w)

    _flush(buf)
    return cues


# ---------------------------------------------------------------------------
# SRT export
# ---------------------------------------------------------------------------


def _srt_ts(seconds: float) -> str:
    """Convert seconds → SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def cues_to_srt(cues: list[CaptionCue]) -> str:
    """Serialize CaptionCue list → SRT string (no embedded markup)."""
    entries = []
    for idx, cue in enumerate(cues, start=1):
        entries.append(
            f"{idx}\n"
            f"{_srt_ts(cue.start)} --> {_srt_ts(cue.end)}\n"
            f"{cue.text}\n"
        )
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_track(word_timestamps: list[dict], style: str) -> CaptionTrack:
    """Build a full CaptionTrack from raw word timestamps."""
    cues = words_to_cues(word_timestamps, style)
    return CaptionTrack(style=style, cues=cues)


def generate_srt(
    word_timestamps: list[dict],
    style: str = "clean",
    output_path: str | None = None,
) -> str:
    """Generate an SRT caption file from word-level timestamps.

    Args:
        word_timestamps: list of {"word": str, "start": float, "end": float}
        style: CaptionStyle value (e.g. "clean", "beast", "clarity")
        output_path: where to write the .srt file; defaults to /tmp

    Returns:
        Path to the generated .srt file.
    """
    track = build_track(word_timestamps, style)
    srt_content = cues_to_srt(track.cues)

    if output_path is None:
        output_path = f"/tmp/captions_{style}_{os.getpid()}.srt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info("Generated %s captions (%d cues) at %s", style, len(track.cues), output_path)
    return output_path


def generate_word_timestamps_from_script(
    voiceover_text: str,
    total_duration: float,
) -> list[dict]:
    """Estimate word-level timestamps when real STT timestamps aren't available.

    Distributes words evenly across the duration. Prefer real Nova Sonic timestamps.
    """
    words = voiceover_text.split()
    if not words:
        return []

    time_per_word = total_duration / len(words)
    return [
        {
            "word": word,
            "start": round(i * time_per_word, 3),
            "end": round((i + 1) * time_per_word, 3),
        }
        for i, word in enumerate(words)
    ]
