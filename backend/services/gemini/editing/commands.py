"""Command normalization and proposal-building helpers for edit flows."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from .constants import _SUPPORTED_MEDIA_URL_SCHEMES, _VALID_CAPTION_STYLES, _VALID_MUSIC_PRESETS
from .context import _summarize_editor_context


def _resolve_gs_media_url(value: str) -> str | None:
    parsed = urlparse(value)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        return None
    return f"https://storage.googleapis.com/{bucket}/{key}"


def _normalize_editor_media_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return value
    if value.startswith("data:"):
        return value
    if parsed.scheme == "gs":
        return _resolve_gs_media_url(value)
    return None


def _looks_like_media_url(value: str) -> bool:
    return _normalize_editor_media_url(value) is not None


def _queue_pending_edits(
    pending_edits: dict,
    args: dict,
    editor_context: dict | None,
) -> dict:
    updates: dict = {}
    caption_style = args.get("caption_style")
    if caption_style and caption_style in _VALID_CAPTION_STYLES:
        updates["caption_style"] = caption_style
    elif caption_style:
        return {"error": f"Unknown caption style '{caption_style}'. Valid: {', '.join(sorted(_VALID_CAPTION_STYLES))}"}

    background_music = args.get("background_music")
    if background_music and background_music in _VALID_MUSIC_PRESETS:
        updates["background_music"] = background_music
    elif background_music:
        return {"error": f"Unknown music preset '{background_music}'. Valid: {', '.join(sorted(_VALID_MUSIC_PRESETS))}"}

    if "music_volume" in args and args.get("music_volume") is not None:
        updates["music_volume"] = max(0.0, min(1.0, float(args["music_volume"])))

    hook_title = args.get("hook_title")
    if hook_title:
        cleaned_title = str(hook_title).strip()
        if not cleaned_title:
            return {"error": "hook_title cannot be empty."}
        updates["hook_title"] = cleaned_title[:120]
        if args.get("hook_duration_seconds") is not None:
            updates["hook_duration_seconds"] = max(0.5, min(5.0, float(args["hook_duration_seconds"])))

    if args.get("move_selected_text_y_delta") is not None:
        context = _summarize_editor_context(editor_context)
        selected_types = set(context.get("selected_element_types") or [])
        if "text" not in selected_types:
            return {"error": "move_selected_text_y_delta requires a selected text element."}
        updates["move_selected_text_y_delta"] = float(args["move_selected_text_y_delta"])

    if args.get("replace_selected_media_url") is not None:
        media_url = str(args["replace_selected_media_url"]).strip()
        normalized_media_url = _normalize_editor_media_url(media_url)
        if not normalized_media_url:
            schemes = ", ".join(sorted(_SUPPORTED_MEDIA_URL_SCHEMES))
            return {"error": f"replace_selected_media_url must be a direct media URL using one of: {schemes}."}
        context = _summarize_editor_context(editor_context)
        selected_types = set(context.get("selected_element_types") or [])
        if not (selected_types & {"image", "video"}):
            return {"error": "replace_selected_media_url requires a selected image or video element."}
        updates["replace_selected_media_url"] = normalized_media_url

    if args.get("add_text_overlay") is not None:
        updates["add_text_overlay"] = args["add_text_overlay"]

    if args.get("update_selected_text") is not None:
        ctx = _summarize_editor_context(editor_context)
        if not ctx.get("selected_element_ids"):
            return {"error": "update_selected_text: no element is currently selected"}
        updates["update_selected_text"] = str(args["update_selected_text"])

    if args.get("trim_selected_element") is not None:
        ctx = _summarize_editor_context(editor_context)
        if not ctx.get("selected_element_ids"):
            return {"error": "trim_selected_element: no element is currently selected"}
        updates["trim_selected_element"] = args["trim_selected_element"]

    if args.get("delete_selected_element"):
        ctx = _summarize_editor_context(editor_context)
        if not ctx.get("selected_element_ids"):
            return {"error": "delete_selected_element: no element is currently selected"}
        updates["delete_selected_element"] = True

    if args.get("insert_media_asset") is not None:
        updates["insert_media_asset"] = args["insert_media_asset"]

    pending_edits.update(updates)
    return {"queued": updates}


def _build_proposal_from_pending_edits(
    pending_edits: dict,
    editor_context: dict | None = None,
) -> dict:
    """Convert old-style pending_edits dict into an EditProposal-shaped dict."""
    edit_key_to_kind: dict[str, str] = {
        "caption_style": "set_caption_style",
        "background_music": "set_background_music",
        "music_volume": "set_background_music",
        "hook_title": "add_hook_title",
        "hook_duration_seconds": "add_hook_title",
        "move_selected_text_y_delta": "move_selected_element",
        "replace_selected_media_url": "replace_selected_media",
        "add_text_overlay": "add_text_overlay",
        "update_selected_text": "update_selected_text",
        "trim_selected_element": "trim_selected_element",
        "delete_selected_element": "delete_selected_element",
        "insert_media_asset": "insert_media_asset",
    }

    commands: list[dict] = []
    seen_kinds: set[str] = set()
    for key, value in pending_edits.items():
        kind = edit_key_to_kind.get(key)
        if not kind or kind in seen_kinds:
            continue
        if kind == "set_background_music":
            commands.append({
                "kind": kind,
                "args": {
                    "preset": pending_edits.get("background_music"),
                    "volume": pending_edits.get("music_volume"),
                },
            })
        elif kind == "add_hook_title":
            commands.append({
                "kind": kind,
                "args": {
                    "text": pending_edits.get("hook_title"),
                    "duration_seconds": pending_edits.get("hook_duration_seconds"),
                },
            })
        elif kind == "move_selected_element":
            ctx = _summarize_editor_context(editor_context)
            commands.append({
                "kind": kind,
                "args": {"dy": value},
                "element_id": (ctx.get("selected_element_ids") or [None])[0],
            })
        elif kind == "replace_selected_media":
            ctx = _summarize_editor_context(editor_context)
            commands.append({
                "kind": kind,
                "args": {"src": value},
                "element_id": (ctx.get("selected_element_ids") or [None])[0],
            })
        elif kind == "add_text_overlay":
            commands.append({"kind": kind, "args": value if isinstance(value, dict) else {"text": str(value)}})
        elif kind == "update_selected_text":
            ctx = _summarize_editor_context(editor_context)
            commands.append({
                "kind": kind,
                "args": {"text": str(value)},
                "element_id": (ctx.get("selected_element_ids") or [None])[0],
            })
        elif kind == "trim_selected_element":
            ctx = _summarize_editor_context(editor_context)
            commands.append({
                "kind": kind,
                "args": value if isinstance(value, dict) else {},
                "element_id": (ctx.get("selected_element_ids") or [None])[0],
            })
        elif kind == "delete_selected_element":
            ctx = _summarize_editor_context(editor_context)
            commands.append({
                "kind": kind,
                "args": {},
                "element_id": (ctx.get("selected_element_ids") or [None])[0],
            })
        elif kind == "insert_media_asset":
            commands.append({"kind": kind, "args": value if isinstance(value, dict) else {}})
        else:
            commands.append({"kind": kind, "args": {key: value}})
        seen_kinds.add(kind)

    summaries: list[str] = []
    for cmd in commands:
        kind = cmd["kind"]
        args = cmd.get("args", {})
        if kind == "set_caption_style":
            summaries.append(f"Caption style → {args.get('caption_style') or args.get('style', '?')}")
        elif kind == "set_background_music":
            summaries.append(f"Music → {args.get('preset', '?')}")
        elif kind == "add_hook_title":
            summaries.append(f"Hook title: \"{args.get('text', '')}\"")
        elif kind == "move_selected_element":
            summaries.append("Move selected element")
        elif kind == "replace_selected_media":
            summaries.append("Replace selected media")
        else:
            summaries.append(kind.replace("_", " ").title())

    return {
        "proposal_id": uuid4().hex[:16],
        "summary": "; ".join(summaries) or "Apply suggested edits",
        "commands": commands,
        "confirmation_required": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_proposal_from_commands(draft_commands: list[dict]) -> dict:
    summaries: list[str] = []
    for cmd in draft_commands:
        kind = cmd.get("kind", "")
        args = cmd.get("args", {})
        if kind == "set_caption_style":
            summaries.append(f"Caption style → {args.get('caption_style') or args.get('style', '?')}")
        elif kind == "set_background_music":
            summaries.append(f"Music → {args.get('preset', '?')}")
        elif kind == "add_hook_title":
            summaries.append(f"Hook title: \"{args.get('text', '')}\"")
        elif kind == "move_selected_element":
            summaries.append("Move selected element")
        elif kind == "replace_selected_media":
            summaries.append("Replace selected media")
        else:
            summaries.append(kind.replace("_", " ").title())

    return {
        "proposal_id": uuid4().hex[:16],
        "summary": "; ".join(summaries) or "Apply suggested edits",
        "commands": list(draft_commands),
        "confirmation_required": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

