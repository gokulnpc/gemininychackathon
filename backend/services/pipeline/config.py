"""Pipeline configuration and series settings resolution."""

from __future__ import annotations

from models.schemas import SeriesConfig

# Duration range string → integer seconds
DURATION_MAP = {
    "15-30": 25,
    "30-40": 35,
    "60+": 60,
}


def resolve_series_settings(
    series: SeriesConfig | None,
    video_duration: int,
    caption_style_override: str,
) -> dict:
    """Merge series config with request defaults; series always wins."""
    return {
        "voice_id": series.voice_id if series else "Aoede",
        "language": series.language if series else "en-US",
        "art_style": series.art_style.value if series else "realism",
        "video_format": series.video_format.value if series else "storytelling",
        "niche": series.niche if series else None,
        "caption_style": series.caption_style.value if series else caption_style_override,
        "music_preset": series.background_music.value if series else "none",
        "music_volume": series.music_volume if series else 0.15,
        "resolved_duration": (
            DURATION_MAP.get(series.video_duration.value, video_duration)
            if series else video_duration
        ),
    }
