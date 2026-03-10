"""Build a Twick-compatible TimelineProject from VoiceVid pipeline outputs.

The resulting TimelineProject can be serialised to JSON and stored in Firestore
under `project_json`, then loaded directly by the Twick SDK editor on the frontend.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from models.project_timeline import ElementFrame, TimelineElement, TimelineProject, TimelineTrack
from models.schemas import ScriptGenerationResponse
from services.media.captions import words_to_cues

# ── Constants ─────────────────────────────────────────────────────────────────

# Scene clip output dimensions (matches ffmpeg.animate_image defaults)
SCENE_WIDTH = 576
SCENE_HEIGHT = 1024


# Map pipeline caption_style → Twick capStyle
_CAP_STYLE_MAP: dict[str, str] = {
    "bold_stroke": "text_bg",
    "beast": "text_bg",
    "karaoke": "karaoke",
    "red_highlight": "highlight_bg",
    "clarity": "text_bg",
    "majestic": "text_bg",
    "sleek": "text_bg",
    "clean": "text_bg",
    "elegant": "text_bg",
}

# Default font/color props per caption style
_CAP_PROPS: dict[str, dict] = {
    "beast": {
        "font": {"size": 60, "weight": 900, "family": "Impact"},
        "colors": {"text": "#ffffff", "highlight": "#ff0000", "bgColor": "transparent"},
        "stroke": "#000000",
        "shadowOffset": [0, 4],
        "shadowColor": "#000000",
    },
    "bold_stroke": {
        "font": {"size": 52, "weight": 700, "family": "Arial Black"},
        "colors": {"text": "#ffffff", "highlight": "#ff4081", "bgColor": "#00000080"},
        "stroke": "#000000",
        "shadowOffset": [-2, 2],
        "shadowColor": "#000000",
    },
    "karaoke": {
        "font": {"size": 46, "weight": 700, "family": "Bangers"},
        "colors": {"text": "#ffffff", "highlight": "#ffd700", "bgColor": "transparent"},
        "stroke": "#000000",
        "shadowOffset": [0, 2],
        "shadowColor": "#000000",
    },
    "red_highlight": {
        "font": {"size": 48, "weight": 700, "family": "Arial Black"},
        "colors": {"text": "#ffffff", "highlight": "#ff0000", "bgColor": "#ff0000"},
        "stroke": "#000000",
        "shadowOffset": [0, 0],
        "shadowColor": "#000000",
    },
    "clarity": {
        "font": {"size": 36, "weight": 400, "family": "Arial"},
        "colors": {"text": "#cccccc", "highlight": "#ffffff", "bgColor": "transparent"},
        "stroke": "#000000",
        "shadowOffset": [0, 1],
        "shadowColor": "#000000",
    },
    "majestic": {
        "font": {"size": 50, "weight": 700, "family": "Georgia"},
        "colors": {"text": "#ffffff", "highlight": "#ffd700", "bgColor": "transparent"},
        "stroke": "#000000",
        "shadowOffset": [-2, 4],
        "shadowColor": "#444444",
    },
}
_DEFAULT_CAP_PROPS = _CAP_PROPS["bold_stroke"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]




# ── Main builder ──────────────────────────────────────────────────────────────

def build_project_timeline(
    project_id: UUID,
    script: ScriptGenerationResponse,
    scene_gcs_urls: list[str],
    voiceover_gcs_url: str | None,
    word_timestamps: list[dict],
    caption_style: str,
    music_preset: str,
    music_volume: float,
) -> TimelineProject:
    """Build a Twick-compatible TimelineProject from pipeline outputs.

    Args:
        project_id: The project UUID (used in metadata).
        script: Fully populated script with scenes and timing.
        scene_gcs_urls: GCS public URLs for each animated scene clip (index-aligned with script.scenes).
        voiceover_gcs_url: GCS URL for the voiceover MP3, or None if TTS failed.
        word_timestamps: Per-word timestamps [{"word", "start", "end"}, ...].
        caption_style: Pipeline caption style key (e.g. "bold_stroke").
        music_preset: Music preset key (e.g. "happy_rhythm") or "none".
        music_volume: Background music mix volume (0.0–1.0).

    Returns:
        A TimelineProject ready for .model_dump() serialisation.
    """
    tracks: list[TimelineTrack] = []

    # ── 1. Scene video tracks ─────────────────────────────────────────────────
    cursor = 0.0  # running timeline position (seconds)
    for idx, (scene, src_url) in enumerate(zip(script.scenes, scene_gcs_urls)):
        duration = float(getattr(scene, "duration_seconds", 2) or 2)
        track_id = f"t-scene-{_uid()}"
        elem_id = f"e-scene-{_uid()}"

        element = TimelineElement(
            id=elem_id,
            trackId=track_id,
            type="video",
            s=round(cursor, 3),
            e=round(cursor + duration, 3),
            props={
                "src": src_url,
                "playbackRate": 1,
                "time": 0,
                "mediaFilter": "none",
                "volume": 0,   # scene clips have no audio (voiceover is separate)
                "zIndex": idx + 1,
            },
            zIndex=idx + 1,
            frame=ElementFrame(size=[SCENE_WIDTH, SCENE_HEIGHT], x=0.0, y=0.0),
            frameEffects=[],
            objectFit="cover",
            mediaDuration=duration,
        )

        tracks.append(TimelineTrack(
            id=track_id,
            name=f"Scene_{idx + 1}",
            type="element",
            elements=[element],
        ))
        cursor += duration

    total_duration = cursor

    # ── 2. Voiceover audio track ──────────────────────────────────────────────
    if voiceover_gcs_url:
        vo_track_id = f"t-vo-{_uid()}"
        tracks.append(TimelineTrack(
            id=vo_track_id,
            name="Voiceover",
            type="element",
            elements=[TimelineElement(
                id=f"e-vo-{_uid()}",
                trackId=vo_track_id,
                type="audio",
                s=0.0,
                e=round(total_duration, 3),
                props={
                    "src": voiceover_gcs_url,
                    "time": 0,
                    "playbackRate": 1,
                    "volume": 1.0,
                    "loop": False,
                },
                mediaDuration=round(total_duration, 3),
            )],
        ))

    # Background music is generated by Lyria during recompose and mixed into
    # the final MP4 — no static audio URL exists at edit time, so no track here.

    # ── 4. Caption track ──────────────────────────────────────────────────────
    if word_timestamps:
        cues = words_to_cues(word_timestamps, caption_style)

        cap_style_key = _CAP_STYLE_MAP.get(caption_style, "text_bg")
        cap_props_template = _CAP_PROPS.get(caption_style, _DEFAULT_CAP_PROPS)

        cap_track_id = f"t-captions-{_uid()}"
        caption_elements: list[TimelineElement] = []

        for cue in cues:
            caption_elements.append(TimelineElement(
                id=f"e-cap-{_uid()}",
                trackId=cap_track_id,
                type="caption",
                s=round(cue.start, 3),
                e=round(cue.end, 3),
                props={},
                t=cue.text,
            ))

        tracks.append(TimelineTrack(
            id=cap_track_id,
            name="Captions",
            type="caption",
            props={
                "capStyle": cap_style_key,
                "font": cap_props_template.get("font", {}),
                "colors": cap_props_template.get("colors", {}),
                "lineWidth": 0.35,
                "stroke": cap_props_template.get("stroke", "#000000"),
                "fontWeight": cap_props_template.get("font", {}).get("weight", 700),
                "shadowOffset": cap_props_template.get("shadowOffset", [0, 0]),
                "shadowColor": cap_props_template.get("shadowColor", "#000000"),
                "x": 0,
                "y": 150,
                "applyToAll": True,
            },
            elements=caption_elements,
        ))

    return TimelineProject(
        tracks=tracks,
        version=1,
        metadata={
            "project_id": str(project_id),
            "pipeline_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "caption_style": caption_style,
            "music_preset": music_preset,
            "total_duration": round(total_duration, 3),
            "scene_count": len(script.scenes),
        },
    )
