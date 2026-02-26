import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


class CaptionStyle(str, Enum):
    # Legacy values (kept for backward compat)
    HORMOZI = "hormozi"
    CLEAN = "clean"
    KARAOKE = "karaoke"
    # New wizard styles
    BOLD_STROKE = "bold_stroke"
    RED_HIGHLIGHT = "red_highlight"
    SLEEK = "sleek"
    MAJESTIC = "majestic"
    BEAST = "beast"
    ELEGANT = "elegant"
    CLARITY = "clarity"


def _format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(
    word_timestamps: list[dict],
    style: str = "clean",
    output_path: str | None = None,
) -> str:
    """Generate an SRT caption file from word-level timestamps.

    Args:
        word_timestamps: List of dicts with keys: word, start, end
            Example: [{"word": "Hello", "start": 0.0, "end": 0.5}, ...]
        style: Caption style — "hormozi", "clean", or "karaoke"
        output_path: Where to write the .srt file. If None, writes to /tmp.

    Returns:
        Path to the generated .srt file.
    """
    if style == CaptionStyle.BEAST:
        srt_content = _generate_hormozi(word_timestamps, words_per_group=1)
    elif style == CaptionStyle.KARAOKE:
        srt_content = _generate_karaoke(word_timestamps)
    elif style == CaptionStyle.CLARITY:
        srt_content = _generate_clean(word_timestamps, words_per_group=7)
    else:  # all other styles: max 2 words per subtitle
        srt_content = _generate_hormozi(word_timestamps, words_per_group=2)

    if output_path is None:
        output_path = f"/tmp/captions_{style}_{os.getpid()}.srt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info("Generated %s captions at %s", style, output_path)
    return output_path


def _generate_hormozi(word_timestamps: list[dict], words_per_group: int = 2) -> str:
    """Word-by-word captions — configurable words per subtitle, ALL CAPS, fast cuts."""
    entries = []
    idx = 1

    i = 0
    while i < len(word_timestamps):
        group_end = min(i + words_per_group, len(word_timestamps))
        words_in_group = word_timestamps[i:group_end]

        start = words_in_group[0]["start"]
        end = words_in_group[-1]["end"]
        text = " ".join(w["word"] for w in words_in_group).upper()

        entries.append(
            f"{idx}\n"
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n"
            f"{text}\n"
        )
        idx += 1
        i = group_end

    return "\n".join(entries)


def _generate_clean(word_timestamps: list[dict], words_per_group: int = 7) -> str:
    """Standard subtitle style — groups words into natural phrases."""
    entries = []
    idx = 1

    i = 0
    while i < len(word_timestamps):
        group_end = min(i + words_per_group, len(word_timestamps))
        words_in_group = word_timestamps[i:group_end]

        start = words_in_group[0]["start"]
        end = words_in_group[-1]["end"]
        text = " ".join(w["word"] for w in words_in_group)

        entries.append(
            f"{idx}\n"
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n"
            f"{text}\n"
        )
        idx += 1
        i = group_end

    return "\n".join(entries)


def _generate_karaoke(word_timestamps: list[dict]) -> str:
    """Karaoke-style — shows the full phrase but highlights the current word.

    Uses ASS-style markup within SRT for word highlighting. The active word
    is wrapped in <font color="#FFD700"> tags. Groups of ~6 words shown at once,
    with each word highlighted in sequence.
    """
    entries = []
    idx = 1
    words_per_group = 6

    i = 0
    while i < len(word_timestamps):
        group_end = min(i + words_per_group, len(word_timestamps))
        words_in_group = word_timestamps[i:group_end]

        # Create one entry per word in the group, highlighting the active word
        for j, active_word in enumerate(words_in_group):
            parts = []
            for k, w in enumerate(words_in_group):
                if k == j:
                    parts.append(f'<font color="#FFD700"><b>{w["word"]}</b></font>')
                else:
                    parts.append(w["word"])

            start = active_word["start"]
            # End at next word start, or this word's end for the last word
            if j + 1 < len(words_in_group):
                end = words_in_group[j + 1]["start"]
            else:
                end = active_word["end"]

            entries.append(
                f"{idx}\n"
                f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n"
                f"{' '.join(parts)}\n"
            )
            idx += 1

        i = group_end

    return "\n".join(entries)


def generate_word_timestamps_from_script(
    voiceover_text: str,
    total_duration: float,
) -> list[dict]:
    """Estimate word-level timestamps from text when real timestamps aren't available.

    Distributes words evenly across the duration. This is a fallback —
    real word timestamps from Nova Sonic are preferred.
    """
    words = voiceover_text.split()
    if not words:
        return []

    time_per_word = total_duration / len(words)
    timestamps = []

    for i, word in enumerate(words):
        timestamps.append({
            "word": word,
            "start": round(i * time_per_word, 3),
            "end": round((i + 1) * time_per_word, 3),
        })

    return timestamps
