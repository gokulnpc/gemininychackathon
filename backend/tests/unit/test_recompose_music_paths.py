from __future__ import annotations

from pathlib import Path

from services.infra import recompose


def test_recompose_music_dir_points_to_backend_assets_music():
    music_dir = Path(recompose._MUSIC_DIR)

    assert music_dir.name == "music"
    assert music_dir.parent.name == "assets"
    assert music_dir.exists()


def test_recompose_music_dir_contains_static_presets():
    music_dir = Path(recompose._MUSIC_DIR)

    expected = {
        "happy_rhythm.mp3",
        "quiet_before_storm.mp3",
        "peaceful_vibes.mp3",
        "brilliant_symphony.mp3",
        "breathing_shadows.mp3",
    }

    assert expected.issubset({path.name for path in music_dir.iterdir()})
