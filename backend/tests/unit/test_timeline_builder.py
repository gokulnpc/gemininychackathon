"""Unit tests for services/content/timeline_builder.py.

Uses deterministic id_factory and now_factory to make all assertions stable.
No external services required — pure unit tests.

Usage:
    cd backend && .venv/bin/python tests/unit/test_timeline_builder.py
"""
from __future__ import annotations

import itertools
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.schemas import CTA, Hook, Scene, ScriptGenerationResponse
from services.content.timeline_builder import OverlayElementSpec, build_project_timeline

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FIXED_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)
_TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
_SCENE_URLS = ["https://gcs/scene1.mp4", "https://gcs/scene2.mp4"]
_VO_URL = "https://gcs/vo.mp3"
_SAMPLE_WORDS = [
    {"word": "Hello", "start": 0.0, "end": 0.5},
    {"word": "world", "start": 0.5, "end": 1.0},
    {"word": "this",  "start": 1.0, "end": 1.4},
    {"word": "is",    "start": 1.4, "end": 1.6},
    {"word": "a",     "start": 1.6, "end": 1.7},
    {"word": "test",  "start": 1.7, "end": 2.0},
    {"word": "of",    "start": 2.2, "end": 2.4},
    {"word": "captions", "start": 2.4, "end": 3.0},
]


def _make_script() -> ScriptGenerationResponse:
    return ScriptGenerationResponse(
        metadata={"agent_quality_score": 82, "hook_type": "mystery"},
        hook=Hook(text="Did you know this one thing?"),
        scenes=[
            Scene(scene_id=1, duration_seconds=5, voiceover_text="The giraffe walked slowly.",
                  visual_prompt="A giraffe in a golden savanna", emotion="calm"),
            Scene(scene_id=2, duration_seconds=5, voiceover_text="And then it ran.",
                  visual_prompt="A giraffe running at sunset", emotion="exciting"),
        ],
        cta=CTA(text="Follow for more wildlife facts"),
        voiceover_full_script="The giraffe walked slowly. And then it ran.",
    )


def _det_id_factory():
    counter = itertools.count()
    return lambda: f"id{next(counter):04d}"


def _det_now() -> datetime:
    return _FIXED_NOW


def _build(
    script=None,
    *,
    urls=None,
    vo=True,
    words=True,
    caption_style="bold_stroke",
    music_volume=0.0,
    det_ids=None,
    **kw,
):
    return build_project_timeline(
        project_id=_TEST_PROJECT_ID,
        script=script or _make_script(),
        scene_gcs_urls=urls or _SCENE_URLS,
        voiceover_gcs_url=_VO_URL if vo else None,
        word_timestamps=_SAMPLE_WORDS if words else [],
        caption_style=caption_style,
        music_preset="none",
        music_volume=music_volume,
        id_factory=det_ids or _det_id_factory(),
        now_factory=_det_now,
        **kw,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_basic_build_track_count():
    result = _build()
    assert len(result.tracks) == 4, f"Expected 4 tracks (2 scene + vo + captions), got {len(result.tracks)}"
    print("  ✓ basic build: 4 tracks")


def test_scene_track_names():
    result = _build()
    scene_names = [t.name for t in result.tracks if t.name.startswith("Scene_")]
    assert scene_names == ["Scene_1", "Scene_2"]
    print("  ✓ scene track names")


def test_scene_element_timing():
    result = _build()
    scene_tracks = [t for t in result.tracks if t.name.startswith("Scene_")]
    el1 = scene_tracks[0].elements[-1]
    el2 = scene_tracks[1].elements[-1]
    assert el1.s == 0.0 and el1.e == 5.0
    assert el2.s == 5.0 and el2.e == 10.0
    print("  ✓ scene element timing")


def test_scene_element_src():
    result = _build()
    scene_tracks = [t for t in result.tracks if t.name.startswith("Scene_")]
    assert scene_tracks[0].elements[-1].props["src"] == _SCENE_URLS[0]
    assert scene_tracks[1].elements[-1].props["src"] == _SCENE_URLS[1]
    print("  ✓ scene element src")


def test_scene_element_volume_zero():
    result = _build()
    scene_tracks = [t for t in result.tracks if t.name.startswith("Scene_")]
    for track in scene_tracks:
        video_el = next(e for e in track.elements if e.type == "video")
        assert video_el.props["volume"] == 0
    print("  ✓ scene element volume=0")


def test_voiceover_track_span():
    result = _build()
    vo_track = next(t for t in result.tracks if t.name == "Voiceover")
    el = vo_track.elements[0]
    assert el.s == 0.0 and el.e == 10.0
    print("  ✓ voiceover track span")


def test_voiceover_element_volume_one():
    result = _build()
    vo_track = next(t for t in result.tracks if t.name == "Voiceover")
    assert vo_track.elements[0].props["volume"] == 1.0
    print("  ✓ voiceover element volume=1.0")


def test_no_voiceover_omits_track():
    result = _build(vo=False)
    assert "Voiceover" not in [t.name for t in result.tracks]
    print("  ✓ no voiceover → track omitted")


def test_no_word_timestamps_omits_captions():
    result = _build(words=False)
    assert "caption" not in [t.type for t in result.tracks]
    print("  ✓ no word timestamps → caption track omitted")


def test_caption_track_present():
    result = _build()
    cap_track = next((t for t in result.tracks if t.name == "Captions"), None)
    assert cap_track is not None and cap_track.type == "caption"
    print("  ✓ caption track present")


def test_caption_style_mapping_bold_stroke():
    result = _build(caption_style="bold_stroke")
    cap_track = next(t for t in result.tracks if t.name == "Captions")
    assert cap_track.props["capStyle"] == "text_bg"
    print("  ✓ bold_stroke → text_bg")


def test_caption_style_mapping_karaoke():
    result = _build(caption_style="karaoke")
    cap_track = next(t for t in result.tracks if t.name == "Captions")
    assert cap_track.props["capStyle"] == "karaoke"
    print("  ✓ karaoke → karaoke")


def test_unknown_caption_style_fallback():
    result = _build(caption_style="nonexistent_style")
    cap_track = next(t for t in result.tracks if t.name == "Captions")
    assert cap_track.props["capStyle"] == "text_bg"
    print("  ✓ unknown style → text_bg fallback")


def test_metadata_fields():
    result = _build()
    meta = result.metadata
    assert meta["project_id"] == str(_TEST_PROJECT_ID)
    assert meta["total_duration"] == 10.0
    assert meta["scene_count"] == 2
    assert meta["music_preset"] == "none"
    print("  ✓ metadata fields")


def test_metadata_created_at_deterministic():
    result = _build()
    assert result.metadata["created_at"] == "2025-01-01T00:00:00+00:00"
    print("  ✓ created_at deterministic")


def test_version_is_2():
    result = _build()
    assert result.version == 2
    print("  ✓ version == 2")


def test_scene_count_mismatch_raises():
    try:
        _build(urls=["https://gcs/only_one.mp4"])
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "scene_assets length" in str(e)
    print("  ✓ scene count mismatch → ValueError")


def test_music_volume_too_high_raises():
    try:
        _build(music_volume=1.5)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "music_volume" in str(e)
    print("  ✓ music_volume=1.5 → ValueError")


def test_music_volume_too_low_raises():
    try:
        _build(music_volume=-0.1)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "music_volume" in str(e)
    print("  ✓ music_volume=-0.1 → ValueError")


def test_music_volume_boundaries_valid():
    _build(music_volume=0.0)
    _build(music_volume=1.0)
    print("  ✓ music_volume 0.0 and 1.0 are valid")


def test_image_url_per_scene():
    img_urls = ["https://gcs/img1.jpg", "https://gcs/img2.jpg"]
    result = _build(scene_image_gcs_urls=img_urls)
    scene_tracks = [t for t in result.tracks if t.name.startswith("Scene_")]
    for idx, track in enumerate(scene_tracks):
        img_els = [e for e in track.elements if e.type == "image"]
        assert len(img_els) == 1, f"Scene_{idx+1} should have 1 image element"
        assert img_els[0].props["src"] == img_urls[idx]
    print("  ✓ image URLs per scene")


def test_overlay_track():
    overlays = [OverlayElementSpec(text="Hello", s=0.0, e=3.0, x=10.0, y=20.0)]
    result = _build(overlay_elements=overlays)
    ov_track = next((t for t in result.tracks if t.name == "Overlays"), None)
    assert ov_track is not None
    el = ov_track.elements[0]
    assert el.type == "text" and el.t == "Hello" and el.s == 0.0 and el.e == 3.0
    print("  ✓ overlay track")


def test_no_overlays_no_overlay_track():
    result = _build()
    assert "Overlays" not in [t.name for t in result.tracks]
    print("  ✓ no overlays → no Overlays track")


def test_element_and_track_ids_unique():
    img_urls = ["https://gcs/img1.jpg", "https://gcs/img2.jpg"]
    overlays = [OverlayElementSpec(text="A", s=0.0, e=1.0)]
    result = _build(scene_image_gcs_urls=img_urls, overlay_elements=overlays)
    track_ids = [t.id for t in result.tracks]
    assert len(track_ids) == len(set(track_ids)), "Track IDs must be unique"
    elem_ids = [e.id for t in result.tracks for e in t.elements]
    assert len(elem_ids) == len(set(elem_ids)), "Element IDs must be unique"
    print("  ✓ all track and element IDs unique")


# ── Runner ─────────────────────────────────────────────────────────────────────

def main() -> None:
    tests = [
        test_basic_build_track_count,
        test_scene_track_names,
        test_scene_element_timing,
        test_scene_element_src,
        test_scene_element_volume_zero,
        test_voiceover_track_span,
        test_voiceover_element_volume_one,
        test_no_voiceover_omits_track,
        test_no_word_timestamps_omits_captions,
        test_caption_track_present,
        test_caption_style_mapping_bold_stroke,
        test_caption_style_mapping_karaoke,
        test_unknown_caption_style_fallback,
        test_metadata_fields,
        test_metadata_created_at_deterministic,
        test_version_is_2,
        test_scene_count_mismatch_raises,
        test_music_volume_too_high_raises,
        test_music_volume_too_low_raises,
        test_music_volume_boundaries_valid,
        test_image_url_per_scene,
        test_overlay_track,
        test_no_overlays_no_overlay_track,
        test_element_and_track_ids_unique,
    ]

    passed = failed = 0
    for fn in tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─' * 44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
