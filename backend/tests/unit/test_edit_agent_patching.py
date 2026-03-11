from __future__ import annotations

from services.gemini.edit_voice import _patch_project_json


def test_patch_project_json_adds_hook_title_to_overlay_track():
    project_json = {
        "tracks": [
            {"id": "track-audio", "name": "Audio", "type": "element", "elements": []},
        ]
    }

    patched = _patch_project_json(
        project_json,
        {"hook_title": "PREPARE TO BE SCARED", "hook_duration_seconds": 2.5},
        editor_context={"playhead_seconds": 1.25},
    )

    overlay_track = next(track for track in patched["tracks"] if track["name"] == "Overlays")
    element = overlay_track["elements"][0]

    assert element["type"] == "text"
    assert element["t"] == "PREPARE TO BE SCARED"
    assert element["s"] == 1.25
    assert element["e"] == 3.75
    assert element["frame"]["y"] == -540


def test_patch_project_json_moves_selected_text_element():
    project_json = {
        "tracks": [
            {
                "id": "track-1",
                "name": "Overlays",
                "type": "element",
                "elements": [
                    {
                        "id": "text-1",
                        "trackId": "track-1",
                        "type": "text",
                        "s": 0,
                        "e": 2,
                        "frame": {"size": [500, 200], "x": 0, "y": -100, "rotation": 0},
                        "props": {"text": "Hello"},
                    }
                ],
            }
        ]
    }

    patched = _patch_project_json(
        project_json,
        {"move_selected_text_y_delta": -120},
        editor_context={
            "selected_element_ids": ["text-1"],
            "selected_element_types": ["text"],
        },
    )

    element = patched["tracks"][0]["elements"][0]
    assert element["frame"]["y"] == -220


def test_patch_project_json_replaces_selected_media_url():
    project_json = {
        "tracks": [
            {
                "id": "track-1",
                "name": "Scene 1",
                "type": "element",
                "elements": [
                    {
                        "id": "image-1",
                        "trackId": "track-1",
                        "type": "image",
                        "s": 0,
                        "e": 4,
                        "props": {"src": "https://old.example/image.png"},
                    }
                ],
            }
        ]
    }

    patched = _patch_project_json(
        project_json,
        {"replace_selected_media_url": "https://new.example/darker-image.png"},
        editor_context={
            "selected_element_ids": ["image-1"],
            "selected_element_types": ["image"],
        },
    )

    assert patched["tracks"][0]["elements"][0]["props"]["src"] == "https://new.example/darker-image.png"


def test_patch_project_json_adds_background_music_track_for_static_preset():
    project_json = {
        "tracks": [
            {
                "id": "track-scene",
                "name": "Scene 1",
                "type": "element",
                "elements": [
                    {
                        "id": "scene-1",
                        "trackId": "track-scene",
                        "type": "image",
                        "s": 0,
                        "e": 6,
                        "props": {"src": "https://example.com/scene.png"},
                    }
                ],
            }
        ]
    }

    patched = _patch_project_json(
        project_json,
        {"background_music": "quiet_before_storm", "music_volume": 0.2},
    )

    music_track = next(track for track in patched["tracks"] if track["name"] == "Background Music")
    music_element = music_track["elements"][0]

    assert music_element["props"]["src"] == "/music/quiet_before_storm.mp3"
    assert music_element["props"]["musicPreset"] == "quiet_before_storm"
    assert music_element["props"]["volume"] == 0.2
    assert music_element["e"] == 6


def test_patch_project_json_removes_background_music_track_for_none():
    project_json = {
        "tracks": [
            {
                "id": "track-music",
                "name": "Background Music",
                "type": "element",
                "elements": [
                    {
                        "id": "music-1",
                        "trackId": "track-music",
                        "type": "audio",
                        "s": 0,
                        "e": 6,
                        "props": {
                            "src": "/music/breathing_shadows.mp3",
                            "musicPreset": "breathing_shadows",
                            "volume": 0.15,
                        },
                    }
                ],
            }
        ]
    }

    patched = _patch_project_json(project_json, {"background_music": "none"})

    assert all(track["name"] != "Background Music" for track in patched["tracks"])
