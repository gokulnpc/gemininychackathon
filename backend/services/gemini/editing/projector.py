"""Project Twick edit commands onto project_json and persist live edits."""

from __future__ import annotations

import copy
from uuid import uuid4

from .commands import _normalize_editor_media_url
from .constants import _VALID_CAPTION_STYLES, _VALID_MUSIC_PRESETS
from .context import _coerce_playhead_seconds, _find_selected_elements, _summarize_editor_context


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _ensure_overlay_track(project_json: dict) -> dict:
    for track in project_json.get("tracks", []):
        if track.get("type") == "element" and track.get("name") == "Overlays":
            track.setdefault("props", {})
            track.setdefault("elements", [])
            return track

    track = {
        "id": _make_id("track"),
        "name": "Overlays",
        "type": "element",
        "props": {},
        "elements": [],
    }
    project_json.setdefault("tracks", []).append(track)
    return track


def _ensure_effect_track(project_json: dict) -> dict:
    for track in project_json.get("tracks", []):
        if track.get("name") == "Effect Styles":
            return track
    new_track: dict = {
        "id": _make_id("track"),
        "name": "Effect Styles",
        "type": "element",
        "elements": [],
    }
    project_json.setdefault("tracks", []).append(new_track)
    return new_track


def _find_music_track(project_json: dict) -> tuple[dict, dict] | tuple[None, None]:
    for track in project_json.get("tracks", []):
        if track.get("name") != "Background Music":
            continue
        for element in track.get("elements", []):
            if element.get("type") == "audio":
                return track, element
    return None, None


def _ensure_music_track(project_json: dict, music_preset: str, music_volume: float) -> None:
    from services.content.timeline_builder import get_music_preview_src

    preview_src = get_music_preview_src(music_preset)
    track, element = _find_music_track(project_json)
    total_duration = max(
        (
            float(elem.get("e", 0.0))
            for track_item in project_json.get("tracks", [])
            for elem in track_item.get("elements", [])
        ),
        default=0.0,
    )

    if not preview_src:
        if track:
            project_json["tracks"] = [
                existing for existing in project_json.get("tracks", [])
                if existing.get("id") != track.get("id")
            ]
        return

    if not track or not element:
        track_id = _make_id("track")
        track = {
            "id": track_id,
            "name": "Background Music",
            "type": "element",
            "props": {},
            "elements": [],
        }
        element = {
            "id": _make_id("music"),
            "trackId": track_id,
            "type": "audio",
            "name": "Background Music",
            "s": 0.0,
            "e": total_duration,
            "props": {
                "src": preview_src,
                "time": 0,
                "playbackRate": 1,
                "volume": music_volume,
                "loop": True,
                "musicPreset": music_preset,
            },
            "mediaDuration": total_duration,
        }
        track["elements"].append(element)
        project_json.setdefault("tracks", []).append(track)
        return

    element.setdefault("props", {})
    element["props"]["src"] = preview_src
    element["props"]["volume"] = music_volume
    element["props"]["loop"] = True
    element["props"]["musicPreset"] = music_preset
    element["e"] = total_duration
    element["mediaDuration"] = total_duration


def _patch_project_json(project_json: dict, changes: dict, editor_context: dict | None = None) -> dict:
    """Patch caption style and music settings in a Twick project_json without re-rendering."""
    from services.content.timeline_builder import _CAP_STYLE_MAP

    patched = copy.deepcopy(project_json)
    next_music_preset = changes.get("background_music")
    next_music_volume = float(
        changes.get("music_volume")
        if "music_volume" in changes
        else next(
            (
                elem.get("props", {}).get("volume", 0.15)
                for track in patched.get("tracks", [])
                for elem in track.get("elements", [])
                if "musicPreset" in elem.get("props", {})
            ),
            0.15,
        )
    )

    for track in patched.get("tracks", []):
        if track.get("type") == "caption" and "caption_style" in changes:
            track.setdefault("props", {})["capStyle"] = _CAP_STYLE_MAP.get(
                changes["caption_style"], "text_bg",
            )
        for elem in track.get("elements", []):
            if "musicPreset" in elem.get("props", {}):
                if "background_music" in changes:
                    elem["props"]["musicPreset"] = changes["background_music"]
                if "music_volume" in changes:
                    elem["props"]["volume"] = changes["music_volume"]

    if next_music_preset is not None:
        _ensure_music_track(patched, next_music_preset, next_music_volume)
    elif "music_volume" in changes:
        _, element = _find_music_track(patched)
        if element:
            element.setdefault("props", {})["volume"] = changes["music_volume"]

    if "voiceover_volume" in changes:
        vo_volume = changes["voiceover_volume"]
        for track in patched.get("tracks", []):
            if track.get("name") == "Voiceover":
                for elem in track.get("elements", []):
                    elem.setdefault("props", {})["volume"] = vo_volume
                break

    if "move_selected_text_y_delta" in changes:
        delta = float(changes["move_selected_text_y_delta"])
        for _, elem in _find_selected_elements(patched, editor_context):
            frame = elem.get("frame")
            if isinstance(frame, dict):
                frame["y"] = float(frame.get("y", 0.0)) + delta
            else:
                props = elem.setdefault("props", {})
                props["y"] = float(props.get("y", 0.0)) + delta

    if "move_element_by_id" in changes:
        cmd = changes["move_element_by_id"]
        target_id = str(cmd.get("element_id", ""))
        dy = float(cmd.get("dy", 0.0))
        if not target_id:
            raise ValueError("move_element_by_id: element_id is required")
        found = False
        for track in patched.get("tracks", []):
            for elem in track.get("elements", []):
                if elem.get("id") == target_id:
                    found = True
                    frame = elem.get("frame")
                    if isinstance(frame, dict) and "y" in frame:
                        frame["y"] = float(frame.get("y", 0.0)) + dy
                    else:
                        props = elem.setdefault("props", {})
                        props["y"] = float(props.get("y", 0.0)) + dy
                    break
            if found:
                break
        if not found:
            raise ValueError(f"move_element_by_id: element {target_id!r} not found")

    if "delete_element_by_id" in changes:
        cmd = changes["delete_element_by_id"]
        target_id = str(cmd.get("element_id", ""))
        if not target_id:
            raise ValueError("delete_element_by_id: element_id is required")
        found = False
        for track in patched.get("tracks", []):
            before = len(track.get("elements", []))
            track["elements"] = [el for el in track.get("elements", []) if el.get("id") != target_id]
            if len(track.get("elements", [])) < before:
                found = True
        if not found:
            raise ValueError(f"delete_element_by_id: element {target_id!r} not found")

    if "apply_effect" in changes:
        cmd = changes["apply_effect"]
        effect_key = str(cmd.get("effect_key", ""))
        intensity = float(cmd.get("intensity", 1.0))
        if not effect_key:
            raise ValueError("apply_effect: effect_key is required")
        else:
            start_s = 0.0
            end_s = float(patched.get("duration", 30.0))
            selected = _find_selected_elements(patched, editor_context)
            if selected:
                _, sel_elem = selected[0]
                start_s = float(sel_elem.get("s", 0.0))
                end_s = float(sel_elem.get("e", end_s))
            effect_track = _ensure_effect_track(patched)
            updated = False
            for existing in effect_track.get("elements", []):
                if existing.get("type") == "effect" and abs(float(existing.get("s", -999)) - start_s) < 0.1:
                    existing["props"] = {"effectKey": effect_key, "intensity": intensity}
                    existing["name"] = effect_key.replace("_", " ").title()
                    updated = True
                    break
            if not updated:
                effect_track.setdefault("elements", []).append({
                    "id": _make_id("effect"),
                    "trackId": effect_track["id"],
                    "type": "effect",
                    "s": start_s,
                    "e": end_s,
                    "props": {"effectKey": effect_key, "intensity": intensity},
                    "name": effect_key.replace("_", " ").title(),
                })

    if "replace_selected_media_url" in changes:
        src = _normalize_editor_media_url(str(changes["replace_selected_media_url"])) or str(changes["replace_selected_media_url"])
        for _, elem in _find_selected_elements(patched, editor_context):
            if elem.get("type") not in {"image", "video"}:
                continue
            elem.setdefault("props", {})["src"] = src

    if "hook_title" in changes:
        start = _coerce_playhead_seconds(editor_context)
        duration = max(0.5, min(5.0, float(changes.get("hook_duration_seconds") or 2.0)))
        overlay_track = _ensure_overlay_track(patched)
        overlay_track["elements"].append(
            {
                "id": _make_id("text"),
                "trackId": overlay_track["id"],
                "type": "text",
                "name": "Hook Title",
                "s": start,
                "e": start + duration,
                "zIndex": 100,
                "t": changes["hook_title"],
                "props": {
                    "text": changes["hook_title"],
                    "fontSize": 82,
                    "fontFamily": "Inter",
                    "fontWeight": 800,
                    "color": "#FFFFFF",
                    "textAlign": "center",
                    "stroke": "#000000",
                    "strokeWidth": 4,
                    "shadowColor": "rgba(0,0,0,0.35)",
                },
                "frame": {
                    "size": [900, 220],
                    "x": 0,
                    "y": -540,
                    "rotation": 0,
                },
                "frameEffects": [],
            }
        )

    if "update_selected_text" in changes:
        new_text = str(changes["update_selected_text"])
        for _, elem in _find_selected_elements(patched, editor_context):
            if elem.get("type") != "text":
                continue
            elem["t"] = new_text
            elem.setdefault("props", {})["text"] = new_text

    if "add_text_overlay" in changes:
        position_y: dict[str, float] = {
            "top": -380.0, "middle": 0.0, "bottom": 380.0, "bottom_center": 380.0,
        }
        ov = changes["add_text_overlay"]
        pos_y = position_y.get(str(ov.get("position_hint", "bottom")), 500.0)
        start = float(ov.get("start_seconds", _coerce_playhead_seconds(editor_context)))
        dur = max(0.5, min(10.0, float(ov.get("duration_seconds", 3.0))))
        overlay_track = _ensure_overlay_track(patched)
        overlay_track["elements"].append({
            "id": _make_id("text"),
            "trackId": overlay_track["id"],
            "type": "text",
            "name": str(ov.get("variant", "text_overlay")).replace("_", " ").title(),
            "s": start,
            "e": start + dur,
            "zIndex": 90,
            "t": ov.get("text", ""),
            "props": {
                "text": ov.get("text", ""),
                "fontSize": 56,
                "fontFamily": "Inter",
                "fontWeight": 700,
                "color": "#FFFFFF",
                "textAlign": "center",
                "stroke": "#000000",
                "strokeWidth": 3,
            },
            "frame": {"size": [900, 180], "x": 0, "y": pos_y, "rotation": 0},
            "frameEffects": [],
        })

    if "trim_selected_element" in changes:
        trim = changes["trim_selected_element"]
        for _, elem in _find_selected_elements(patched, editor_context):
            if "start_seconds" in trim:
                elem["s"] = max(0.0, float(trim["start_seconds"]))
            if "end_seconds" in trim:
                elem["e"] = float(trim["end_seconds"])
            elif "duration_seconds" in trim:
                elem["e"] = float(elem.get("s", 0.0)) + max(0.1, float(trim["duration_seconds"]))

    if changes.get("delete_selected_element"):
        selected_ids = set((editor_context or {}).get("selected_element_ids") or [])
        if selected_ids:
            for track in patched.get("tracks", []):
                track["elements"] = [
                    element for element in track.get("elements", [])
                    if element.get("id") not in selected_ids
                ]

    if "insert_media_asset" in changes:
        ins = changes["insert_media_asset"]
        src = ins.get("resolved_src") or ins.get("src", "")
        if src:
            media_kind = ins.get("media_kind", "image")
            start = float(ins.get("start_seconds", _coerce_playhead_seconds(editor_context)))
            dur = max(0.1, float(ins.get("duration_seconds", 4.0)))
            new_end = start + dur
            explicit_track_name = ins.get("track_name")

            if explicit_track_name:
                # Use a named track explicitly (e.g. storyboard builder uses "Scene 1", "Scene 2", ...)
                media_track = next(
                    (t for t in patched.get("tracks", []) if t.get("name") == explicit_track_name),
                    None,
                )
                if not media_track:
                    media_track = {
                        "id": _make_id("track"),
                        "name": explicit_track_name,
                        "type": "element",
                        "props": {},
                        "elements": [],
                    }
                    patched.setdefault("tracks", []).append(media_track)
            else:
                def _track_overlaps(track: dict) -> bool:
                    for element in track.get("elements", []):
                        if float(element.get("s", 0)) < new_end and float(element.get("e", 0)) > start:
                            return True
                    return False

                all_insert_tracks = [
                    track for track in patched.get("tracks", [])
                    if track.get("name", "").startswith("Media Inserts")
                ]
                media_track = next((track for track in all_insert_tracks if not _track_overlaps(track)), None)

                if not media_track:
                    highest_n = 0
                    for track in all_insert_tracks:
                        name = track.get("name", "")
                        if name == "Media Inserts":
                            highest_n = max(highest_n, 1)
                        elif name.startswith("Media Inserts "):
                            part = name[len("Media Inserts "):]
                            if part.isdigit():
                                highest_n = max(highest_n, int(part))
                    n = highest_n + 1
                    media_track = {
                        "id": _make_id("track"),
                        "name": f"Media Inserts {n}",
                        "type": "element",
                        "props": {},
                        "elements": [],
                    }
                    patched.setdefault("tracks", []).append(media_track)

            _new_elem: dict = {
                "id": _make_id(media_kind[:3]),
                "trackId": media_track["id"],
                "type": media_kind,
                "name": ins.get("name", "Inserted Media"),
                "s": start,
                "e": new_end,
                "props": {"src": src},
            }
            if media_kind == "image":
                _new_elem["frame"] = {"size": [576, 1024], "x": 0.0, "y": 0.0}
                _new_elem["objectFit"] = "cover"
                _new_elem["props"]["objectFit"] = "cover"
                _new_elem["mediaDuration"] = dur
            media_track["elements"].append(_new_elem)

    if "add_color_slide" in changes:
        cs = changes["add_color_slide"]
        text = str(cs.get("text", "")).strip()
        custom_src = str(cs.get("src", "")).strip()
        duration = max(1.0, min(10.0, float(cs.get("duration_seconds", 3.0))))
        position = str(cs.get("position", "end"))

        total_dur = max(
            (float(el.get("e", 0.0))
             for track in patched.get("tracks", [])
             for el in track.get("elements", [])),
            default=0.0,
        )
        start_s = 0.0 if position == "start" else total_dur
        end_s = start_s + duration

        # 1×1 black PNG data URI — Twick objectFit:cover scales it to fill the canvas
        _BLACK_1PX = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        slide_track_name = "Intro Slide" if position == "start" else "Outro Slide"
        slide_track = next(
            (t for t in patched.get("tracks", []) if t.get("name") == slide_track_name),
            None,
        )
        if not slide_track:
            slide_track = {
                "id": _make_id("track"),
                "name": slide_track_name,
                "type": "element",
                "props": {},
                "elements": [],
            }
            patched.setdefault("tracks", []).append(slide_track)

        slide_track["elements"].append({
            "id": _make_id("img"),
            "trackId": slide_track["id"],
            "type": "image",
            "name": slide_track_name,
            "s": start_s,
            "e": end_s,
            "zIndex": 200,
            "props": {"src": custom_src or _BLACK_1PX, "objectFit": "cover"},
            "frame": {"size": [576, 1024], "x": 0.0, "y": 0.0},
            "objectFit": "cover",
            "mediaDuration": duration,
            "frameEffects": [],
        })

        if text:
            overlay_track = _ensure_overlay_track(patched)
            overlay_track["elements"].append({
                "id": _make_id("text"),
                "trackId": overlay_track["id"],
                "type": "text",
                "name": "Slide Title",
                "s": start_s,
                "e": end_s,
                "zIndex": 210,
                "t": text,
                "props": {
                    "text": text,
                    "fontSize": 72,
                    "fontFamily": "Inter",
                    "fontWeight": 800,
                    "color": "#FFFFFF",
                    "textAlign": "center",
                    "stroke": "#000000",
                    "strokeWidth": 3,
                    "shadowColor": "rgba(0,0,0,0.5)",
                },
                "frame": {"size": [860, 260], "x": 0, "y": 0, "rotation": 0},
                "frameEffects": [],
            })

    return patched


async def _project_commands(
    project_json: dict,
    commands: list[dict],
    editor_context: dict | None,
    uid: str = "",
) -> tuple[dict, dict, list[str]]:
    """Project normalized edit commands onto a Twick project_json."""
    kind_to_changes_key: dict[str, str | None] = {
        "set_caption_style": "caption_style",
        "set_background_music": None,
        "set_music_volume": None,
        "set_voiceover_volume": None,
        "add_text_overlay": "add_text_overlay",
        "update_selected_text": "update_selected_text",
        "move_selected_element": "move_selected_text_y_delta",
        "replace_selected_media": "replace_selected_media_url",
        "insert_media_asset": "insert_media_asset",
        "trim_selected_element": "trim_selected_element",
        "delete_selected_element": "delete_selected_element",
        "add_hook_title": None,
        "move_element_by_id": "move_element_by_id",
        "delete_element_by_id": "delete_element_by_id",
        "apply_effect": "apply_effect",
        "add_color_slide": "add_color_slide",
    }

    patched = copy.deepcopy(project_json)
    applied: dict = {}
    errors: list[str] = []

    for cmd in commands:
        kind = cmd.get("kind", "")
        args = cmd.get("args") or {}

        if kind not in kind_to_changes_key:
            errors.append(f"Unsupported command kind: '{kind}'")
            continue

        changes: dict = {}

        if kind == "set_caption_style":
            style = args.get("style") or args.get("caption_style", "")
            if style not in _VALID_CAPTION_STYLES:
                errors.append(f"Unknown caption style '{style}'. Valid: {', '.join(sorted(_VALID_CAPTION_STYLES))}")
                continue
            changes["caption_style"] = style

        elif kind == "set_background_music":
            preset = args.get("preset") or args.get("background_music")
            volume = args.get("volume") or args.get("music_volume")
            if preset is not None and preset not in _VALID_MUSIC_PRESETS:
                errors.append(f"Unknown music preset '{preset}'. Valid: {', '.join(sorted(_VALID_MUSIC_PRESETS))}")
                continue
            if preset is not None:
                changes["background_music"] = preset
            if volume is not None:
                changes["music_volume"] = max(0.0, min(1.0, float(volume)))

        elif kind == "set_music_volume":
            volume = args.get("volume")
            if volume is None:
                errors.append("set_music_volume: 'volume' (0.0–1.0) is required")
                continue
            changes["music_volume"] = max(0.0, min(1.0, float(volume)))

        elif kind == "set_voiceover_volume":
            volume = args.get("volume")
            if volume is None:
                errors.append("set_voiceover_volume: 'volume' (0.0–1.0) is required")
                continue
            changes["voiceover_volume"] = max(0.0, min(1.0, float(volume)))

        elif kind == "add_hook_title":
            text = args.get("text") or args.get("hook_title", "")
            if not text:
                errors.append("add_hook_title: 'text' is required")
                continue
            changes["hook_title"] = str(text).strip()[:120]
            if args.get("duration_seconds") is not None or args.get("hook_duration_seconds") is not None:
                dur = args.get("duration_seconds") or args.get("hook_duration_seconds")
                changes["hook_duration_seconds"] = max(0.5, min(5.0, float(dur)))
            if args.get("start_seconds") is not None:
                editor_context = {**(editor_context or {}), "playhead_seconds": float(args["start_seconds"])}

        elif kind == "move_selected_element":
            ctx = _summarize_editor_context(editor_context)
            if not ctx.get("selected_element_ids"):
                errors.append("move_selected_element: no element is currently selected")
                continue
            dy = args.get("dy") or args.get("move_selected_text_y_delta", 0.0)
            changes["move_selected_text_y_delta"] = float(dy)

        elif kind == "replace_selected_media":
            src = args.get("src") or args.get("replace_selected_media_url", "")
            if not src:
                asset_id = args.get("asset_id")
                if asset_id:
                    category = args.get("category") or (editor_context or {}).get("focused_asset_category", "images")
                    try:
                        from services.storage.assets import resolve_asset_url
                        src = await resolve_asset_url(uid, category, asset_id) or ""
                    except Exception as exc:
                        errors.append(f"replace_selected_media: could not resolve asset '{asset_id}': {exc}")
                        continue
                    if not src:
                        errors.append(f"replace_selected_media: asset '{asset_id}' not found")
                        continue
                else:
                    errors.append("replace_selected_media: 'src' or 'asset_id' is required")
                    continue
            normalized = _normalize_editor_media_url(src)
            if not normalized:
                errors.append(f"replace_selected_media: unsupported URL scheme for '{src}'")
                continue
            changes["replace_selected_media_url"] = normalized

        elif kind == "update_selected_text":
            changes["update_selected_text"] = args.get("text", "")

        elif kind == "add_text_overlay":
            changes["add_text_overlay"] = args

        elif kind == "trim_selected_element":
            changes["trim_selected_element"] = args

        elif kind == "delete_selected_element":
            changes["delete_selected_element"] = True

        elif kind == "move_element_by_id":
            changes["move_element_by_id"] = args

        elif kind == "delete_element_by_id":
            changes["delete_element_by_id"] = args

        elif kind == "apply_effect":
            changes["apply_effect"] = args

        elif kind == "add_color_slide":
            changes["add_color_slide"] = args

        elif kind == "insert_media_asset":
            ins_args = dict(args)
            if "asset_id" in ins_args and "resolved_src" not in ins_args and "src" not in ins_args:
                category = ins_args.get("category") or (editor_context or {}).get("focused_asset_category", "images")
                try:
                    from services.storage.assets import resolve_asset_url
                    resolved = await resolve_asset_url(uid, category, ins_args["asset_id"])
                except Exception as exc:
                    errors.append(f"insert_media_asset: could not resolve asset '{ins_args['asset_id']}': {exc}")
                    continue
                if not resolved:
                    errors.append(f"insert_media_asset: asset '{ins_args['asset_id']}' not found")
                    continue
                ins_args["resolved_src"] = resolved
            changes["insert_media_asset"] = ins_args

        try:
            patched = _patch_project_json(patched, changes, editor_context=editor_context)
            applied.update(changes)
        except Exception as exc:
            errors.append(f"Command '{kind}' failed during patch: {exc}")

    return patched, applied, errors


_CHANGE_LABELS: dict = {
    "replace_selected_media_url": "replaced media",
    "background_music": lambda v: f"music → {v}",
    "hook_title": lambda v: f"hook title updated",
    "text_overlay_added": "added text overlay",
    "element_deleted": "deleted element",
    "element_trimmed": "trimmed element",
    "element_moved": "moved element",
    "voiceover_volume": lambda v: f"voiceover volume → {v}",
    "music_volume_set": lambda v: f"music volume → {v}",
}
_SKIP_CHANGE_KEYS = {"music_volume", "project_json", "editor_context", "requires_export"}


def _friendly_change_summary(applied_changes: dict) -> str:
    parts = []
    for k, v in applied_changes.items():
        if k in _SKIP_CHANGE_KEYS:
            continue
        label = _CHANGE_LABELS.get(k)
        if label is None:
            parts.append(k.replace("_", " "))
        elif callable(label):
            parts.append(label(v))
        else:
            parts.append(label)
    return ", ".join(parts) if parts else "edits applied"


async def _apply_live_edits(
    project_id: str,
    project_data: dict,
    patched_project_json: dict | None,
    applied_changes: dict,
    editor_context: dict | None,
) -> dict:
    from services.storage import firestore_db as _fdb

    doc = await _fdb.get_project(project_id) or {}
    updates = {**doc}

    if "caption_style" in applied_changes:
        updates["caption_style"] = applied_changes["caption_style"]
        project_data["caption_style"] = applied_changes["caption_style"]
    if "background_music" in applied_changes:
        updates["background_music"] = applied_changes["background_music"]
        project_data["background_music"] = applied_changes["background_music"]
    if "music_volume" in applied_changes:
        updates["music_volume"] = applied_changes["music_volume"]
        project_data["music_volume"] = applied_changes["music_volume"]

    if patched_project_json:
        updates["project_json"] = patched_project_json
        project_data["project_json"] = patched_project_json

    await _fdb.save_project(project_id, updates)

    change_summary = _friendly_change_summary(applied_changes)
    return {
        "message": f"Done! Applied live edits: {change_summary}. Export when you're ready.",
        "changes": dict(applied_changes),
        "project_json": patched_project_json,
        "editor_context": _summarize_editor_context(editor_context),
        "requires_export": True,
    }

