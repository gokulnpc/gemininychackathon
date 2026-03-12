"""Unit tests for the _project_commands command projector and the 5 new _patch_project_json handlers.

Run: cd backend && python tests/unit/test_edit_command_projector.py
"""
from __future__ import annotations

import asyncio
import sys

# ── helpers ────────────────────────────────────────────────────────────────────

def _base_project() -> dict:
    return {
        "tracks": [
            {
                "id": "track-scene",
                "name": "Scene 1",
                "type": "element",
                "elements": [
                    {
                        "id": "img-1",
                        "trackId": "track-scene",
                        "type": "image",
                        "s": 0.0,
                        "e": 4.0,
                        "props": {"src": "https://example.com/scene1.png"},
                    }
                ],
            },
            {
                "id": "track-overlay",
                "name": "Overlays",
                "type": "element",
                "elements": [
                    {
                        "id": "text-1",
                        "trackId": "track-overlay",
                        "type": "text",
                        "s": 0.0,
                        "e": 3.0,
                        "t": "Original Text",
                        "props": {"text": "Original Text"},
                        "frame": {"size": [900, 180], "x": 0, "y": 200.0, "rotation": 0},
                    }
                ],
            },
            {
                "id": "track-caption",
                "name": "Captions",
                "type": "caption",
                "props": {"capStyle": "text_bg"},
                "elements": [],
            },
        ]
    }


_TESTS_PASSED: list[str] = []
_TESTS_FAILED: list[str] = []


def _run(name: str, fn):
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
        _TESTS_PASSED.append(name)
        print(f"✓ {name}")
    except Exception as exc:
        _TESTS_FAILED.append(name)
        print(f"✗ FAILED: {name} — {exc}")


# ── patch handler tests ────────────────────────────────────────────────────────

def test_patch_update_selected_text():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"update_selected_text": "New Text Here"},
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    el = patched["tracks"][1]["elements"][0]
    assert el["t"] == "New Text Here"
    assert el["props"]["text"] == "New Text Here"


def test_patch_add_text_overlay_bottom():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"add_text_overlay": {"text": "Lower Text", "duration_seconds": 2.5, "position_hint": "bottom"}},
        editor_context={"playhead_seconds": 1.0},
    )
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    new_els = [e for e in overlay["elements"] if e.get("t") == "Lower Text"]
    assert len(new_els) == 1
    el = new_els[0]
    assert el["frame"]["y"] == 500.0
    assert el["s"] == 1.0
    assert abs(el["e"] - 3.5) < 0.01


def test_patch_add_text_overlay_top():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"add_text_overlay": {"text": "Top Banner", "duration_seconds": 2.0, "position_hint": "top"}},
        editor_context={"playhead_seconds": 0.0},
    )
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    el = next(e for e in overlay["elements"] if e.get("t") == "Top Banner")
    assert el["frame"]["y"] == -720.0


def test_patch_add_text_overlay_middle():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"add_text_overlay": {"text": "Center", "position_hint": "middle"}},
        editor_context={"playhead_seconds": 0.5},
    )
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    el = next(e for e in overlay["elements"] if e.get("t") == "Center")
    assert el["frame"]["y"] == 0.0


def test_patch_trim_selected_element_duration():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"trim_selected_element": {"duration_seconds": 1.5}},
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    el = patched["tracks"][1]["elements"][0]
    assert abs(el["e"] - 1.5) < 0.01  # s=0 + duration=1.5


def test_patch_trim_selected_element_end_seconds():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"trim_selected_element": {"end_seconds": 2.2}},
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    el = patched["tracks"][1]["elements"][0]
    assert abs(el["e"] - 2.2) < 0.01


def test_patch_delete_selected_element():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"delete_selected_element": True},
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    assert all(e["id"] != "text-1" for e in overlay["elements"])


def test_patch_delete_no_selection_is_noop():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"delete_selected_element": True},
        editor_context={"selected_element_ids": []},
    )
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    assert len(overlay["elements"]) == 1  # unchanged


def test_patch_insert_media_asset():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    patched = _patch_project_json(
        pj,
        {"insert_media_asset": {"resolved_src": "https://example.com/broll.mp4", "media_kind": "video", "start_seconds": 1.5, "duration_seconds": 3.0}},
        editor_context={"playhead_seconds": 1.5},
    )
    media_track = next((t for t in patched["tracks"] if t["name"].startswith("Media Inserts")), None)
    assert media_track is not None
    el = media_track["elements"][0]
    assert el["type"] == "video"
    assert el["props"]["src"] == "https://example.com/broll.mp4"
    assert el["s"] == 1.5
    assert abs(el["e"] - 4.5) < 0.01


def test_patch_insert_media_asset_overlap():
    from services.gemini.edit_voice import _patch_project_json
    pj = _base_project()
    # First insert
    patched1 = _patch_project_json(
        pj,
        {"insert_media_asset": {"resolved_src": "https://example.com/1.mp4", "media_kind": "video", "start_seconds": 1.0, "duration_seconds": 3.0}},
        editor_context={"playhead_seconds": 1.0},
    )
    # Second insert overlapping
    patched2 = _patch_project_json(
        patched1,
        {"insert_media_asset": {"resolved_src": "https://example.com/2.mp4", "media_kind": "video", "start_seconds": 2.0, "duration_seconds": 3.0}},
        editor_context={"playhead_seconds": 2.0},
    )
    insert_tracks = [t for t in patched2["tracks"] if t["name"].startswith("Media Inserts")]
    assert len(insert_tracks) == 2
    assert insert_tracks[0]["name"] == "Media Inserts 1"
    assert insert_tracks[1]["name"] == "Media Inserts 2"
    assert insert_tracks[0]["elements"][0]["props"]["src"] == "https://example.com/1.mp4"
    assert insert_tracks[1]["elements"][0]["props"]["src"] == "https://example.com/2.mp4"


# ── _project_commands tests ────────────────────────────────────────────────────

async def test_project_commands_set_caption_style():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "set_caption_style", "args": {"style": "karaoke"}}],
        editor_context=None,
    )
    assert not errors
    caption_track = next(t for t in patched["tracks"] if t["type"] == "caption")
    assert caption_track["props"]["capStyle"] == "karaoke"
    assert "caption_style" in applied


async def test_project_commands_set_background_music():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "set_background_music", "args": {"preset": "quiet_before_storm", "volume": 0.3}}],
        editor_context=None,
    )
    assert not errors
    music_track = next((t for t in patched["tracks"] if t["name"] == "Background Music"), None)
    assert music_track is not None
    assert "background_music" in applied


async def test_project_commands_add_hook_title():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "add_hook_title", "args": {"text": "Watch This!", "duration_seconds": 2.0}}],
        editor_context={"playhead_seconds": 0.5},
    )
    assert not errors
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    new_hook = next((e for e in overlay["elements"] if e.get("t") == "Watch This!"), None)
    assert new_hook is not None
    assert "hook_title" in applied


async def test_project_commands_move_selected_element():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "move_selected_element", "args": {"dy": -50.0}}],
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    assert not errors
    el = patched["tracks"][1]["elements"][0]
    assert el["frame"]["y"] == 150.0  # 200.0 - 50.0


async def test_project_commands_move_selected_element_no_selection():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    _, _, errors = await _project_commands(
        pj,
        [{"kind": "move_selected_element", "args": {"dy": -50.0}}],
        editor_context={"selected_element_ids": []},
    )
    assert errors
    assert any("selected" in e.lower() for e in errors)


async def test_project_commands_update_selected_text():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "update_selected_text", "args": {"text": "Updated!"}}],
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    assert not errors
    el = patched["tracks"][1]["elements"][0]
    assert el["t"] == "Updated!"
    assert el["props"]["text"] == "Updated!"


async def test_project_commands_trim_selected_element():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "trim_selected_element", "args": {"duration_seconds": 1.0}}],
        editor_context={"selected_element_ids": ["text-1"], "selected_element_types": ["text"]},
    )
    assert not errors
    el = patched["tracks"][1]["elements"][0]
    assert abs(el["e"] - 1.0) < 0.01


async def test_project_commands_delete_selected_element():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [{"kind": "delete_selected_element", "args": {}}],
        editor_context={"selected_element_ids": ["text-1"]},
    )
    assert not errors
    overlay = next(t for t in patched["tracks"] if t["name"] == "Overlays")
    assert all(e["id"] != "text-1" for e in overlay["elements"])


async def test_project_commands_unknown_kind():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    _, _, errors = await _project_commands(
        pj,
        [{"kind": "fly_to_the_moon", "args": {}}],
        editor_context=None,
    )
    assert errors
    assert any("fly_to_the_moon" in e for e in errors)


async def test_project_commands_invalid_caption_style():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    _, _, errors = await _project_commands(
        pj,
        [{"kind": "set_caption_style", "args": {"style": "rainbow_explosion"}}],
        editor_context=None,
    )
    assert errors
    assert any("rainbow_explosion" in e for e in errors)


async def test_project_commands_multiple_in_order():
    from services.gemini.edit_voice import _project_commands
    pj = _base_project()
    patched, applied, errors = await _project_commands(
        pj,
        [
            {"kind": "set_caption_style", "args": {"style": "karaoke"}},
            {"kind": "set_background_music", "args": {"preset": "happy_rhythm", "volume": 0.2}},
        ],
        editor_context=None,
    )
    assert not errors
    caption_track = next(t for t in patched["tracks"] if t["type"] == "caption")
    assert caption_track["props"]["capStyle"] == "karaoke"
    music_track = next((t for t in patched["tracks"] if t["name"] == "Background Music"), None)
    assert music_track is not None


async def test_project_commands_does_not_mutate_other_tracks():
    from services.gemini.edit_voice import _project_commands
    import copy
    pj = _base_project()
    original = copy.deepcopy(pj)
    patched, _, _ = await _project_commands(
        pj,
        [{"kind": "set_caption_style", "args": {"style": "sleek"}}],
        editor_context=None,
    )
    # Scene track elements are unchanged
    orig_scene = original["tracks"][0]["elements"]
    new_scene = patched["tracks"][0]["elements"]
    assert orig_scene[0]["props"]["src"] == new_scene[0]["props"]["src"]


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

    # patch handler tests (sync)
    _run("patch_update_selected_text", test_patch_update_selected_text)
    _run("patch_add_text_overlay_bottom", test_patch_add_text_overlay_bottom)
    _run("patch_add_text_overlay_top", test_patch_add_text_overlay_top)
    _run("patch_add_text_overlay_middle", test_patch_add_text_overlay_middle)
    _run("patch_trim_selected_element_duration", test_patch_trim_selected_element_duration)
    _run("patch_trim_selected_element_end_seconds", test_patch_trim_selected_element_end_seconds)
    _run("patch_delete_selected_element", test_patch_delete_selected_element)
    _run("patch_delete_no_selection_is_noop", test_patch_delete_no_selection_is_noop)
    _run("patch_insert_media_asset", test_patch_insert_media_asset)
    _run("patch_insert_media_asset_overlap", test_patch_insert_media_asset_overlap)

    # _project_commands tests (async)
    _run("project_commands_set_caption_style", test_project_commands_set_caption_style)
    _run("project_commands_set_background_music", test_project_commands_set_background_music)
    _run("project_commands_add_hook_title", test_project_commands_add_hook_title)
    _run("project_commands_move_selected_element", test_project_commands_move_selected_element)
    _run("project_commands_move_selected_element_no_selection", test_project_commands_move_selected_element_no_selection)
    _run("project_commands_update_selected_text", test_project_commands_update_selected_text)
    _run("project_commands_trim_selected_element", test_project_commands_trim_selected_element)
    _run("project_commands_delete_selected_element", test_project_commands_delete_selected_element)
    _run("project_commands_unknown_kind", test_project_commands_unknown_kind)
    _run("project_commands_invalid_caption_style", test_project_commands_invalid_caption_style)
    _run("project_commands_multiple_in_order", test_project_commands_multiple_in_order)
    _run("project_commands_does_not_mutate_other_tracks", test_project_commands_does_not_mutate_other_tracks)

    print(f"\n{len(_TESTS_PASSED)} passed, {len(_TESTS_FAILED)} failed")
    if _TESTS_FAILED:
        sys.exit(1)
