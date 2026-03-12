"""Unit tests for the extended _queue_pending_edits function.

Run: cd backend && python -m pytest tests/unit/test_queue_pending_edits.py -v
"""
from __future__ import annotations

import pytest

from services.gemini.edit_voice import _queue_pending_edits


# ── add_text_overlay ──────────────────────────────────────────────────────────

def test_add_text_overlay_passes_through():
    pending: dict = {}
    overlay = {"text": "Subscribe!", "duration_seconds": 2.0, "position_hint": "bottom"}
    result = _queue_pending_edits(pending, {"add_text_overlay": overlay}, editor_context=None)
    assert "error" not in result
    assert pending["add_text_overlay"] == overlay


def test_add_text_overlay_without_position_hint_still_queues():
    pending: dict = {}
    result = _queue_pending_edits(pending, {"add_text_overlay": {"text": "Hi"}}, editor_context=None)
    assert "error" not in result
    assert "add_text_overlay" in pending


# ── update_selected_text ──────────────────────────────────────────────────────

def test_update_selected_text_passes_through_with_selection():
    pending: dict = {}
    ctx = {"selected_element_ids": ["el-1"], "selected_element_types": ["text"]}
    result = _queue_pending_edits(pending, {"update_selected_text": "New Caption"}, editor_context=ctx)
    assert "error" not in result
    assert pending["update_selected_text"] == "New Caption"


def test_update_selected_text_returns_error_without_selection():
    pending: dict = {}
    result = _queue_pending_edits(pending, {"update_selected_text": "Anything"}, editor_context=None)
    assert "error" in result
    assert "selected" in result["error"].lower()
    assert "update_selected_text" not in pending


def test_update_selected_text_returns_error_with_empty_selection():
    pending: dict = {}
    ctx = {"selected_element_ids": []}
    result = _queue_pending_edits(pending, {"update_selected_text": "Anything"}, editor_context=ctx)
    assert "error" in result
    assert "update_selected_text" not in pending


# ── trim_selected_element ─────────────────────────────────────────────────────

def test_trim_selected_element_passes_through_with_selection():
    pending: dict = {}
    ctx = {"selected_element_ids": ["el-1"]}
    trim_args = {"duration_seconds": 2.5}
    result = _queue_pending_edits(pending, {"trim_selected_element": trim_args}, editor_context=ctx)
    assert "error" not in result
    assert pending["trim_selected_element"] == trim_args


def test_trim_selected_element_returns_error_without_selection():
    pending: dict = {}
    result = _queue_pending_edits(pending, {"trim_selected_element": {"duration_seconds": 1.0}}, editor_context=None)
    assert "error" in result
    assert "trim_selected_element" not in pending


# ── delete_selected_element ───────────────────────────────────────────────────

def test_delete_selected_element_passes_through_with_selection():
    pending: dict = {}
    ctx = {"selected_element_ids": ["el-1"]}
    result = _queue_pending_edits(pending, {"delete_selected_element": True}, editor_context=ctx)
    assert "error" not in result
    assert pending["delete_selected_element"] is True


def test_delete_selected_element_returns_error_without_selection():
    pending: dict = {}
    result = _queue_pending_edits(pending, {"delete_selected_element": True}, editor_context=None)
    assert "error" in result
    assert "delete_selected_element" not in pending


# ── insert_media_asset ────────────────────────────────────────────────────────

def test_insert_media_asset_passes_through():
    pending: dict = {}
    ins = {"asset_id": "abc123", "media_kind": "image", "start_seconds": 1.5, "duration_seconds": 3.0}
    result = _queue_pending_edits(pending, {"insert_media_asset": ins}, editor_context=None)
    assert "error" not in result
    assert pending["insert_media_asset"] == ins


def test_insert_media_asset_with_resolved_src_passes_through():
    pending: dict = {}
    ins = {"resolved_src": "https://cdn.example.com/img.png", "media_kind": "image", "start_seconds": 0.0}
    result = _queue_pending_edits(pending, {"insert_media_asset": ins}, editor_context=None)
    assert "error" not in result
    assert "insert_media_asset" in pending


# ── multiple fields at once ───────────────────────────────────────────────────

def test_multiple_new_fields_queued_together():
    pending: dict = {}
    ctx = {"selected_element_ids": ["el-1"], "selected_element_types": ["text"]}
    result = _queue_pending_edits(
        pending,
        {
            "add_text_overlay": {"text": "End card", "position_hint": "bottom"},
            "update_selected_text": "Changed!",
        },
        editor_context=ctx,
    )
    assert "error" not in result
    assert "add_text_overlay" in pending
    assert pending["update_selected_text"] == "Changed!"


# ── interaction with legacy fields ────────────────────────────────────────────

def test_new_field_alongside_caption_style():
    pending: dict = {}
    ctx = {"selected_element_ids": ["el-1"]}
    result = _queue_pending_edits(
        pending,
        {"caption_style": "beast", "trim_selected_element": {"duration_seconds": 2.0}},
        editor_context=ctx,
    )
    assert "error" not in result
    assert pending["caption_style"] == "beast"
    assert pending["trim_selected_element"] == {"duration_seconds": 2.0}
