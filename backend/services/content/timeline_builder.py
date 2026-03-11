"""Build a Twick-compatible TimelineProject from VoiceVid pipeline outputs.

The resulting TimelineProject can be serialised to JSON and stored in Firestore
under `project_json`, then loaded directly by the Twick SDK editor on the frontend.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from models.project_timeline import ElementFrame, TimelineElement, TimelineProject, TimelineTrack
from models.schemas import ScriptGenerationResponse
from services.media.captions import CAPTION_STYLE_REGISTRY, build_track, resolve_caption_style

# ── Constants ─────────────────────────────────────────────────────────────────

# Scene clip output dimensions (matches ffmpeg.animate_image defaults)
SCENE_WIDTH = 576
SCENE_HEIGHT = 1024

_CAP_STYLE_MAP: dict[str, str] = {
    style: definition.get("twick_cap_style", "text_bg")
    for style, definition in CAPTION_STYLE_REGISTRY.items()
    if "inherits" not in definition
}

_STATIC_MUSIC_PRESETS = {
    "happy_rhythm",
    "quiet_before_storm",
    "peaceful_vibes",
    "brilliant_symphony",
    "breathing_shadows",
}


# ── Spec dataclasses ───────────────────────────────────────────────────────────


@dataclass
class SceneAssetSpec:
    """Canonical editable asset for a single scene."""
    image_url: str | None = None
    video_url: str | None = None
    motion_effect: str | None = None
    transition_to_next: str | None = None


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
    duration_seconds: float | None = None


@dataclass
class CaptionTrackSpec:
    """Caption configuration with word-level timestamps."""
    word_timestamps: list[dict]
    style: str = "bold_stroke"
    timing_source: str = "unknown"


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


def _validate_scene_assets(scene_assets: list[SceneAssetSpec]) -> None:
    for idx, asset in enumerate(scene_assets, start=1):
        if not asset.image_url and not asset.video_url:
            raise ValueError(f"scene asset {idx} must include image_url or video_url")


def _safe_round(value: float) -> float:
    return round(float(value), 3)


def _normalize_audio_duration(audio_duration: float | None) -> float | None:
    if audio_duration is None:
        return None
    if audio_duration <= 0:
        raise ValueError(f"voiceover duration must be > 0, got {audio_duration}")
    return float(audio_duration)


def _clamp_caption_timestamps(
    word_timestamps: list[dict[str, Any]],
    audio_duration: float | None,
) -> list[dict[str, Any]]:
    if audio_duration is None:
        return word_timestamps

    clamped: list[dict[str, Any]] = []
    for word in word_timestamps:
        start = max(0.0, min(float(word.get("start", 0.0)), audio_duration))
        end = max(start, min(float(word.get("end", start)), audio_duration))
        if end <= start:
            continue
        clamped.append({
            **word,
            "start": start,
            "end": end,
        })
    return clamped


def _find_primary_scene_element(track: TimelineTrack) -> TimelineElement | None:
    for element in track.elements:
        if element.type in {"image", "video"}:
            return element
    return None


def get_music_preview_src(music_preset: str) -> str | None:
    """Return a frontend-playable preview URL for static music presets."""
    if music_preset not in _STATIC_MUSIC_PRESETS:
        return None
    return f"/music/{music_preset}.mp3"


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
    _validate_scene_assets(spec.scene_assets)
    if not (0.0 <= spec.music_volume <= 1.0):
        raise ValueError(f"music_volume must be in [0.0, 1.0], got {spec.music_volume}")
    audio_duration = _normalize_audio_duration(spec.voiceover.duration_seconds) if spec.voiceover else None

    tracks: list[TimelineTrack] = []
    scene_image_assets: list[dict[str, Any]] = []
    scene_video_assets: list[dict[str, Any]] = []
    caption_style_key = ""
    caption_style_def: dict[str, Any] = {}

    # ── 1. Scene tracks ───────────────────────────────────────────────────────
    cursor = 0.0
    for idx, (scene, asset) in enumerate(zip(spec.script.scenes, spec.scene_assets)):
        duration = float(getattr(scene, "duration_seconds", 2) or 2)
        track_id = f"t-scene-{id_factory()}"
        start_time = _safe_round(cursor)
        end_time = _safe_round(cursor + duration)

        base_props: dict[str, Any] = {
            "sceneId": getattr(scene, "scene_id", idx + 1),
            "motionEffect": asset.motion_effect,
            "transitionToNext": asset.transition_to_next,
        }
        elements: list[TimelineElement] = []

        if asset.image_url:
            scene_image_assets.append({
                "scene_index": idx,
                "url": asset.image_url,
                "duration": duration,
            })
            elements.append(TimelineElement(
                id=f"e-img-{id_factory()}",
                trackId=track_id,
                type="image",
                s=start_time,
                e=end_time,
                props={
                    **base_props,
                    "src": asset.image_url,
                    "objectFit": "cover",
                },
                zIndex=idx,
                frame=ElementFrame(size=[SCENE_WIDTH, SCENE_HEIGHT], x=0.0, y=0.0),
                objectFit="cover",
                mediaDuration=duration,
            ))
        elif asset.video_url:
            elements.append(TimelineElement(
                id=f"e-scene-{id_factory()}",
                trackId=track_id,
                type="video",
                s=start_time,
                e=end_time,
                props={
                    **base_props,
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

        if asset.video_url:
            scene_video_assets.append({
                "scene_index": idx,
                "url": asset.video_url,
                "duration": duration,
            })

        tracks.append(TimelineTrack(
            id=track_id,
            name=f"Scene_{idx + 1}",
            type="element",
            elements=elements,
        ))
        cursor += duration

    scene_total_duration = cursor

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
                e=_safe_round(audio_duration or scene_total_duration),
                props={
                    "src": spec.voiceover.url,
                    "time": 0,
                    "playbackRate": 1,
                    "volume": spec.voiceover.volume,
                    "loop": spec.voiceover.loop,
                },
                mediaDuration=_safe_round(audio_duration or scene_total_duration),
            )],
        ))

    # ── 3. Background music preview track ────────────────────────────────────
    music_preview_src = get_music_preview_src(spec.music_preset)
    if music_preview_src:
        music_track_id = f"t-music-{id_factory()}"
        tracks.append(TimelineTrack(
            id=music_track_id,
            name="Background Music",
            type="element",
            elements=[TimelineElement(
                id=f"e-music-{id_factory()}",
                trackId=music_track_id,
                type="audio",
                s=0.0,
                e=_safe_round(scene_total_duration),
                props={
                    "src": music_preview_src,
                    "time": 0,
                    "playbackRate": 1,
                    "volume": spec.music_volume,
                    "loop": True,
                    "musicPreset": spec.music_preset,
                },
                mediaDuration=_safe_round(scene_total_duration),
                name="Background Music",
            )],
        ))

    # ── 4. Overlay track ──────────────────────────────────────────────────────
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

    # ── 5. Caption track ──────────────────────────────────────────────────────
    if spec.captions and spec.captions.word_timestamps:
        caption_words = _clamp_caption_timestamps(spec.captions.word_timestamps, audio_duration)
        caption_track = build_track(caption_words, spec.captions.style)
        style_key, style_def = resolve_caption_style(spec.captions.style)
        caption_style_key = style_key
        caption_style_def = style_def
        cues = caption_track.cues

        cap_style_key = style_def["twick_cap_style"]
        cap_props_template = style_def["twick_props"]

        cap_track_id = f"t-captions-{id_factory()}"
        caption_elements: list[TimelineElement] = []

        for cue in cues:
            cue_start = _safe_round(cue.start)
            cue_end = _safe_round(cue.end)
            if cue_end <= cue_start:
                continue
            caption_elements.append(TimelineElement(
                id=f"e-cap-{id_factory()}",
                trackId=cap_track_id,
                type="caption",
                s=cue_start,
                e=cue_end,
                props={
                    "words": [
                        {
                            "text": word.word,
                            "s": _safe_round(word.start),
                            "e": _safe_round(word.end),
                        }
                        for word in cue.words
                    ],
                },
                t=cue.text,
            ))

        if caption_elements:
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

    last_caption_end = max(
        (element.e for track in tracks if track.name == "Captions" for element in track.elements),
        default=0.0,
    )
    project_end_time = max(scene_total_duration, audio_duration or 0.0, last_caption_end)
    final_visual_original_end = _safe_round(scene_total_duration)
    final_visual_effective_end = final_visual_original_end
    final_visual_extended = False

    if tracks and project_end_time > scene_total_duration:
        for track in reversed(tracks):
            primary_element = _find_primary_scene_element(track)
            if primary_element is None:
                continue
            primary_element.e = _safe_round(project_end_time)
            primary_element.mediaDuration = _safe_round(project_end_time - primary_element.s)
            final_visual_effective_end = primary_element.e
            final_visual_extended = True
            break

    total_duration = project_end_time
    timeline_build_mode = "image_canonical" if scene_image_assets else "video_fallback"
    artifact_manifest = {
        "scene_image_urls": [asset.image_url for asset in spec.scene_assets if asset.image_url],
        "scene_video_urls": [asset.video_url for asset in spec.scene_assets if asset.video_url],
        "voiceover_url": spec.voiceover.url if spec.voiceover else None,
        "actual_voiceover_duration": _safe_round(audio_duration) if audio_duration else None,
        "caption_timing_source": spec.captions.timing_source if spec.captions else "",
        "timeline_build_mode": timeline_build_mode,
        "caption_payload_mode": "phrase_with_words" if spec.captions and spec.captions.word_timestamps else "",
        "caption_render_mode": caption_style_def.get("export_mode", "") if spec.captions else "",
        "caption_style_requested": spec.captions.style if spec.captions else "",
        "caption_style_effective": caption_style_key if spec.captions else "",
        "caption_degraded": False,
        "final_visual_extended": final_visual_extended,
        "final_visual_original_end": final_visual_original_end,
        "final_visual_effective_end": final_visual_effective_end,
        "visual_end_policy": "extend_last_scene",
    }

    return TimelineProject(
        tracks=tracks,
        version=2,
        metadata={
            "project_id": str(spec.project_id),
            "pipeline_version": "1.0",
            "created_at": now_factory().isoformat(),
            "caption_style": spec.captions.style if spec.captions else "",
            "music_preset": spec.music_preset,
            "total_duration": _safe_round(total_duration),
            "scene_total_duration": _safe_round(scene_total_duration),
            "scene_count": len(spec.script.scenes),
            "voiceover_duration": _safe_round(audio_duration) if audio_duration else None,
            "caption_timing_source": spec.captions.timing_source if spec.captions else "",
            "timeline_build_mode": timeline_build_mode,
            "caption_payload_mode": "phrase_with_words" if spec.captions and spec.captions.word_timestamps else "",
            "caption_render_mode": caption_style_def.get("export_mode", "") if spec.captions else "",
            "caption_style_requested": spec.captions.style if spec.captions else "",
            "caption_style_effective": caption_style_key if spec.captions else "",
            "caption_degraded": False,
            "final_visual_extended": final_visual_extended,
            "final_visual_original_end": final_visual_original_end,
            "final_visual_effective_end": final_visual_effective_end,
            "visual_end_policy": "extend_last_scene",
            "artifact_manifest": artifact_manifest,
        },
        assets={
            "scene_images": scene_image_assets,
            "scene_videos": scene_video_assets,
            "voiceover": {
                "url": spec.voiceover.url,
                "duration": _safe_round(audio_duration) if audio_duration else None,
            } if spec.voiceover else {},
        },
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def build_project_timeline(
    project_id: UUID,
    script: ScriptGenerationResponse,
    scene_gcs_urls: list[str] | None,
    voiceover_gcs_url: str | None,
    word_timestamps: list[dict],
    caption_style: str,
    music_preset: str,
    music_volume: float,
    *,
    scene_image_gcs_urls: list[str | None] | None = None,
    voiceover_duration_seconds: float | None = None,
    caption_timing_source: str = "unknown",
    scene_motion_effects: list[str | None] | None = None,
    scene_transitions: list[str | None] | None = None,
    overlay_elements: list[OverlayElementSpec] | None = None,
    id_factory: Callable[[], str] = _uid,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> TimelineProject:
    """Build a Twick-compatible TimelineProject from pipeline outputs.

    Args:
        project_id: The project UUID (used in metadata).
        script: Fully populated script with scenes and timing.
        scene_gcs_urls: Optional GCS public URLs for animated scene clips (index-aligned with script.scenes).
        voiceover_gcs_url: GCS URL for the voiceover asset, or None if TTS failed.
        word_timestamps: Per-word timestamps [{"word", "start", "end"}, ...].
        caption_style: Pipeline caption style key (e.g. "bold_stroke").
        music_preset: Music preset key (e.g. "happy_rhythm") or "none".
        music_volume: Background music mix volume (0.0–1.0).
        scene_image_gcs_urls: Optional per-scene still-image URLs (index-aligned).
        voiceover_duration_seconds: Actual uploaded voiceover duration in seconds.
        caption_timing_source: Timestamp provenance ("stt", "estimated", ...).
        scene_motion_effects: Optional per-scene motion effect names.
        scene_transitions: Optional per-scene transition names.
        overlay_elements: Optional list of OverlayElementSpec for text overlays.
        id_factory: Callable returning a unique string ID (injectable for testing).
        now_factory: Callable returning current datetime (injectable for testing).

    Returns:
        A TimelineProject ready for .model_dump() serialisation.

    Raises:
        ValueError: if scene asset inputs are misaligned or invalid, or
                    if music_volume is outside [0.0, 1.0].
    """
    scene_video_urls = scene_gcs_urls or []
    scene_count = len(script.scenes)
    image_urls = scene_image_gcs_urls or ([None] * scene_count)
    video_urls = scene_video_urls or ([None] * scene_count)
    motion_effects = scene_motion_effects or ([None] * scene_count)
    transitions = scene_transitions or ([None] * scene_count)
    lengths = {
        "scene_image_gcs_urls": len(image_urls),
        "scene_gcs_urls": len(video_urls),
        "scene_motion_effects": len(motion_effects),
        "scene_transitions": len(transitions),
    }
    for label, size in lengths.items():
        if size != scene_count:
            raise ValueError(f"{label} length ({size}) != script.scenes length ({scene_count})")

    scene_assets = [
        SceneAssetSpec(
            image_url=image_urls[idx],
            video_url=video_urls[idx],
            motion_effect=motion_effects[idx],
            transition_to_next=transitions[idx],
        )
        for idx in range(scene_count)
    ]

    spec = TimelineBuildSpec(
        project_id=project_id,
        script=script,
        scene_assets=scene_assets,
        voiceover=AudioTrackSpec(
            url=voiceover_gcs_url,
            duration_seconds=voiceover_duration_seconds,
        ) if voiceover_gcs_url else None,
        captions=CaptionTrackSpec(
            word_timestamps=word_timestamps,
            style=caption_style,
            timing_source=caption_timing_source,
        ) if word_timestamps else None,
        overlays=overlay_elements or [],
        music_preset=music_preset,
        music_volume=music_volume,
    )
    return _build_from_spec(spec, id_factory=id_factory, now_factory=now_factory)
