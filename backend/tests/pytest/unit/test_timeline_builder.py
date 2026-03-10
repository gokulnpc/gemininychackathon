"""Tests for services/content/timeline_builder.py

Run:  cd backend && pytest tests/pytest/unit/test_timeline_builder.py -v
Cov:  cd backend && pytest tests/pytest/unit/test_timeline_builder.py --cov=services.content.timeline_builder --cov-report=term-missing
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from models.schemas import CTA, Hook, Scene, ScriptGenerationResponse
from services.content.timeline_builder import (
    AudioTrackSpec,
    CaptionTrackSpec,
    OverlayElementSpec,
    SceneAssetSpec,
    TimelineBuildSpec,
    _build_from_spec,
    build_project_timeline,
)

# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

_DET_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _det_now() -> datetime:
    return _DET_NOW


@pytest.fixture()
def det_id_factory():
    """Return a callable that yields deterministic IDs: 000000000000, 000000000001, ..."""
    counter = itertools.count()

    def _factory() -> str:
        return f"{next(counter):012d}"

    return _factory


@pytest.fixture()
def script() -> ScriptGenerationResponse:
    """Minimal two-scene ScriptGenerationResponse for timeline tests."""
    return ScriptGenerationResponse(
        metadata={},
        hook=Hook(text="Did you know?", duration=3),
        scenes=[
            Scene(scene_id=1, duration_seconds=5, voiceover_text="Scene one text", visual_prompt="A dramatic scene"),
            Scene(scene_id=2, duration_seconds=5, voiceover_text="Scene two text", visual_prompt="Another scene"),
        ],
        cta=CTA(text="Subscribe now"),
        voiceover_full_script="Scene one text Scene two text",
    )


@pytest.fixture()
def _build(script, sample_words, det_id_factory):
    """Return a helper that calls build_project_timeline with sensible defaults."""
    project_id = UUID("12345678-1234-5678-1234-567812345678")

    def _call(
        *,
        scene_gcs_urls=None,
        voiceover_gcs_url="gs://bucket/vo.wav",
        word_timestamps=None,
        caption_style="bold_stroke",
        music_preset="upbeat",
        music_volume=0.5,
        scene_image_gcs_urls=None,
        overlay_elements=None,
        id_factory=None,
        now_factory=_det_now,
    ):
        return build_project_timeline(
            project_id=project_id,
            script=script,
            scene_gcs_urls=scene_gcs_urls or ["gs://bucket/s1.mp4", "gs://bucket/s2.mp4"],
            voiceover_gcs_url=voiceover_gcs_url,
            word_timestamps=word_timestamps if word_timestamps is not None else sample_words,
            caption_style=caption_style,
            music_preset=music_preset,
            music_volume=music_volume,
            scene_image_gcs_urls=scene_image_gcs_urls,
            overlay_elements=overlay_elements,
            id_factory=id_factory or det_id_factory,
            now_factory=now_factory,
        )

    return _call


# ---------------------------------------------------------------------------
# Track-count and structure tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_basic_build_four_tracks(_build):
    """Full build with two scenes, voiceover, and captions produces exactly 4 tracks."""
    project = _build()
    assert len(project.tracks) == 4


@pytest.mark.unit
def test_scene_track_names(_build):
    """Scene tracks are named Scene_1 and Scene_2."""
    project = _build()
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    names = {t.name for t in scene_tracks}
    assert names == {"Scene_1", "Scene_2"}


@pytest.mark.unit
def test_scene_element_timing(_build):
    """First scene runs 0.0-5.0 and second scene runs 5.0-10.0."""
    project = _build()
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    timings = {}
    for track in scene_tracks:
        video_elem = next(e for e in track.elements if e.type == "video")
        timings[track.name] = (video_elem.s, video_elem.e)
    assert timings["Scene_1"] == (0.0, 5.0)
    assert timings["Scene_2"] == (5.0, 10.0)


@pytest.mark.unit
def test_scene_element_src_matches_url(_build):
    """Video element src props match the supplied GCS URLs."""
    urls = ["gs://bucket/scene1.mp4", "gs://bucket/scene2.mp4"]
    project = _build(scene_gcs_urls=urls)
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    srcs = set()
    for track in scene_tracks:
        video_elem = next(e for e in track.elements if e.type == "video")
        srcs.add(video_elem.props["src"])
    assert srcs == set(urls)


@pytest.mark.unit
def test_scene_video_element_volume_is_zero(_build):
    """Scene video elements have volume == 0 (audio comes from voiceover track)."""
    project = _build()
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    for track in scene_tracks:
        video_elem = next(e for e in track.elements if e.type == "video")
        assert video_elem.props["volume"] == 0


# ---------------------------------------------------------------------------
# Voiceover track tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_voiceover_track_span(_build):
    """Voiceover audio element spans 0.0 to total duration (10.0)."""
    project = _build()
    vo_track = next(t for t in project.tracks if t.name == "Voiceover")
    vo_elem = vo_track.elements[0]
    assert vo_elem.s == 0.0
    assert vo_elem.e == 10.0


@pytest.mark.unit
def test_voiceover_element_volume(_build):
    """Voiceover audio element has volume == 1.0 by default."""
    project = _build()
    vo_track = next(t for t in project.tracks if t.name == "Voiceover")
    assert vo_track.elements[0].props["volume"] == 1.0


@pytest.mark.unit
def test_no_voiceover_url_omits_track(_build):
    """Omitting voiceover_gcs_url removes the Voiceover track entirely."""
    project = _build(voiceover_gcs_url=None)
    track_names = [t.name for t in project.tracks]
    assert "Voiceover" not in track_names


# ---------------------------------------------------------------------------
# Caption track tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_word_timestamps_omits_caption_track(_build):
    """Empty word_timestamps list produces no Captions track."""
    project = _build(word_timestamps=[])
    track_names = [t.name for t in project.tracks]
    assert "Captions" not in track_names


@pytest.mark.unit
def test_caption_track_present_when_words_provided(_build):
    """Non-empty word_timestamps produces a Captions track."""
    project = _build()
    track_names = [t.name for t in project.tracks]
    assert "Captions" in track_names


@pytest.mark.parametrize(
    "style,expected_cap_style",
    [
        ("bold_stroke", "text_bg"),
        ("karaoke", "karaoke"),
        ("unknown_style_xyz", "text_bg"),
    ],
)
@pytest.mark.unit
def test_caption_style_mapping(_build, style, expected_cap_style):
    """Caption style names map correctly to Twick capStyle values."""
    project = _build(caption_style=style)
    cap_track = next(t for t in project.tracks if t.name == "Captions")
    assert cap_track.props["capStyle"] == expected_cap_style


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metadata_fields(_build):
    """Metadata contains correct project_id, total_duration, scene_count, and music_preset."""
    project = _build(music_preset="chill")
    meta = project.metadata
    assert meta["project_id"] == "12345678-1234-5678-1234-567812345678"
    assert meta["total_duration"] == 10.0
    assert meta["scene_count"] == 2
    assert meta["music_preset"] == "chill"


@pytest.mark.unit
def test_metadata_created_at_deterministic(_build):
    """created_at uses the injected now_factory and is deterministic."""
    project = _build(now_factory=_det_now)
    assert project.metadata["created_at"] == _DET_NOW.isoformat()


@pytest.mark.unit
def test_version_is_two(_build):
    """TimelineProject version field is always 2."""
    project = _build()
    assert project.version == 2


# ---------------------------------------------------------------------------
# ValueError tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_volume",
    [1.5, -0.1],
)
@pytest.mark.unit
def test_invalid_music_volume_raises(_build, bad_volume):
    """music_volume outside [0.0, 1.0] raises ValueError with 'music_volume' in message."""
    with pytest.raises(ValueError, match=r"music_volume"):
        _build(music_volume=bad_volume)


@pytest.mark.unit
def test_mismatched_scene_assets_raises(script, sample_words, det_id_factory):
    """Mismatched scene_assets and script.scenes lengths raise ValueError."""
    with pytest.raises(ValueError, match=r"scene_assets length"):
        build_project_timeline(
            project_id=uuid4(),
            script=script,
            scene_gcs_urls=["gs://bucket/only_one.mp4"],  # 1 URL, script has 2 scenes
            voiceover_gcs_url=None,
            word_timestamps=sample_words,
            caption_style="bold_stroke",
            music_preset="none",
            music_volume=0.0,
            id_factory=det_id_factory,
            now_factory=_det_now,
        )


# ---------------------------------------------------------------------------
# Boundary / valid-edge tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valid_volume", [0.0, 1.0])
@pytest.mark.unit
def test_boundary_music_volume_valid(_build, valid_volume):
    """music_volume at exactly 0.0 and 1.0 are both accepted without error."""
    project = _build(music_volume=valid_volume)
    assert project.metadata["total_duration"] == 10.0


# ---------------------------------------------------------------------------
# scene_image_gcs_urls tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scene_image_urls_produce_image_elements(_build):
    """Providing scene_image_gcs_urls adds image elements to each scene track."""
    image_urls = ["gs://bucket/img1.jpg", "gs://bucket/img2.jpg"]
    project = _build(scene_image_gcs_urls=image_urls)
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    for track in scene_tracks:
        image_elems = [e for e in track.elements if e.type == "image"]
        assert len(image_elems) == 1


@pytest.mark.unit
def test_scene_image_element_srcs_match(_build):
    """Image element src props match the supplied image GCS URLs."""
    image_urls = ["gs://bucket/img_a.jpg", "gs://bucket/img_b.jpg"]
    project = _build(scene_image_gcs_urls=image_urls)
    scene_tracks = sorted(
        [t for t in project.tracks if t.name.startswith("Scene_")],
        key=lambda t: t.name,
    )
    collected_srcs = [
        next(e for e in t.elements if e.type == "image").props["src"]
        for t in scene_tracks
    ]
    assert collected_srcs == image_urls


@pytest.mark.unit
def test_no_scene_image_urls_omits_image_elements(_build):
    """Without scene_image_gcs_urls, scene tracks contain only video elements."""
    project = _build(scene_image_gcs_urls=None)
    scene_tracks = [t for t in project.tracks if t.name.startswith("Scene_")]
    for track in scene_tracks:
        image_elems = [e for e in track.elements if e.type == "image"]
        assert len(image_elems) == 0


# ---------------------------------------------------------------------------
# Overlay track tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overlay_elements_produce_overlays_track(_build):
    """Supplying overlay_elements creates an 'Overlays' track with text elements."""
    overlays = [
        OverlayElementSpec(text="Top banner", s=0.0, e=3.0, x=0.1, y=0.05),
        OverlayElementSpec(text="Bottom text", s=5.0, e=8.0, x=0.1, y=0.9),
    ]
    project = _build(overlay_elements=overlays)
    ov_track = next((t for t in project.tracks if t.name == "Overlays"), None)
    assert ov_track is not None
    assert len(ov_track.elements) == 2
    texts = {e.props["text"] for e in ov_track.elements}
    assert texts == {"Top banner", "Bottom text"}


@pytest.mark.unit
def test_no_overlays_omits_overlays_track(_build):
    """Omitting overlay_elements produces no 'Overlays' track."""
    project = _build(overlay_elements=None)
    track_names = [t.name for t in project.tracks]
    assert "Overlays" not in track_names


@pytest.mark.unit
def test_empty_overlays_list_omits_overlays_track(_build):
    """An empty overlay_elements list produces no 'Overlays' track."""
    project = _build(overlay_elements=[])
    track_names = [t.name for t in project.tracks]
    assert "Overlays" not in track_names


# ---------------------------------------------------------------------------
# ID uniqueness test
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_track_and_element_ids_are_unique(_build):
    """All track IDs and element IDs across the entire timeline are unique."""
    overlays = [OverlayElementSpec(text="Banner", s=0.0, e=2.0)]
    image_urls = ["gs://bucket/i1.jpg", "gs://bucket/i2.jpg"]
    project = _build(overlay_elements=overlays, scene_image_gcs_urls=image_urls)

    track_ids = [t.id for t in project.tracks]
    element_ids = [e.id for t in project.tracks for e in t.elements]
    all_ids = track_ids + element_ids

    assert len(all_ids) == len(set(all_ids)), "Duplicate IDs found in timeline"


# ---------------------------------------------------------------------------
# _build_from_spec direct tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_from_spec_single_scene(det_id_factory):
    """_build_from_spec with a single scene produces correct timing and metadata."""
    single_scene_script = ScriptGenerationResponse(
        metadata={},
        hook=Hook(text="Hook!", duration=3),
        scenes=[Scene(scene_id=1, duration_seconds=7, voiceover_text="Only scene")],
        cta=CTA(text="Like and subscribe"),
        voiceover_full_script="Only scene",
    )
    spec = TimelineBuildSpec(
        project_id=uuid4(),
        script=single_scene_script,
        scene_assets=[SceneAssetSpec(video_url="gs://bucket/only.mp4")],
        voiceover=None,
        captions=None,
    )
    project = _build_from_spec(spec, id_factory=det_id_factory, now_factory=_det_now)
    assert len(project.tracks) == 1
    assert project.metadata["total_duration"] == 7.0
    assert project.metadata["scene_count"] == 1


@pytest.mark.unit
def test_build_from_spec_mismatched_raises(script, det_id_factory):
    """_build_from_spec raises ValueError when scene_assets count != scenes count."""
    spec = TimelineBuildSpec(
        project_id=uuid4(),
        script=script,
        scene_assets=[SceneAssetSpec(video_url="gs://bucket/only.mp4")],
    )
    with pytest.raises(ValueError, match=r"scene_assets length"):
        _build_from_spec(spec, id_factory=det_id_factory, now_factory=_det_now)


@pytest.mark.unit
def test_build_from_spec_invalid_volume_raises(script, det_id_factory):
    """_build_from_spec raises ValueError when music_volume > 1.0."""
    spec = TimelineBuildSpec(
        project_id=uuid4(),
        script=script,
        scene_assets=[
            SceneAssetSpec(video_url="gs://bucket/s1.mp4"),
            SceneAssetSpec(video_url="gs://bucket/s2.mp4"),
        ],
        music_volume=2.0,
    )
    with pytest.raises(ValueError, match=r"music_volume"):
        _build_from_spec(spec, id_factory=det_id_factory, now_factory=_det_now)


# ---------------------------------------------------------------------------
# Caption props tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "style,expected_font_family",
    [
        ("beast", "Impact"),
        ("bold_stroke", "Arial Black"),
        ("karaoke", "Bangers"),
        ("red_highlight", "Arial Black"),
        ("clarity", "Arial"),
        ("majestic", "Georgia"),
    ],
)
@pytest.mark.unit
def test_caption_style_font_family(_build, style, expected_font_family):
    """Each known caption style maps to the correct font family in track props."""
    project = _build(caption_style=style)
    cap_track = next((t for t in project.tracks if t.name == "Captions"), None)
    if cap_track is None:
        pytest.skip("No captions track produced — check words_to_cues output")
    assert cap_track.props["font"]["family"] == expected_font_family


@pytest.mark.unit
def test_unknown_caption_style_uses_default_props(_build):
    """An unknown caption style falls back to bold_stroke font properties."""
    project = _build(caption_style="totally_unknown")
    cap_track = next(t for t in project.tracks if t.name == "Captions")
    assert cap_track.props["font"]["family"] == "Arial Black"


# ---------------------------------------------------------------------------
# Metadata caption_style field
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metadata_caption_style_set(_build):
    """Metadata caption_style reflects the supplied style string."""
    project = _build(caption_style="karaoke")
    assert project.metadata["caption_style"] == "karaoke"


@pytest.mark.unit
def test_metadata_caption_style_empty_when_no_words(_build):
    """Metadata caption_style is empty string when no word_timestamps are provided."""
    project = _build(word_timestamps=[])
    assert project.metadata["caption_style"] == ""


# ---------------------------------------------------------------------------
# Integration test stubs — run manually with: pytest -m api
# Require: GEMINI_API_KEY, GCP ADC (gcloud auth application-default login)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.skip(reason="Requires live pipeline outputs — run manually")
async def test_build_project_timeline_real_assets():
    """Live build_project_timeline call — validates end-to-end timeline construction with real GCS URLs."""
    pass
