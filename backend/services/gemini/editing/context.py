"""Shared editor-context helpers for edit runtimes and project patching."""

from __future__ import annotations


def _coerce_playhead_seconds(editor_context: dict | None) -> float:
    if not editor_context:
        return 0.0
    try:
        return max(0.0, float(editor_context.get("playhead_seconds") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _find_selected_elements(project_json: dict, editor_context: dict | None) -> list[tuple[dict, dict]]:
    if not editor_context:
        return []

    selected_ids = set(editor_context.get("selected_element_ids") or [])
    if not selected_ids:
        return []

    matches: list[tuple[dict, dict]] = []
    for track in project_json.get("tracks", []):
        for element in track.get("elements", []):
            if element.get("id") in selected_ids:
                matches.append((track, element))
    return matches


def _summarize_editor_context(editor_context: dict | None) -> dict:
    """Return a compact, model-safe summary of the current editor state."""
    if not editor_context:
        return {
            "mode": None,
            "active_panel": None,
            "playhead_seconds": None,
            "viewport_scale": None,
            "selected_element_ids": [],
            "selected_track_ids": [],
            "selected_element_types": [],
            "has_screenshot": False,
            "screenshot_dimensions": None,
        }

    screenshot = editor_context.get("screenshot") or {}
    width = screenshot.get("width")
    height = screenshot.get("height")

    return {
        "mode": editor_context.get("mode"),
        "active_panel": editor_context.get("active_panel"),
        "playhead_seconds": editor_context.get("playhead_seconds"),
        "viewport_scale": editor_context.get("viewport_scale"),
        "selected_element_ids": editor_context.get("selected_element_ids", []),
        "selected_track_ids": editor_context.get("selected_track_ids", []),
        "selected_element_types": editor_context.get("selected_element_types", []),
        "has_screenshot": bool(screenshot),
        "screenshot_dimensions": (
            {"width": width, "height": height}
            if width is not None or height is not None
            else None
        ),
    }

