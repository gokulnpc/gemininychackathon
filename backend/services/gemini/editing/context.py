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


def _summarize_editor_context(
    editor_context: dict | None,
    project_json: dict | None = None,
) -> dict:
    """Return a compact, model-safe summary of the current editor state.

    When project_json is provided, includes a timeline_elements catalog (up to 10
    elements sorted by proximity to the playhead) so the model can identify candidate
    elements even when nothing is explicitly selected.
    """
    if not editor_context:
        result: dict = {
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
    else:
        screenshot = editor_context.get("screenshot") or {}
        width = screenshot.get("width")
        height = screenshot.get("height")
        result = {
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

    if project_json:
        playhead = float(result.get("playhead_seconds") or 0.0)
        elements: list[dict] = []
        for track in project_json.get("tracks", []):
            track_name = track.get("name", "")
            track_id = track.get("id", "")
            for el in track.get("elements", []):
                el_id = el.get("id", "")
                if not el_id:
                    continue
                start = float(el.get("s", 0))
                end = float(el.get("e", 0))
                kind = el.get("type") or el.get("kind") or "unknown"
                elements.append({
                    "element_id": el_id,
                    "track_id": track_id,
                    "track_name": track_name,
                    "kind": kind,
                    "start_seconds": round(start, 2),
                    "end_seconds": round(end, 2),
                    "distance_from_playhead": round(abs(start - playhead), 2),
                })
        elements.sort(key=lambda e: e["distance_from_playhead"])
        result["timeline_elements"] = elements[:10]

    return result

