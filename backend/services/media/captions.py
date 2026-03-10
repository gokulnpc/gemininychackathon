"""Caption track model + SRT/WebVTT/Twick export.

Internal representation uses Pydantic models (Word, CaptionCue, CaptionTrack).
Cues are grouped by time/duration — not fixed word count.
SRT/WebVTT are export-only formats; karaoke highlighting is handled by the renderer
using the word-level timing stored in each CaptionCue.

Public API (backward compat):
    generate_srt(word_timestamps, style, output_path) -> str
    build_track(word_timestamps, style) -> CaptionTrack
    generate_word_timestamps_from_script(text, duration) -> list[dict]
    cues_to_webvtt(cues) -> str
    cues_to_twick(cues, style) -> list[dict]
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from enum import Enum

from pydantic import BaseModel, field_validator

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

    @field_validator("start")
    @classmethod
    def start_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"start must be ≥ 0, got {v}")
        return v

    @field_validator("end")
    @classmethod
    def end_not_before_start(cls, v: float, info) -> float:
        start = info.data.get("start")
        if start is not None and v < start:
            raise ValueError(f"end ({v}) must be ≥ start ({start})")
        return v


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

_PUNCT_ONLY = re.compile(r"^[^\w']+$")           # purely non-word chars: "-", "--"
_BRACKET_TAG = re.compile(r"^\[.*]$|^<.*>$")    # noise tags: "[uh]", "<unk>", "[noise]"
_STRIP_LEADING = re.compile(r"^[^\w']+")         # leading non-word chars
_STRIP_TRAILING = re.compile(r"[^\w'.?!]+$")     # trailing non-word chars (preserve .?!)


def _clean_token(raw: str) -> str:
    """Return display text for an STT token, or '' if it should be skipped.

    - Standalone punctuation tokens ("-", "--") → ""
    - Bracket/angle-bracket noise tags ("[uh]", "<unk>", "[noise]") → ""
    - Sentence-ending punctuation preserved ("freezing." → "freezing.", "really?" → "really?")
    - Non-sentence trailing punctuation stripped ("Hello," → "Hello", "so;" → "so")
    - Internal apostrophes/hyphens ("don't", "well-known") → preserved
    """
    if _PUNCT_ONLY.match(raw) or _BRACKET_TAG.match(raw):
        return ""
    cleaned = _STRIP_LEADING.sub("", raw)
    cleaned = _STRIP_TRAILING.sub("", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Grouping limits per style
# ---------------------------------------------------------------------------

_STYLE_LIMITS: dict[str, tuple[float, int]] = {
    # style → (max_duration_secs, max_chars)
    CaptionStyle.BEAST:        (1.5,  20),   # one or two words max, fast cuts
    CaptionStyle.HORMOZI:      (2.0,  30),
    CaptionStyle.KARAOKE:      (3.0,  42),
    CaptionStyle.CLARITY:      (5.0,  42),   # longer duration, WCAG-compliant char limit
    CaptionStyle.CLEAN:        (3.0,  42),
    CaptionStyle.BOLD_STROKE:  (3.0,  42),
    CaptionStyle.RED_HIGHLIGHT:(3.0,  42),
    CaptionStyle.SLEEK:        (3.0,  42),
    CaptionStyle.MAJESTIC:     (3.0,  42),
    CaptionStyle.ELEGANT:      (3.0,  42),
}
_DEFAULT_LIMITS = (3.0, 42)

# Minimum time a cue should stay on screen (seconds) — WCAG readability
MIN_CUE_DURATION = 1.0

# Silence gap threshold: flush buffer if gap between words > this (seconds)
SILENCE_GAP_THRESHOLD = 0.7

# Sentence-ending characters that trigger a preferred break point
_SENTENCE_END = frozenset(".?!")


def _limits(style: str) -> tuple[float, int]:
    return _STYLE_LIMITS.get(style, _DEFAULT_LIMITS)


# ---------------------------------------------------------------------------
# Core grouping
# ---------------------------------------------------------------------------


def words_to_cues(word_timestamps: list[dict], style: str) -> list[CaptionCue]:
    """Group word-level timestamps into CaptionCue objects.

    Uses time/char limits, sentence-boundary detection, silence-gap flushing,
    and minimum-duration post-processing for industry-standard caption quality.

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

    def _flush(words: list[Word]) -> None:
        if not words:
            return
        joined = " ".join(w.word for w in words)
        cues.append(CaptionCue(
            start=words[0].start,
            end=words[-1].end,
            text=joined.upper() if upper_style else joined,
            words=list(words),
        ))

    prev_end: float | None = None

    for raw in word_timestamps:
        display = _clean_token(raw["word"])
        if not display:
            continue  # skip standalone punct / noise tokens

        start = raw["start"]
        end = raw["end"]
        if end < start:
            logger.warning("Skipping word %r: end (%.3f) < start (%.3f)", display, end, start)
            continue

        w = Word(word=display, start=start, end=end)

        if not buf:
            buf.append(w)
            prev_end = end
            continue

        # ── Gap-aware flush: silence > threshold → flush early ─────────
        if prev_end is not None and (start - prev_end) > SILENCE_GAP_THRESHOLD:
            _flush(buf)
            buf = [w]
            prev_end = end
            continue

        cue_duration = w.end - buf[0].start
        projected_chars = len(" ".join(x.word for x in buf)) + 1 + len(w.word)

        if cue_duration > max_duration or projected_chars > max_chars:
            # ── Sentence-boundary-aware flush ──────────────────────────
            # Prefer to break at the last sentence-ending word in the buffer
            break_idx = None
            for i in range(len(buf) - 1, -1, -1):
                if buf[i].word and buf[i].word[-1] in _SENTENCE_END:
                    break_idx = i
                    break

            if break_idx is not None and break_idx < len(buf) - 1:
                # Flush up to (including) the sentence-end word
                _flush(buf[: break_idx + 1])
                buf = buf[break_idx + 1 :] + [w]
            else:
                _flush(buf)
                buf = [w]
        else:
            buf.append(w)

            # ── Eager flush at sentence end if buffer is non-trivially full
            if display[-1] in _SENTENCE_END and len(buf) >= 2:
                _flush(buf)
                buf = []

        prev_end = end

    _flush(buf)

    # ── Post-process: enforce minimum cue duration ────────────────────────
    for i, cue in enumerate(cues):
        duration = cue.end - cue.start
        if duration < MIN_CUE_DURATION:
            desired_end = cue.start + MIN_CUE_DURATION
            # Cap at next cue's start to prevent overlap
            if i + 1 < len(cues):
                desired_end = min(desired_end, cues[i + 1].start)
            cues[i] = cue.model_copy(update={"end": round(desired_end, 3)})

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
    if not cues:
        return ""
    entries = []
    for idx, cue in enumerate(cues, start=1):
        entries.append(
            f"{idx}\n"
            f"{_srt_ts(cue.start)} --> {_srt_ts(cue.end)}\n"
            f"{cue.text}\n"
        )
    return "\n".join(entries) + "\n"


def _webvtt_ts(seconds: float) -> str:
    """Convert seconds → WebVTT timestamp: HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def cues_to_webvtt(cues: list[CaptionCue]) -> str:
    """Serialize CaptionCue list → WebVTT string (HTML5 compatible)."""
    if not cues:
        return "WEBVTT\n\n"
    lines = ["WEBVTT", ""]
    for idx, cue in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_webvtt_ts(cue.start)} --> {_webvtt_ts(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines) + "\n"


def cues_to_twick(cues: list[CaptionCue], track_id: str | None = None) -> list[dict]:
    """Convert CaptionCue list → Twick SDK caption elements.

    Each element has: id, trackId, type, s, e, props, t
    Timing matches SRT/WebVTT exactly for consistency.
    """
    tid = track_id or f"t-captions-{uuid.uuid4().hex[:12]}"
    elements = []
    for cue in cues:
        elements.append({
            "id": f"e-cap-{uuid.uuid4().hex[:12]}",
            "trackId": tid,
            "type": "caption",
            "s": round(cue.start, 3),
            "e": round(cue.end, 3),
            "props": {},
            "t": cue.text,
        })
    return elements


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
    if not words or total_duration <= 0:
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
