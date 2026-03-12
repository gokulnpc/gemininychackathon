"""Unit tests for _build_proposal_from_pending_edits.

Run: cd backend && python tests/unit/test_build_proposal.py
"""
from __future__ import annotations

import sys

_TESTS_PASSED: list[str] = []
_TESTS_FAILED: list[str] = []


def _run(name: str, fn):
    try:
        fn()
        _TESTS_PASSED.append(name)
        print(f"✓ {name}")
    except Exception as exc:
        _TESTS_FAILED.append(name)
        print(f"✗ FAILED: {name} — {exc}")


def test_single_caption_style():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"caption_style": "sleek"})
    assert len(proposal["commands"]) == 1
    cmd = proposal["commands"][0]
    assert cmd["kind"] == "set_caption_style"
    assert cmd["args"].get("caption_style") == "sleek"


def test_music_and_volume_merged_into_one_command():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits(
        {"background_music": "breathing_shadows", "music_volume": 0.25}
    )
    music_cmds = [c for c in proposal["commands"] if c["kind"] == "set_background_music"]
    assert len(music_cmds) == 1
    assert music_cmds[0]["args"]["preset"] == "breathing_shadows"
    assert music_cmds[0]["args"]["volume"] == 0.25


def test_hook_title_and_duration_merged():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits(
        {"hook_title": "WATCH THIS", "hook_duration_seconds": 2.5}
    )
    hook_cmds = [c for c in proposal["commands"] if c["kind"] == "add_hook_title"]
    assert len(hook_cmds) == 1
    assert hook_cmds[0]["args"]["text"] == "WATCH THIS"
    assert hook_cmds[0]["args"]["duration_seconds"] == 2.5


def test_empty_pending_edits_produces_no_commands():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({})
    assert proposal["commands"] == []


def test_proposal_has_non_empty_id():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"caption_style": "beast"})
    assert proposal["proposal_id"]
    assert len(proposal["proposal_id"]) > 0


def test_summary_is_non_empty_string():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"caption_style": "elegant"})
    assert isinstance(proposal["summary"], str)
    assert len(proposal["summary"]) > 0


def test_summary_contains_readable_change_name():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"background_music": "happy_rhythm"})
    assert "Music" in proposal["summary"] or "music" in proposal["summary"] or "happy_rhythm" in proposal["summary"]


def test_confirmation_required_is_true():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"caption_style": "beast"})
    assert proposal["confirmation_required"] is True


def test_created_at_is_set():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits({"caption_style": "beast"})
    assert proposal["created_at"] is not None
    assert "T" in proposal["created_at"]


def test_move_selected_text_includes_element_id():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits(
        {"move_selected_text_y_delta": -80.0},
        editor_context={
            "selected_element_ids": ["el-42"],
            "selected_element_types": ["text"],
        },
    )
    move_cmds = [c for c in proposal["commands"] if c["kind"] == "move_selected_element"]
    assert len(move_cmds) == 1
    assert move_cmds[0].get("element_id") == "el-42"


def test_replace_selected_media_includes_src():
    from services.gemini.edit_voice import _build_proposal_from_pending_edits
    proposal = _build_proposal_from_pending_edits(
        {"replace_selected_media_url": "https://cdn.example.com/new.jpg"},
        editor_context={
            "selected_element_ids": ["img-7"],
            "selected_element_types": ["image"],
        },
    )
    replace_cmds = [c for c in proposal["commands"] if c["kind"] == "replace_selected_media"]
    assert len(replace_cmds) == 1
    assert replace_cmds[0]["args"]["src"] == "https://cdn.example.com/new.jpg"


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

    _run("single_caption_style", test_single_caption_style)
    _run("music_and_volume_merged_into_one_command", test_music_and_volume_merged_into_one_command)
    _run("hook_title_and_duration_merged", test_hook_title_and_duration_merged)
    _run("empty_pending_edits_produces_no_commands", test_empty_pending_edits_produces_no_commands)
    _run("proposal_has_non_empty_id", test_proposal_has_non_empty_id)
    _run("summary_is_non_empty_string", test_summary_is_non_empty_string)
    _run("summary_contains_readable_change_name", test_summary_contains_readable_change_name)
    _run("confirmation_required_is_true", test_confirmation_required_is_true)
    _run("created_at_is_set", test_created_at_is_set)
    _run("move_selected_text_includes_element_id", test_move_selected_text_includes_element_id)
    _run("replace_selected_media_includes_src", test_replace_selected_media_includes_src)

    print(f"\n{len(_TESTS_PASSED)} passed, {len(_TESTS_FAILED)} failed")
    if _TESTS_FAILED:
        sys.exit(1)
