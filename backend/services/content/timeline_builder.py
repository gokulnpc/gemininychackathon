"""Build a Twick-compatible TimelineProject from VoiceVid pipeline outputs.

The resulting TimelineProject can be serialised to JSON and stored in Firestore
under `project_json`, then loaded directly by the Twick SDK editor on the frontend.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Callable
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

# ── Spec dataclasses ───────────────────────────────────────────────────────────


@dataclass
class SceneAssetSpec:
    """Video URL (required) + optional still-image overlay for a single scene."""
    video_url: str
    image_url: str | None = None


@dataclass
class OverlayElementSpec:
    """A text overlay placed at a specific time window on the canvas."""
    text: str
    s: float          # start time (seconds)
    e: float          # end time (seconds)
    x: float = 0.0
    y: float = 0.0
    font_size: int = 32
    color: str = "#ffffff"


@dataclass
class AudioTrackSpec:
    """A single audio asset (voiceover or music)."""
    url: str
    volume: float = 1.0
    loop: bool = False


@dataclass
class CaptionTrackSpec:
    """Caption configuration with word-level timestamps."""
    word_timestamps: list[dict]
    style: str = "bold_stroke"


@dataclass
class TimelineBuildSpec:
    """Fully-typed input spec for the timeline builder."""
    project_id: UUID
    script: ScriptGenerationResponse
    scene_assets: list[SceneAssetSpec]
    voiceover: AudioTrackSpec | None = None
    captions: CaptionTrackSpec | None = None
    overlays: list[OverlayElementSpec] = dc_field(default_factory=list)
    music_preset: str = "none"
    music_volume: float = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ── Core builder (accepts spec + injectable factories) ─────────────────────────

def _build_from_spec(
    spec: TimelineBuildSpec,
    id_factory: Callable[[], str] = _uid,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> TimelineProject:
    """Build a TimelineProject from a fully-typed TimelineBuildSpec.

    Raises:
        ValueError: if scene_assets length != script.scenes length, or
                    if music_volume is outside [0.0, 1.0].
    """
    # ── Validation ────────────────────────────────────────────────────────────
    if len(spec.scene_assets) != len(spec.script.scenes):
        raise ValueError(
            f"scene_assets length ({len(spec.scene_assets)}) != "
            f"script.scenes length ({len(spec.script.scenes)})"
        )
    if not (0.0 <= spec.music_volume <= 1.0):
        raise ValueError(f"music_volume must be in [0.0, 1.0], got {spec.music_volume}")

    tracks: list[TimelineTrack] = []

    # ── 1. Scene video tracks ─────────────────────────────────────────────────
    cursor = 0.0
    for idx, (scene, asset) in enumerate(zip(spec.script.scenes, spec.scene_assets)):
        duration = float(getattr(scene, "duration_seconds", 2) or 2)
        track_id = f"t-scene-{id_factory()}"
        elem_id = f"e-scene-{id_factory()}"

        elements: list[TimelineElement] = []

        # Optional background image element (behind video)
        if asset.image_url:
            elements.append(TimelineElement(
                id=f"e-img-{id_factory()}",
                trackId=track_id,
                type="image",
                s=round(cursor, 3),
                e=round(cursor + duration, 3),
                props={"src": asset.image_url},
                zIndex=idx,
                frame=ElementFrame(size=[SCENE_WIDTH, SCENE_HEIGHT], x=0.0, y=0.0),
                objectFit="cover",
                mediaDuration=duration,
            ))

        elements.append(TimelineElement(
            id=elem_id,
            trackId=track_id,
            type="video",
            s=round(cursor, 3),
            e=round(cursor + duration, 3),
            props={
                "src": asset.video_url,
                "playbackRate": 1,
                "time": 0,
                "mediaFilter": "none",
                "volume": 0,
                "zIndex": idx + 1,
            },
            zIndex=idx + 1,
            frame=ElementFrame(size=[SCENE_WIDTH, SCENE_HEIGHT], x=0.0, y=0.0),
            frameEffects=[],
            objectFit="cover",
            mediaDuration=duration,
        ))

        tracks.append(TimelineTrack(
            id=track_id,
            name=f"Scene_{idx + 1}",
            type="element",
            elements=elements,
        ))
        cursor += duration

    total_duration = cursor

    # ── 2. Voiceover audio track ──────────────────────────────────────────────
    if spec.voiceover:
        vo_track_id = f"t-vo-{id_factory()}"
        tracks.append(TimelineTrack(
            id=vo_track_id,
            name="Voiceover",
            type="element",
            elements=[TimelineElement(
                id=f"e-vo-{id_factory()}",
                trackId=vo_track_id,
                type="audio",
                s=0.0,
                e=round(total_duration, 3),
                props={
                    "src": spec.voiceover.url,
                    "time": 0,
                    "playbackRate": 1,
                    "volume": spec.voiceover.volume,
                    "loop": spec.voiceover.loop,
                },
                mediaDuration=round(total_duration, 3),
            )],
        ))

    # Background music is generated by Lyria during recompose and mixed into
    # the final MP4 — no static audio URL exists at edit time, so no track here.

    # ── 3. Overlay track ──────────────────────────────────────────────────────
    if spec.overlays:
        ov_track_id = f"t-overlays-{id_factory()}"
        overlay_elements: list[TimelineElement] = []
        for ov in spec.overlays:
            overlay_elements.append(TimelineElement(
                id=f"e-ov-{id_factory()}",
                trackId=ov_track_id,
                type="text",
                s=round(ov.s, 3),
                e=round(ov.e, 3),
                props={
                    "text": ov.text,
                    "x": ov.x,
                    "y": ov.y,
                    "fontSize": ov.font_size,
                    "color": ov.color,
                },
                t=ov.text,
            ))
        tracks.append(TimelineTrack(
            id=ov_track_id,
            name="Overlays",
            type="element",
            elements=overlay_elements,
        ))

    # ── 4. Caption track ──────────────────────────────────────────────────────
    if spec.captions and spec.captions.word_timestamps:
        cues = words_to_cues(spec.captions.word_timestamps, spec.captions.style)

        cap_style_key = _CAP_STYLE_MAP.get(spec.captions.style, "text_bg")
        cap_props_template = _CAP_PROPS.get(spec.captions.style, _DEFAULT_CAP_PROPS)

        cap_track_id = f"t-captions-{id_factory()}"
        caption_elements: list[TimelineElement] = []

        for cue in cues:
            caption_elements.append(TimelineElement(
                id=f"e-cap-{id_factory()}",
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
        version=2,
        metadata={
            "project_id": str(spec.project_id),
            "pipeline_version": "1.0",
            "created_at": now_factory().isoformat(),
            "caption_style": spec.captions.style if spec.captions else "",
            "music_preset": spec.music_preset,
            "total_duration": round(total_duration, 3),
            "scene_count": len(spec.script.scenes),
        },
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def build_project_timeline(
    project_id: UUID,
    script: ScriptGenerationResponse,
    scene_gcs_urls: list[str],
    voiceover_gcs_url: str | None,
    word_timestamps: list[dict],
    caption_style: str,
    music_preset: str,
    music_volume: float,
    *,
    scene_image_gcs_urls: list[str | None] | None = None,
    overlay_elements: list[OverlayElementSpec] | None = None,
    id_factory: Callable[[], str] = _uid,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
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
        scene_image_gcs_urls: Optional per-scene still-image URLs (index-aligned).
        overlay_elements: Optional list of OverlayElementSpec for text overlays.
        id_factory: Callable returning a unique string ID (injectable for testing).
        now_factory: Callable returning current datetime (injectable for testing).

    Returns:
        A TimelineProject ready for .model_dump() serialisation.

    Raises:
        ValueError: if scene_gcs_urls length != script.scenes length, or
                    if music_volume is outside [0.0, 1.0].
    """
    image_urls = scene_image_gcs_urls or ([None] * len(scene_gcs_urls))
    scene_assets = [
        SceneAssetSpec(video_url=v, image_url=i)
        for v, i in zip(scene_gcs_urls, image_urls)
    ]

    spec = TimelineBuildSpec(
        project_id=project_id,
        script=script,
        scene_assets=scene_assets,
        voiceover=AudioTrackSpec(url=voiceover_gcs_url) if voiceover_gcs_url else None,
        captions=CaptionTrackSpec(word_timestamps=word_timestamps, style=caption_style) if word_timestamps else None,
        overlays=overlay_elements or [],
        music_preset=music_preset,
        music_volume=music_volume,
    )
    return _build_from_spec(spec, id_factory=id_factory, now_factory=now_factory)
