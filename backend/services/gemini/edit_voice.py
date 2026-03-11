"""Scout Edit Voice Agent — voice-driven video editor for completed projects.

WebSocket: /api/v1/projects/{project_id}/edit-voice
SSE:       POST /api/v1/projects/{project_id}/edit-agent

Two modes for the same editing intent:

  Voice mode — Scout speaks with the user over Gemini Live API, can call Maya to
               show a fast single-image style preview, then applies the recompose
               pipeline on confirmation.

  Text mode  — ADK agent interprets a natural-language instruction, streams tool-call
               progress as SSE events, applies the recompose pipeline, returns new
               video URL.

Speed-first: style previews generate 1 image (not 4–6). Recompose targets a single
platform only (saves ~50% time). Text agent uses gemini-2.5-flash.

All existing endpoints (generate-script, generate-video, voice-agent, recompose)
are UNCHANGED — this is fully additive.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
from collections.abc import AsyncIterator, Callable, Coroutine
from uuid import UUID, uuid4
from urllib.parse import urlparse

try:
    from google.adk.tools import ToolContext  # needed at module level for nested tool function type annotations
except ImportError:
    ToolContext = object  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

from services.gemini.models import MODELS

_LIVE_MODEL = MODELS.live_audio
_TEXT_MODEL = MODELS.fast_text  # faster than the reasoning model for simple edit reasoning

# ── Scout edit system prompt ────────────────────────────────────────────────────

_EDIT_SYSTEM = """You are Scout, Content Factory's AI video editor.
You are editing an EXISTING completed video. The project info is already loaded — use get_project_info to see the current settings.

Your job:
1. Greet the user warmly, mention the current video's hook in 1 sentence.
2. Ask what they want to change — ONE question only.
3. If they want to SEE visual options (style, mood, look) → call generate_style_preview first.
4. Once you know what to change → call queue_edit with the supported edit fields.
5. Confirm the changes in 1 sentence, then call apply_live_edits.
6. Tell the user the timeline is updated live and they can export when ready.

Rules:
- Keep every response under 2 sentences.
- Never ask more than one question per turn.
- generate_style_preview is for SHOWING options only — never for applying changes.
- Only call apply_live_edits ONCE per turn, after ALL edits are queued.
- Valid caption styles: bold_stroke, red_highlight, sleek, karaoke, majestic, beast, elegant, clarity
- Valid music presets: happy_rhythm, quiet_before_storm, peaceful_vibes, brilliant_symphony, breathing_shadows, lyria, none
- Supported timeline edits in queue_edit:
  - hook_title: add a short text hook near the current playhead or at the start
  - move_selected_text_y_delta: move the selected text element up or down in pixels
  - replace_selected_media_url: replace the selected image/video src when the user gives a direct URL
- For selection-sensitive requests, call get_editor_context first.
- Do not invent asset URLs. Only replace media when the user provides a usable URL."""

# ── Fast single-image style preview ────────────────────────────────────────────

def _quick_preview_prompt(brief: str, art_style: str | None) -> str:
    style_clause = f"Art style: {art_style}. " if art_style else ""
    return (
        f"{style_clause}Generate ONE striking vertical image (9:16 portrait) "
        f"that visually represents this concept: {brief}. "
        "Output ONLY the image — no text."
    )


def _invoke_quick_preview(prompt: str) -> list[dict]:
    """Synchronous single-image Gemini call — run via asyncio.to_thread."""
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    response = client.models.generate_content(
        model=MODELS.image_generation,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    blocks: list[dict] = []
    for part in response.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob is not None:
            raw = getattr(blob, "data", None)
            mime = getattr(blob, "mime_type", "image/png")
            if raw:
                if isinstance(raw, bytes):
                    raw = base64.b64encode(raw).decode()
                blocks.append({"type": "image", "content": raw, "mime_type": mime})
    return blocks


async def _generate_quick_preview(
    brief: str,
    art_style: str | None = None,
    on_event: Callable | None = None,
) -> dict:
    """Generate ONE preview image and stream it to the browser via on_event."""
    try:
        prompt = _quick_preview_prompt(brief, art_style)
        logger.info("Quick style preview: art_style=%s", art_style)
        blocks = await asyncio.to_thread(_invoke_quick_preview, prompt)

        if on_event and blocks:
            try:
                await on_event({
                    "type": "creative_block",
                    "block": blocks[0],
                    "block_index": 0,
                    "total_blocks": 1,
                })
            except Exception:
                pass

        logger.info("Quick style preview done — %d image(s)", len(blocks))
        return {"status": "completed", "total_images": len(blocks)}

    except Exception as exc:
        logger.warning("generate_style_preview failed: %s", exc)
        return {"error": str(exc)}


# ── Shared edit tool logic (used by both voice + text agent) ───────────────────

_VALID_CAPTION_STYLES = {
    "bold_stroke", "red_highlight", "sleek", "karaoke",
    "majestic", "beast", "elegant", "clarity",
}
_VALID_MUSIC_PRESETS = {
    "happy_rhythm", "quiet_before_storm", "peaceful_vibes",
    "brilliant_symphony", "breathing_shadows", "lyria", "none",
}

_SUPPORTED_MEDIA_URL_SCHEMES = {"http", "https", "gs", "data"}


async def _apply_recompose(
    project_id: str,
    project_data: dict,
    pending_edits: dict,
) -> dict:
    """Run the recompose pipeline with queued edits. Single-platform for speed."""
    from models.schemas import CaptionStyleEnum, MusicPreset, Platform
    from services.infra.recompose import recompose_video

    caption_style = pending_edits.get("caption_style") or project_data.get("caption_style", "beast")
    background_music = pending_edits.get("background_music") or project_data.get("background_music", "none")
    music_volume = float(pending_edits.get("music_volume") or project_data.get("music_volume", 0.15))

    # Single platform only (speed optimisation)
    platforms_raw = project_data.get("platforms") or ["instagram_reels"]
    target_platform = Platform(platforms_raw[0])

    voiceover_script = project_data.get("voiceover_full_script", "")
    video_duration = int(project_data.get("video_duration", 30))

    _, video_urls = await recompose_video(
        project_id=UUID(project_id),
        voiceover_full_script=voiceover_script,
        video_duration=video_duration,
        caption_style=caption_style,
        background_music=background_music,
        target_platforms=[target_platform],
        music_volume=music_volume,
    )

    video_url = next(iter(video_urls.values()), "")
    changes: dict = {}
    if "caption_style" in pending_edits:
        changes["caption_style"] = pending_edits["caption_style"]
    if "background_music" in pending_edits:
        changes["background_music"] = pending_edits["background_music"]

    return {
        "status": "applied",
        "video_url": video_url,
        "video_urls": video_urls,
        "changes": changes,
    }


# ── Voice mode ──────────────────────────────────────────────────────────────────

def _build_voice_config(project_data: dict):
    """Build LiveConnectConfig with Scout's edit tools and AUDIO output."""
    from google.genai import types

    hook = project_data.get("hook", "your video")
    caption_style = project_data.get("caption_style", "beast")
    background_music = project_data.get("background_music", "none")

    system = (
        f"{_EDIT_SYSTEM}\n\n"
        f"Current project state:\n"
        f"  Hook: \"{hook}\"\n"
        f"  Caption style: {caption_style}\n"
        f"  Background music: {background_music}"
    )

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription={},
        output_audio_transcription={},
        system_instruction=system,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="get_project_info",
                description="Get the current video's settings — hook, caption style, music.",
                parameters=types.Schema(type="object", properties={}),
            ),
            types.FunctionDeclaration(
                name="get_editor_context",
                description="Get the current editor selection and playhead context for live timeline edits.",
                parameters=types.Schema(type="object", properties={}),
            ),
            types.FunctionDeclaration(
                name="generate_style_preview",
                description=(
                    "Generate ONE fast preview image showing what a style or concept looks like. "
                    "Use this when the user wants to SEE options before deciding."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "brief": types.Schema(type="string", description="Visual concept to preview."),
                        "art_style": types.Schema(type="string", description="Art style: realism | ghibli | comic | polaroid | disney | painting | creepy_comic"),
                    },
                    required=["brief"],
                ),
            ),
            types.FunctionDeclaration(
                name="queue_edit",
                description="Queue metadata or timeline edits. Does NOT apply yet.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "caption_style": types.Schema(type="string", description="bold_stroke | red_highlight | sleek | karaoke | majestic | beast | elegant | clarity"),
                        "background_music": types.Schema(type="string", description="happy_rhythm | quiet_before_storm | peaceful_vibes | brilliant_symphony | breathing_shadows | lyria | none"),
                        "music_volume": types.Schema(type="number", description="0.0–1.0, default 0.15"),
                        "hook_title": types.Schema(type="string", description="Short text hook to add to the timeline."),
                        "hook_duration_seconds": types.Schema(type="number", description="Hook title duration in seconds."),
                        "move_selected_text_y_delta": types.Schema(type="number", description="Negative moves selected text up; positive moves it down."),
                        "replace_selected_media_url": types.Schema(type="string", description="Direct URL for the selected image/video."),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="apply_live_edits",
                description="Apply all queued edits to the live timeline and save them. Call ONCE after confirming with the user.",
                parameters=types.Schema(type="object", properties={}),
            ),
        ])],
    )


async def _dispatch_voice_tool(
    name: str,
    args: dict,
    project_id: str,
    project_data: dict,
    pending_edits: dict,
    current_project_json: dict | None,
    editor_context: dict | None,
    on_event: Callable,
) -> dict:
    """Route a Live API function_call to the correct edit tool."""
    if name == "get_project_info":
        return {
            "hook":             project_data.get("hook", ""),
            "caption_style":    project_data.get("caption_style", "beast"),
            "background_music": project_data.get("background_music", "none"),
            "music_volume":     project_data.get("music_volume", 0.15),
            "platforms":        project_data.get("platforms", ["instagram_reels"]),
        }

    if name == "get_editor_context":
        return _summarize_editor_context(editor_context)

    if name == "generate_style_preview":
        return await _generate_quick_preview(
            brief=args.get("brief", "video concept"),
            art_style=args.get("art_style"),
            on_event=on_event,
        )

    if name == "queue_edit":
        result = _queue_pending_edits(
            pending_edits=pending_edits,
            args=args,
            editor_context=editor_context,
        )
        if "error" in result:
            return result
        return {"queued": dict(pending_edits)}

    if name == "apply_live_edits":
        if not pending_edits:
            return {"error": "No edits queued. Call queue_edit first."}
        result = await _apply_live_edits(
            project_id=project_id,
            project_data=project_data,
            current_project_json=current_project_json,
            pending_edits=pending_edits,
            editor_context=editor_context,
        )
        pending_edits.clear()
        try:
            await on_event({"type": "complete", **result})
        except Exception:
            pass
        return result

    return {"error": f"Unknown tool: {name}"}


async def run_edit_voice_agent(
    project_id: str,
    project_data: dict,
    audio_chunks: AsyncIterator[bytes],
    get_live_state: Callable[[], dict] | None,
    on_event: Callable[[dict], Coroutine],
):
    """Async generator — yields PCM16 audio (Scout's voice) for the edit session.

    Accepts audio from the browser, streams Scout's voice back, sends JSON events
    for transcripts, tool calls, creative blocks, and edit_complete notifications.
    """
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    live_config = _build_voice_config(project_data)

    # Mutable state shared across tool calls within this session
    pending_edits: dict = {}

    logger.info("Scout edit voice session starting: project=%s", project_id)

    async with client.aio.live.connect(model=_LIVE_MODEL, config=live_config) as session:
        send_task: asyncio.Task | None = None

        async def _send_audio() -> None:
            async for chunk in audio_chunks:
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

        send_task = asyncio.create_task(_send_audio())

        try:
            async for response in session.receive():
                # ── Scout's voice → forward to browser ───────────────────────
                if response.data:
                    yield response.data

                server_content = getattr(response, "server_content", None)
                output_transcription = getattr(server_content, "output_transcription", None) if server_content else None
                if output_transcription and getattr(output_transcription, "text", None):
                    try:
                        await on_event({"type": "agent_transcript", "text": output_transcription.text.strip()})
                    except Exception:
                        pass
                else:
                    text = getattr(response, "text", None)
                    if text and text.strip():
                        try:
                            await on_event({"type": "agent_transcript", "text": text.strip()})
                        except Exception:
                            pass

                input_transcription = getattr(server_content, "input_transcription", None) if server_content else None
                if input_transcription and getattr(input_transcription, "text", None):
                    try:
                        await on_event({"type": "user_transcript", "text": input_transcription.text.strip()})
                    except Exception:
                        pass

                if server_content and getattr(server_content, "interrupted", False):
                    try:
                        await on_event({"type": "interrupted"})
                    except Exception:
                        pass

                # ── Tool calls ────────────────────────────────────────────────
                tool_call = getattr(response, "tool_call", None)
                if tool_call:
                    for fc in tool_call.function_calls:
                        args = dict(fc.args) if fc.args else {}
                        logger.info("Scout edit tool call: %s(%s)", fc.name, list(args.keys()))
                        live_state = get_live_state() if get_live_state else {}

                        result = await _dispatch_voice_tool(
                            fc.name,
                            args,
                            project_id,
                            project_data,
                            pending_edits,
                            live_state.get("project_json"),
                            live_state.get("editor_context"),
                            on_event,
                        )

                        try:
                            await on_event({"type": "tool_event", "name": fc.name, **result})
                        except Exception:
                            pass

                        await session.send_tool_response(
                            function_responses=[types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response={"result": result},
                            )]
                        )

                # ── End of session ────────────────────────────────────────────
                turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
                if send_task.done() and turn_complete:
                    break
        except Exception as exc:
            message = str(exc)
            if "Operation is not implemented, or supported, or enabled" in message:
                raise RuntimeError(
                    "Gemini Live rejected the current voice session configuration. "
                    "Retry once; if it persists, use the text agent while we keep the live session on the minimal supported config."
                ) from exc
            raise
        finally:
            if send_task is not None:
                if not send_task.done():
                    send_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await send_task

    logger.info("Scout edit voice session ended: project=%s", project_id)


# ── Timeline JSON patcher ────────────────────────────────────────────────────────

def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


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


def _looks_like_media_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https", "gs"}:
        return True
    return value.startswith("data:")


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
        if not _looks_like_media_url(media_url):
            schemes = ", ".join(sorted(_SUPPORTED_MEDIA_URL_SCHEMES))
            return {"error": f"replace_selected_media_url must be a direct media URL using one of: {schemes}."}
        context = _summarize_editor_context(editor_context)
        selected_types = set(context.get("selected_element_types") or [])
        if not (selected_types & {"image", "video"}):
            return {"error": "replace_selected_media_url requires a selected image or video element."}
        updates["replace_selected_media_url"] = media_url

    pending_edits.update(updates)
    return {"queued": updates}


async def _apply_live_edits(
    project_id: str,
    project_data: dict,
    current_project_json: dict | None,
    pending_edits: dict,
    editor_context: dict | None,
) -> dict:
    from services.storage import firestore_db as _fdb

    doc = await _fdb.get_project(project_id) or {}
    updates = {**doc}

    if "caption_style" in pending_edits:
        updates["caption_style"] = pending_edits["caption_style"]
        project_data["caption_style"] = pending_edits["caption_style"]
    if "background_music" in pending_edits:
        updates["background_music"] = pending_edits["background_music"]
        project_data["background_music"] = pending_edits["background_music"]
    if "music_volume" in pending_edits:
        updates["music_volume"] = pending_edits["music_volume"]
        project_data["music_volume"] = pending_edits["music_volume"]

    source_project_json = current_project_json or doc.get("project_json") or {}
    patched_json: dict | None = None
    if source_project_json:
        patched_json = _patch_project_json(
            source_project_json,
            pending_edits,
            editor_context=editor_context,
        )
        updates["project_json"] = patched_json
        project_data["project_json"] = patched_json

    await _fdb.save_project(project_id, updates)

    change_summary = ", ".join(
        f"{k}={v}" for k, v in pending_edits.items() if k != "music_volume"
    )
    return {
        "message": f"Done! Applied live edits: {change_summary}. Export when you're ready.",
        "changes": dict(pending_edits),
        "project_json": patched_json,
        "editor_context": _summarize_editor_context(editor_context),
        "requires_export": True,
    }


def _patch_project_json(project_json: dict, changes: dict, editor_context: dict | None = None) -> dict:
    """Patch caption style and music settings in a Twick project_json without re-rendering.

    Updates:
    - Caption track props.capStyle when caption_style changes
    - Music element props.musicPreset / props.volume when background_music / music_volume changes
    - Selected text position when move_selected_text_y_delta is provided
    - Selected image/video src when replace_selected_media_url is provided
    - Overlay text hook insertion when hook_title is provided
    """
    import copy
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
        # Caption track: update capStyle
        if track.get("type") == "caption" and "caption_style" in changes:
            track.setdefault("props", {})["capStyle"] = _CAP_STYLE_MAP.get(
                changes["caption_style"], "text_bg"
            )
        # Music element: update musicPreset / volume
        for elem in track.get("elements", []):
            if "musicPreset" in elem.get("props", {}):
                if "background_music" in changes:
                    elem["props"]["musicPreset"] = changes["background_music"]
                if "music_volume" in changes:
                    elem["props"]["volume"] = changes["music_volume"]

    if next_music_preset is not None:
        _ensure_music_track(patched, next_music_preset, next_music_volume)
    elif "music_volume" in changes:
        track, element = _find_music_track(patched)
        if element:
            element.setdefault("props", {})["volume"] = changes["music_volume"]

    if "move_selected_text_y_delta" in changes:
        delta = float(changes["move_selected_text_y_delta"])
        for _, elem in _find_selected_elements(patched, editor_context):
            if elem.get("type") != "text":
                continue
            frame = elem.get("frame")
            if isinstance(frame, dict):
                frame["y"] = float(frame.get("y", 0.0)) + delta
            else:
                props = elem.setdefault("props", {})
                props["y"] = float(props.get("y", 0.0)) + delta

    if "replace_selected_media_url" in changes:
        src = changes["replace_selected_media_url"]
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
    return patched


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


# ── Text / SSE mode (ADK) ───────────────────────────────────────────────────────

async def run_edit_text_agent(
    project_id: str,
    project_data: dict,
    instruction: str,
    current_project_json: dict | None = None,
    editor_context: dict | None = None,
):
    """Async generator — yields SSE-ready dicts for the text-based quick-action editor.

    Uses ADK (Agent + Runner) with gemini-2.5-flash for fast reasoning.
    Yields agent_step progress events, then a complete event with the patched
    project_json (no video re-render — export triggers recompose separately).
    """
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    settings_env()

    app_name = "edit-agent"
    user_id = "user"
    session_id = str(uuid4())

    # ── ADK tools ───────────────────────────────────────────────────────────────

    def get_project_info(tool_context: ToolContext) -> dict:  # noqa: F841
        """Get current caption style, music, and hook for this video."""
        data = tool_context.state.get("project_data", {})
        return {
            "hook":             data.get("hook", ""),
            "caption_style":    data.get("caption_style", "beast"),
            "background_music": data.get("background_music", "none"),
            "music_volume":     data.get("music_volume", 0.15),
            "platforms":        data.get("platforms", ["instagram_reels"]),
        }

    def get_editor_context(tool_context: ToolContext) -> dict:  # noqa: F841
        """Return current editor selection/playhead state for context-aware edits."""
        context = _summarize_editor_context(tool_context.state.get("editor_context"))
        if context["has_screenshot"]:
            context["screenshot_note"] = (
                "Screenshot metadata is attached for future multimodal tooling; "
                "this text edit flow currently uses the structured editor state only."
            )
        return context

    def queue_edit(
        caption_style: str | None = None,
        background_music: str | None = None,
        music_volume: float | None = None,
        hook_title: str | None = None,
        hook_duration_seconds: float | None = None,
        move_selected_text_y_delta: float | None = None,
        replace_selected_media_url: str | None = None,
        tool_context: ToolContext = None,
    ) -> dict:
        """Queue supported metadata and timeline edits.

        Changes are saved to project metadata immediately.
        The actual video re-render only happens when the user exports.
        """
        pending_edits = tool_context.state.get("pending_edits", {}) if tool_context else {}
        result = _queue_pending_edits(
            pending_edits=pending_edits,
            args={
                "caption_style": caption_style,
                "background_music": background_music,
                "music_volume": music_volume,
                "hook_title": hook_title,
                "hook_duration_seconds": hook_duration_seconds,
                "move_selected_text_y_delta": move_selected_text_y_delta,
                "replace_selected_media_url": replace_selected_media_url,
            },
            editor_context=tool_context.state.get("editor_context") if tool_context else None,
        )
        if tool_context:
            tool_context.state["pending_edits"] = pending_edits
        if "error" in result:
            return result
        return {"queued": result.get("queued", {}), "note": "Changes will be applied to the editor instantly. Export to render a new video."}

    # ── ADK agent ────────────────────────────────────────────────────────────────

    hook = project_data.get("hook", "your video")
    caption_style = project_data.get("caption_style", "beast")
    background_music = project_data.get("background_music", "none")
    editor_context_summary = _summarize_editor_context(editor_context)

    system = (
        f"{_EDIT_SYSTEM}\n\n"
        f"Current project state:\n"
        f"  Hook: \"{hook}\"\n"
        f"  Caption style: {caption_style}\n"
        f"  Background music: {background_music}\n"
        f"  Editor mode: {editor_context_summary['mode']}\n"
        f"  Active panel: {editor_context_summary['active_panel']}\n"
        f"  Playhead seconds: {editor_context_summary['playhead_seconds']}\n"
        f"  Selected element ids: {editor_context_summary['selected_element_ids']}\n"
        f"  Selected element types: {editor_context_summary['selected_element_types']}\n"
        f"  Screenshot attached: {editor_context_summary['has_screenshot']}\n\n"
        "Workflow: call get_project_info and call get_editor_context whenever selection/playhead state matters, then call queue_edit.\n"
        "Use hook_title for requests like 'add a hook title' or 'add a title at the beginning'.\n"
        "Use move_selected_text_y_delta for requests like 'move this selected text up/down'. Negative moves up, positive moves down.\n"
        "Use replace_selected_media_url only when the user provides a direct URL and has selected an image/video element.\n"
        "Do NOT try to render or export — the user will export when ready."
    )

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id,
        state={
            "project_id": project_id,
            "project_data": project_data,
            "pending_edits": {},
            "current_project_json": current_project_json or {},
            "editor_context": editor_context or {},
        },
    )

    agent = Agent(
        name="video_edit_agent",
        model=_TEXT_MODEL,
        instruction=system,
        tools=[get_project_info, get_editor_context, queue_edit],
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=instruction)],
    )

    _LABELS: dict[str, str] = {
        "get_project_info": "Checking your current video settings…",
        "get_editor_context": "Checking your current editor selection…",
        "queue_edit": "Applying edit to timeline…",
    }

    logger.info("ADK edit agent starting: project=%s instruction=%.60s", project_id, instruction)

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                fc = getattr(part, "function_call", None)
                if fc and fc.name in _LABELS:
                    yield {"type": "agent_step", "tool": fc.name, "message": _LABELS[fc.name]}

        session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        pending = (session.state or {}).get("pending_edits", {})

        if not pending:
            yield {"type": "error", "message": "Agent did not queue any changes — try rephrasing your request."}
            return

        # Patch timeline JSON and save metadata to Firestore (no video re-render)
        try:
            result = await _apply_live_edits(
                project_id=project_id,
                project_data=project_data,
                current_project_json=current_project_json,
                pending_edits=pending,
                editor_context=editor_context,
            )
        except Exception as _save_exc:
            logger.warning("Failed to save project edits to Firestore: %s", _save_exc)
            result = {
                "message": "Failed to save live edits.",
                "changes": pending,
                "project_json": None,
                "editor_context": editor_context_summary,
                "requires_export": True,
            }

        logger.info("ADK edit agent completed: project=%s changes=%s", project_id, pending)
        yield {
            "type": "complete",
            **result,
        }

    except Exception as exc:
        logger.exception("ADK edit agent failed: project=%s", project_id)
        yield {"type": "error", "message": str(exc)}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def settings_env() -> None:
    """Set ADK environment variables from app config."""
    from config import get_settings
    s = get_settings()
    if s.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", s.vertex_ai_location)
    elif s.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", s.gemini_api_key)
