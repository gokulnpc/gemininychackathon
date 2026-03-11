"""Caption track model + SRT/WebVTT/Twick/ASS export.

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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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


@dataclass(frozen=True)
class CaptionRenderArtifact:
    path: str
    format: str
    render_mode: str
    style_requested: str
    style_effective: str
    degraded: bool
    track: CaptionTrack


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


CAPTION_STYLE_REGISTRY: dict[str, dict] = {
    "bold_stroke": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 52, "weight": 700, "family": "Arial Black"},
            "colors": {"text": "#ffffff", "highlight": "#ff4081", "bgColor": "#00000080"},
            "stroke": "#000000",
            "shadowOffset": [-2, 2],
            "shadowColor": "#000000",
        },
        "export_mode": "basic_subtitle",
        "ffmpeg_force_style": (
            "force_style='FontName=Arial Black,FontSize=20,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=3,Shadow=0,Alignment=10,MarginV=60'"
        ),
        "ass_style": {
            "fontname": "Arial Black",
            "fontsize": 20,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H000000FF",
            "outline_colour": "&H00000000",
            "back_colour": "&H64000000",
            "bold": 1,
            "italic": 0,
            "border_style": 1,
            "outline": 3,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 60,
        },
    },
    "hormozi": {
        "inherits": "bold_stroke",
    },
    "clean": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 36, "weight": 400, "family": "Arial"},
            "colors": {"text": "#ffffff", "highlight": "#ffffff", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [0, 1],
            "shadowColor": "#000000",
        },
        "export_mode": "basic_subtitle",
        "ffmpeg_force_style": (
            "force_style='FontName=Arial,FontSize=14,Bold=0,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=30'"
        ),
        "ass_style": {
            "fontname": "Arial",
            "fontsize": 14,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H00FFFFFF",
            "outline_colour": "&H00000000",
            "back_colour": "&H00000000",
            "bold": 0,
            "italic": 0,
            "border_style": 1,
            "outline": 2,
            "shadow": 1,
            "alignment": 2,
            "margin_v": 30,
        },
    },
    "sleek": {
        "inherits": "clean",
    },
    "clarity": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 36, "weight": 400, "family": "Arial"},
            "colors": {"text": "#cccccc", "highlight": "#ffffff", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [0, 1],
            "shadowColor": "#000000",
        },
        "export_mode": "basic_subtitle",
        "ffmpeg_force_style": (
            "force_style='FontName=Arial,FontSize=14,Bold=0,"
            "PrimaryColour=&H00CCCCCC,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=30'"
        ),
        "ass_style": {
            "fontname": "Arial",
            "fontsize": 14,
            "primary_colour": "&H00CCCCCC",
            "secondary_colour": "&H00FFFFFF",
            "outline_colour": "&H00000000",
            "back_colour": "&H00000000",
            "bold": 0,
            "italic": 0,
            "border_style": 1,
            "outline": 2,
            "shadow": 1,
            "alignment": 2,
            "margin_v": 30,
        },
    },
    "karaoke": {
        "twick_cap_style": "karaoke",
        "twick_props": {
            "font": {"size": 58, "weight": 700, "family": "Bangers"},
            "colors": {"text": "#ffffff", "highlight": "#ffd700", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [0, 2],
            "shadowColor": "#000000",
        },
        "export_mode": "advanced_ass",
        "ass_style": {
            "fontname": "Arial",
            "fontsize": 26,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H0000D7FF",
            "outline_colour": "&H00000000",
            "back_colour": "&H00000000",
            "bold": 1,
            "italic": 0,
            "border_style": 1,
            "outline": 3,
            "shadow": 1,
            "alignment": 2,
            "margin_v": 55,
        },
    },
    "red_highlight": {
        "twick_cap_style": "highlight_bg",
        "twick_props": {
            "font": {"size": 48, "weight": 700, "family": "Arial Black"},
            "colors": {"text": "#ffffff", "highlight": "#ff0000", "bgColor": "#ff0000"},
            "stroke": "#000000",
            "shadowOffset": [0, 0],
            "shadowColor": "#000000",
        },
        "export_mode": "advanced_ass",
        "ass_style": {
            "fontname": "Arial Black",
            "fontsize": 18,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H000000FF",
            "outline_colour": "&H00000000",
            "back_colour": "&H000000FF",
            "bold": 1,
            "italic": 0,
            "border_style": 3,
            "outline": 1,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 60,
        },
    },
    "majestic": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 50, "weight": 700, "family": "Georgia"},
            "colors": {"text": "#ffffff", "highlight": "#ffd700", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [-2, 4],
            "shadowColor": "#444444",
        },
        "export_mode": "advanced_ass",
        "ass_style": {
            "fontname": "Georgia",
            "fontsize": 22,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H0000D7FF",
            "outline_colour": "&H001C86EE",
            "back_colour": "&H00000000",
            "bold": 1,
            "italic": 0,
            "border_style": 1,
            "outline": 2,
            "shadow": 2,
            "alignment": 2,
            "margin_v": 50,
        },
    },
    "beast": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 60, "weight": 900, "family": "Impact"},
            "colors": {"text": "#ffffff", "highlight": "#ff0000", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [0, 4],
            "shadowColor": "#000000",
        },
        "export_mode": "advanced_ass",
        "ass_style": {
            "fontname": "Impact",
            "fontsize": 26,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H000000FF",
            "outline_colour": "&H00000000",
            "back_colour": "&H00000000",
            "bold": 1,
            "italic": 0,
            "border_style": 1,
            "outline": 4,
            "shadow": 0,
            "alignment": 10,
            "margin_v": 80,
        },
    },
    "elegant": {
        "twick_cap_style": "text_bg",
        "twick_props": {
            "font": {"size": 40, "weight": 400, "family": "Georgia"},
            "colors": {"text": "#ffffff", "highlight": "#ffffff", "bgColor": "transparent"},
            "stroke": "#000000",
            "shadowOffset": [0, 1],
            "shadowColor": "#000000",
        },
        "export_mode": "basic_subtitle",
        "ffmpeg_force_style": (
            "force_style='FontName=Georgia,FontSize=16,Bold=0,Italic=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=1,Shadow=1,Alignment=2,MarginV=35'"
        ),
        "ass_style": {
            "fontname": "Georgia",
            "fontsize": 16,
            "primary_colour": "&H00FFFFFF",
            "secondary_colour": "&H00FFFFFF",
            "outline_colour": "&H00000000",
            "back_colour": "&H00000000",
            "bold": 0,
            "italic": -1,
            "border_style": 1,
            "outline": 1,
            "shadow": 1,
            "alignment": 2,
            "margin_v": 35,
        },
    },
}

_DEFAULT_STYLE_KEY = "bold_stroke"

# Minimum time a cue should stay on screen (seconds) — WCAG readability
MIN_CUE_DURATION = 1.0

# Silence gap threshold: flush buffer if gap between words > this (seconds)
SILENCE_GAP_THRESHOLD = 0.7

# Sentence-ending characters that trigger a preferred break point
_SENTENCE_END = frozenset(".?!")


def _limits(style: str) -> tuple[float, int]:
    return _STYLE_LIMITS.get(style, _DEFAULT_LIMITS)


def resolve_caption_style(style: str) -> tuple[str, dict]:
    style_key = (style or _DEFAULT_STYLE_KEY).lower()
    definition = CAPTION_STYLE_REGISTRY.get(style_key)
    if definition is None:
        return _DEFAULT_STYLE_KEY, CAPTION_STYLE_REGISTRY[_DEFAULT_STYLE_KEY]
    inherited = definition.get("inherits")
    if inherited:
        _, base = resolve_caption_style(inherited)
        merged = {**base, **{k: v for k, v in definition.items() if k != "inherits"}}
        if "twick_props" in base or "twick_props" in definition:
            merged["twick_props"] = {
                **base.get("twick_props", {}),
                **definition.get("twick_props", {}),
            }
        if "ass_style" in base or "ass_style" in definition:
            merged["ass_style"] = {
                **base.get("ass_style", {}),
                **definition.get("ass_style", {}),
            }
        return style_key, merged
    return style_key, definition


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
            "props": {
                "words": [
                    {
                        "text": word.word,
                        "s": round(word.start, 3),
                        "e": round(word.end, 3),
                    }
                    for word in cue.words
                ],
            },
            "t": cue.text,
        })
    return elements


def build_track(word_timestamps: list[dict], style: str) -> CaptionTrack:
    """Build a full CaptionTrack from raw word timestamps."""
    cues = words_to_cues(word_timestamps, style)
    resolved_style, _ = resolve_caption_style(style)
    return CaptionTrack(style=resolved_style, cues=cues)


def _ass_ts(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds == 100:
        secs += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _style_to_ass_line(style: dict) -> str:
    ass = style["ass_style"]
    return (
        "Style: Default,"
        f"{ass['fontname']},{ass['fontsize']},{ass['primary_colour']},{ass['secondary_colour']},"
        f"{ass['outline_colour']},{ass['back_colour']},{ass['bold']},{ass['italic']},0,0,100,100,0,0,"
        f"{ass['border_style']},{ass['outline']},{ass['shadow']},{ass['alignment']},20,20,{ass['margin_v']},1"
    )


def cues_to_ass(cues: list[CaptionCue], style: str) -> str:
    """Serialize caption cues to ASS with support for styled advanced captions."""
    resolved_style, style_def = resolve_caption_style(style)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 576",
        "PlayResY: 1024",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        _style_to_ass_line(style_def),
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    for cue in cues:
        text = _ass_escape(cue.text)
        if style_def["export_mode"] == "advanced_ass" and cue.words:
            fragments: list[str] = []
            for word in cue.words:
                duration_cs = max(1, int(round((word.end - word.start) * 100)))
                word_text = _ass_escape(word.word)
                fragments.append(r"{\kf" + str(duration_cs) + "}" + word_text)
            text = " ".join(fragments)
        lines.append(
            f"Dialogue: 0,{_ass_ts(cue.start)},{_ass_ts(cue.end)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def generate_ass(
    word_timestamps: list[dict],
    style: str = "bold_stroke",
    output_path: str | None = None,
) -> str:
    track = build_track(word_timestamps, style)
    ass_content = cues_to_ass(track.cues, style)
    if output_path is None:
        output_path = f"/tmp/captions_{track.style}_{os.getpid()}.ass"
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(ass_content)
    logger.info("Generated %s ASS captions (%d cues) at %s", track.style, len(track.cues), output_path)
    return output_path


def generate_caption_asset(
    word_timestamps: list[dict],
    style: str = "clean",
    output_path: str | None = None,
) -> CaptionRenderArtifact:
    track = build_track(word_timestamps, style)
    style_effective, style_def = resolve_caption_style(style)
    suffix = ".ass" if style_def["export_mode"] == "advanced_ass" else ".srt"
    target_path = output_path or f"/tmp/captions_{style_effective}_{os.getpid()}{suffix}"
    target_path = str(Path(target_path).with_suffix(suffix))
    if style_def["export_mode"] == "advanced_ass":
        path = generate_ass(word_timestamps, style_effective, target_path)
        file_format = "ass"
    else:
        path = generate_srt(word_timestamps, style_effective, target_path)
        file_format = "srt"
    return CaptionRenderArtifact(
        path=path,
        format=file_format,
        render_mode=style_def["export_mode"],
        style_requested=style,
        style_effective=style_effective,
        degraded=False,
        track=track,
    )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


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
