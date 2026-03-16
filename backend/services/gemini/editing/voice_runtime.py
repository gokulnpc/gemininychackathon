"""Gemini Live voice runtime for Scout's edit workflow."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from collections import deque
from typing import Literal, NotRequired, TypedDict

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover - import fallback for test envs
    ToolContext = object  # type: ignore[misc,assignment]

from .commands import (
    _build_proposal_from_commands,
    _build_proposal_from_pending_edits,
    _queue_pending_edits,
)
from .constants import _EDIT_SYSTEM, _LIVE_MODEL
from .context import _summarize_editor_context
from .preview import _generate_multi_preview
from .projector import _apply_live_edits, _project_commands

logger = logging.getLogger(__name__)

_STALL_TIMEOUT_SECONDS = 6.0


VoiceLiveTransport = Literal["vertex", "gemini_api"]


class VoiceRealtimeEvent(TypedDict):
    kind: Literal["audio", "activity_start", "activity_end", "done"]
    audio_b64: NotRequired[str]
    turn_id: NotRequired[str]


@dataclass(slots=True)
class _VoiceSessionRestartRequired(Exception):
    turn_id: str | None


def _resolve_live_transport() -> VoiceLiveTransport:
    # The native-audio preview model requires Gemini API key routing;
    # it is not yet available via Vertex AI. GEMINI_API_KEY is set on Cloud Run.
    return "gemini_api"


async def _send_realtime_event(
    session,
    event: VoiceRealtimeEvent,
    *,
    allow_audio_stream_end: bool,
) -> None:
    """Forward a typed realtime event to Gemini Live."""
    from google.genai import types

    kind = event["kind"]
    turn_id = event.get("turn_id")

    if kind == "audio":
        audio_b64 = event.get("audio_b64")
        if not audio_b64:
            logger.debug("Skipping empty audio event turn=%s", turn_id)
            return
        audio_bytes = base64.b64decode(audio_b64)
        logger.debug(
            "Scout edit realtime -> Gemini: audio turn=%s bytes=%d",
            turn_id,
            len(audio_bytes),
        )
        await session.send_realtime_input(
            audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
        )
        return

    if kind == "activity_start":
        logger.info("Scout edit realtime -> Gemini: activity_start turn=%s", turn_id)
        await session.send_realtime_input(activity_start=types.ActivityStart())
        return

    if kind == "activity_end":
        logger.info("Scout edit realtime -> Gemini: activity_end turn=%s", turn_id)
        await session.send_realtime_input(activity_end=types.ActivityEnd())
        return

    if kind == "done":
        if allow_audio_stream_end:
            logger.info("Scout edit realtime -> Gemini: audio_stream_end")
            await session.send_realtime_input(audio_stream_end=True)
        else:
            logger.info("Scout edit realtime -> Gemini: session shutdown (no audio_stream_end)")
        return

    raise ValueError(f"Unsupported realtime event kind: {kind}")


def _build_voice_config(project_data: dict, transport: VoiceLiveTransport):
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
        f"  Background music: {background_music}\n\n"
        "Screen sharing: The user may share their screen during this session. "
        "When screen frames are being sent, you can SEE the user's screen in real time — "
        "reference what you see visually when helping with edits. "
        "When screen sharing is active and the user gives a spatially vague instruction ('that text', 'the element on the left', 'that thing at the top'), look at the screen frames you are receiving and resolve the reference visually — do NOT ask which element."
    )

    realtime_input_config = types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            disabled=True,
        ),
    )
    if transport == "vertex":
        realtime_input_config.activity_handling = types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
        realtime_input_config.turn_coverage = types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY

    config_kwargs: dict = {
        "response_modalities": ["AUDIO"],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "realtime_input_config": realtime_input_config,
        "system_instruction": system,
        "tools": [types.Tool(function_declarations=[
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
                name="get_user_assets",
                description="List the user's uploaded assets for a given category (images, videos, music, voice_memos). Call before drafting insert_media_asset or replace_selected_media.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "category": types.Schema(type="string", description="images | videos | music | voice_memos"),
                    },
                    required=["category"],
                ),
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
                name="draft_edit_command",
                description="Draft a single normalized edit command. Call this to queue edits before applying.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "kind": types.Schema(type="string", description="set_caption_style | set_background_music | set_music_volume | set_voiceover_volume | add_text_overlay | update_selected_text | move_selected_element | replace_selected_media | insert_media_asset | trim_selected_element | delete_selected_element | delete_element_by_id | add_hook_title | move_element_by_id | apply_effect"),
                        "args": types.Schema(type="string", description='JSON-encoded command arguments, e.g. {"preset": "breathing_shadows"} or {"volume": 0.3}. move_element_by_id: {"element_id": "e-xxx", "dy": pixels_delta (positive=down, negative=up, small=30 medium=80 large=150)}. delete_element_by_id: {"element_id": "e-xxx"}. apply_effect: {"effect_key": "glitch|sepia|vignette|pixelate|warp|rgbShift|halftone|hueShift|waveDistort|tvScanlines|hdr|retro70s|bubbleSparkles|heartSparkles", "intensity": 0.0-1.0 (default 1.0)}'),
                        "element_id": types.Schema(type="string", description="Target element ID, if applicable."),
                        "track_id": types.Schema(type="string", description="Target track ID, if applicable."),
                    },
                    required=["kind"],
                ),
            ),
            types.FunctionDeclaration(
                name="apply_live_edits",
                description="Apply all queued edits to the live timeline and save them. Call ONCE after confirming with the user.",
                parameters=types.Schema(type="object", properties={}),
            ),
            types.FunctionDeclaration(
                name="generate_creative_direction",
                description=(
                    "Generate a rich creative direction package with mixed text and generated images. "
                    "Call when the user wants creative ideas, storyboard concepts, visual direction, "
                    "hook suggestions, caption themes, or mood/music recommendations. "
                    "Streams each creative block as it's generated."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "brief": types.Schema(type="string", description="Creative brief — what the user wants to explore."),
                        "mode": types.Schema(type="string", description="social_content | marketing | storybook | educational (default: social_content)"),
                        "art_style": types.Schema(type="string", description="Optional art style for generated images: realism | ghibli | comic | polaroid | disney | painting | creepy_comic"),
                    },
                    required=["brief"],
                ),
            ),
            types.FunctionDeclaration(
                name="generate_thumbnail_options",
                description=(
                    "Generate 2–3 clickbait AI thumbnail image options for this video. "
                    "Call when the user wants a new thumbnail, thumbnail ideas, or a more eye-catching thumbnail. "
                    "If screen sharing is active, the current screen is used as a visual reference. "
                    "Streams each option as a thumbnail_option event."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "brief": types.Schema(type="string", description="Extra context about the video (optional)."),
                        "art_style": types.Schema(type="string", description="realism | ghibli | comic | polaroid | disney (default: realism)"),
                        "count": types.Schema(type="integer", description="Number of options to generate (1–3, default 1)."),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="set_thumbnail",
                description="Apply one of the generated thumbnail options as the project's permanent thumbnail. Call after generate_thumbnail_options and the user picks one.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "option_index": types.Schema(type="integer", description="0-based index of the chosen option."),
                    },
                    required=["option_index"],
                ),
            ),
            types.FunctionDeclaration(
                name="generate_image_for_scene",
                description=(
                    "Generate a brand-new AI image for the currently selected scene element using Gemini image generation. "
                    "Returns a src URL. After calling this, immediately draft replace_selected_media with the returned src and call apply_live_edits."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "prompt": types.Schema(type="string", description="Detailed visual description of the image to generate."),
                        "art_style": types.Schema(type="string", description="realism | ghibli | comic | polaroid | disney | painting | creepy_comic (default: realism)"),
                    },
                    required=["prompt"],
                ),
            ),
            types.FunctionDeclaration(
                name="edit_selected_image",
                description=(
                    "Edit the currently selected scene image using AI — modify its style, mood, lighting, weather, "
                    "colours, or content based on a natural-language instruction. "
                    "Unlike generate_image_for_scene (generates a new image), this EDITS the existing image. "
                    "After this returns a src URL, draft replace_selected_media with it and call apply_live_edits."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "instruction": types.Schema(
                            type="string",
                            description="Edit instruction, e.g. 'make it darker', 'add snow', 'change sky to orange'",
                        ),
                        "element_id": types.Schema(
                            type="string",
                            description="Optional element_id of the image to edit.",
                        ),
                    },
                    required=["instruction"],
                ),
            ),
            types.FunctionDeclaration(
                name="generate_storyboard",
                description="Generate a manga/manhwa visual story from a brief using the interleaved AI model. Streams panel images to the chat.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "brief": types.Schema(type="string", description="What the story is about"),
                        "art_style": types.Schema(type="string", description="Art style. Default: manga"),
                        "num_scenes": types.Schema(type="integer", description="Number of panels (3–6). Default: 4"),
                    },
                    required=["brief"],
                ),
            ),
            types.FunctionDeclaration(
                name="build_timeline_from_storyboard",
                description="Assemble the storyboard panels into the video timeline. Call immediately after generate_storyboard — no user confirmation needed.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "scene_duration_seconds": types.Schema(type="integer", description="Duration per scene in seconds. Default: 4"),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="rename_project",
                description="Set the project title / hook shown in the editor header.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "title": types.Schema(type="string", description="New project title (≤120 chars)."),
                    },
                    required=["title"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_video_metadata",
                description=(
                    "Set the YouTube/social media title, description, and hashtags for this video. "
                    "Saves them to the project so they are used automatically when publishing."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "title":       types.Schema(type="string", description="YouTube title (max 100 chars)"),
                        "description": types.Schema(type="string", description="YouTube description (max 5000 chars)"),
                        "hashtags":    types.Schema(type="array", items=types.Schema(type="string"), description="List of hashtags without #"),
                    },
                    required=["title"],
                ),
            ),
            types.FunctionDeclaration(
                name="propose_scripts",
                description=(
                    "Present 2-3 short script concept cards to the user so they can pick a story direction. "
                    "Call this FIRST when the user wants to create a video, story, comic, or manga from scratch."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "proposals": types.Schema(
                            type="array",
                            description="2-3 script concept options",
                            items=types.Schema(
                                type="object",
                                properties={
                                    "title": types.Schema(type="string", description="Short catchy concept title"),
                                    "hook":  types.Schema(type="string", description="Opening hook — 1 punchy sentence"),
                                    "arc":   types.Schema(type="string", description="Story arc summary — 2 sentences"),
                                },
                                required=["title", "hook", "arc"],
                            ),
                        ),
                    },
                    required=["proposals"],
                ),
            ),
        ])],
    }
    if transport == "vertex":
        config_kwargs["explicit_vad_signal"] = True

    return types.LiveConnectConfig(
        **config_kwargs,
    )


def _compact_tool_result_for_gemini(name: str, result: dict) -> dict:
    """Return a small tool result that is safe to feed back into Gemini Live."""
    if not isinstance(result, dict):
        return {"status": "ok"}

    if "error" in result:
        return {"error": str(result["error"])}

    if name == "get_project_info":
        return {
            "hook": result.get("hook", ""),
            "caption_style": result.get("caption_style", "beast"),
            "background_music": result.get("background_music", "none"),
            "music_volume": result.get("music_volume", 0.15),
            "platforms": result.get("platforms", []),
        }

    if name == "get_editor_context":
        return {
            "active_panel": result.get("active_panel"),
            "playhead_seconds": result.get("playhead_seconds"),
            "selected_element_ids": result.get("selected_element_ids", []),
            "selected_track_ids": result.get("selected_track_ids", []),
            "selected_element_types": result.get("selected_element_types", []),
            "timeline_elements": result.get("timeline_elements", []),
        }

    if name == "get_user_assets":
        assets = result.get("assets") or []
        return {
            "category": result.get("category", "images"),
            "asset_count": len(assets),
            "asset_names": [asset.get("filename", "") for asset in assets[:5] if isinstance(asset, dict)],
        }

    if name == "generate_style_preview":
        options = result.get("options") or result.get("preview_options") or []
        return {
            "status": "preview_generated",
            "preview_id": result.get("preview_id"),
            "option_count": len(options),
        }

    if name == "draft_edit_command":
        drafted = result.get("drafted") if isinstance(result.get("drafted"), dict) else {}
        return {
            "status": "queued",
            "kind": drafted.get("kind"),
        }

    if name == "apply_live_edits":
        return {
            "status": "applied",
            "summary": result.get("message", "Live edits applied."),
            "requires_export": result.get("requires_export", True),
        }

    if name == "generate_creative_direction":
        return {
            "status": result.get("status", "ok"),
            "block_count": result.get("block_count", 0),
        }

    if name == "generate_thumbnail_options":
        return {
            "status": result.get("status", "ok"),
            "option_count": result.get("option_count", 0),
            "options": result.get("options", []),
        }

    if name == "set_thumbnail":
        return {
            "status": result.get("status", "ok"),
            "thumbnail_url": result.get("thumbnail_url", ""),
        }

    if name == "generate_image_for_scene":
        return {
            "status": result.get("status", "ok"),
            "src": result.get("src", ""),
        }

    if name == "generate_storyboard":
        return {
            "status": result.get("status", "ok"),
            "count": result.get("count", 0),
            "descriptions": result.get("descriptions", []),
        }

    compact: dict = {}
    for key, value in result.items():
        if key in {"project_json", "changes", "editor_context", "creative_blocks", "images"}:
            continue
        if isinstance(value, list):
            compact[key] = value[:5]
        else:
            compact[key] = value
    return compact


async def _dispatch_voice_tool(
    name: str,
    args: dict,
    project_id: str,
    project_data: dict,
    draft_commands: list[dict],
    current_project_json: dict | None,
    editor_context: dict | None,
    on_event: Callable,
    decision_queue: asyncio.Queue | None = None,
    get_live_state: Callable[[], dict] | None = None,
    uid: str = "",
) -> dict:
    """Route a Live API function_call to the correct edit tool."""
    if name == "get_project_info":
        _script = project_data.get("script") or {}
        _scenes = _script.get("scenes") or []
        _scene_summaries = [
            s.get("visual_prompt") or s.get("voiceover_text") or ""
            for s in _scenes[:5]
        ]
        _social_copy = (_script.get("social_copy") or {}).get("youtube") or {}
        return {
            "hook":                 project_data.get("hook", ""),
            "caption_style":        project_data.get("caption_style", "beast"),
            "background_music":     project_data.get("background_music", "none"),
            "music_volume":         project_data.get("music_volume", 0.15),
            "platforms":            project_data.get("platforms", ["instagram_reels"]),
            "scene_summaries":      [s for s in _scene_summaries if s],
            "youtube_title":        _social_copy.get("title", ""),
            "youtube_description":  _social_copy.get("caption", ""),
            "youtube_hashtags":     _social_copy.get("hashtags", []),
        }

    if name == "get_editor_context":
        live_state = get_live_state() if get_live_state else {}
        pj = live_state.get("project_json") or current_project_json
        return _summarize_editor_context(editor_context, project_json=pj)

    if name == "get_user_assets":
        category = args.get("category", "images")
        from services.storage.assets import list_user_assets
        assets = await list_user_assets(uid, category, limit=20) if uid else []
        return {"category": category, "assets": assets}

    if name == "generate_style_preview":
        from .preview import _generate_multi_preview
        return await _generate_multi_preview(
            brief=args.get("brief", "video concept"),
            art_style=args.get("art_style"),
            on_event=on_event,
        )

    if name == "draft_edit_command":
        raw_args = args.get("args") or {}
        if isinstance(raw_args, str):
            import json as _json
            try:
                raw_args = _json.loads(raw_args)
            except Exception:
                raw_args = {}
        cmd: dict = {"kind": args.get("kind"), "args": raw_args}
        if args.get("element_id"):
            cmd["element_id"] = args["element_id"]
        if args.get("track_id"):
            cmd["track_id"] = args["track_id"]
        draft_commands.append(cmd)
        return {"drafted": cmd}

    if name == "queue_edit":
        pending_edits = {}
        result = _queue_pending_edits(
            pending_edits=pending_edits,
            args=args,
            editor_context=editor_context,
        )
        if "error" in result:
            return result
        prop = _build_proposal_from_pending_edits(pending_edits, editor_context)
        draft_commands.extend(prop["commands"])
        return {"queued": dict(pending_edits)}

    if name == "apply_live_edits":
        if not draft_commands:
            return {"error": "No edits queued. Call draft_edit_command first."}

        proposal = _build_proposal_from_commands(draft_commands)

        if decision_queue is None:
            patched, applied, errors = await _project_commands(
                current_project_json or {}, draft_commands, editor_context, uid=uid
            )
            draft_commands.clear()
            if errors:
                return {"error": f"Some commands were rejected: {'; '.join(errors)}"}
            if not applied:
                return {"error": "No commands were applied."}
            result = await _apply_live_edits(
                project_id=project_id,
                project_data=project_data,
                patched_project_json=patched,
                applied_changes=applied,
                editor_context=editor_context,
            )
            try:
                await on_event({"type": "complete", **result})
            except Exception:
                pass
            return result

        try:
            await on_event({"type": "proposal", "proposal": proposal})
        except Exception:
            pass

        try:
            decision = await asyncio.wait_for(decision_queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            try:
                await on_event({
                    "type": "proposal_rejected",
                    "proposal_id": proposal["proposal_id"],
                    "reason": "timeout",
                })
            except Exception:
                pass
            return {"status": "rejected", "reason": "timeout"}

        if decision.get("decision") != "confirm":
            try:
                await on_event({"type": "proposal_rejected", "proposal_id": proposal["proposal_id"]})
            except Exception:
                pass
            return {"status": "rejected"}

        confirmed_commands = decision.get("commands") or []
        live_state = get_live_state() if get_live_state else {}
        source_json = live_state.get("project_json") or current_project_json or {}
        ec = live_state.get("editor_context") or editor_context

        if confirmed_commands:
            patched, applied, errors = await _project_commands(source_json, confirmed_commands, ec, uid=uid)
        else:
            patched, applied, errors = await _project_commands(source_json, draft_commands, ec, uid=uid)

        draft_commands.clear()

        if errors:
            result = {"error": f"Some confirmed commands were rejected: {'; '.join(errors)}"}
            try:
                await on_event({"type": "proposal_rejected", "proposal_id": proposal["proposal_id"], "reason": "projector_error"})
            except Exception:
                pass
            return result

        if not applied:
            result = {"error": "No confirmed commands were applied."}
            try:
                await on_event({"type": "proposal_rejected", "proposal_id": proposal["proposal_id"], "reason": "no_changes"})
            except Exception:
                pass
            return result

        result = await _apply_live_edits(
            project_id=project_id,
            project_data=project_data,
            patched_project_json=patched,
            applied_changes=applied,
            editor_context=ec,
        )
        try:
            await on_event({"type": "applied", "proposal_id": proposal["proposal_id"], **result})
        except Exception:
            pass
        return result

    if name == "generate_creative_direction":
        brief = args.get("brief", "creative video concept")
        mode = args.get("mode", "social_content")
        art_style = args.get("art_style")
        _live = get_live_state() if get_live_state else {}
        _ec = editor_context or {}
        reference_b64 = (
            _live.get("latest_screen_frame_b64")
            or (_ec.get("screenshot") or {}).get("image_b64")
        )
        try:
            from services.gemini.interleaved import generate_creative_package
            blocks, _ = await generate_creative_package(
                brief=brief, mode=mode, art_style=art_style,
                reference_image_b64=reference_b64,
            )
            for block in blocks:
                with contextlib.suppress(Exception):
                    await on_event({"type": "creative_block", "block": block})
            return {"status": "ok", "block_count": len(blocks)}
        except Exception as exc:
            logger.warning("generate_creative_direction failed: %s", exc)
            return {"error": str(exc)}

    if name == "generate_image_for_scene":
        import os as _os_gen
        import tempfile as _tmp_gen
        from uuid import uuid4 as _uuid4_gen

        prompt = args.get("prompt", "")
        art_style = args.get("art_style", "realism")
        if not prompt:
            return {"error": "prompt is required"}

        _live_gen = get_live_state() if get_live_state else {}
        _ec_gen = editor_context or {}
        reference_b64 = (
            _live_gen.get("latest_screen_frame_b64")
            or (_ec_gen.get("screenshot") or {}).get("image_b64")
        )

        full_prompt = (
            f"Generate a single high-quality scene image: {prompt}. "
            f"Art style: {art_style}. "
            "Optimised for a short-form video scene. "
            "No text overlays. Output exactly one image."
        )

        try:
            from services.gemini.interleaved import _invoke_interleaved_with_image as _gen_img
            from services.storage import gcs as _gcs_gen
            import base64 as _b64_gen

            blocks = await asyncio.to_thread(_gen_img, full_prompt, reference_b64)
            image_blocks = [b for b in blocks if b.get("type") == "image"]
            if not image_blocks:
                return {"error": "Image generation returned no images — try rephrasing the prompt."}

            chosen = image_blocks[0]
            image_bytes = _b64_gen.b64decode(chosen["content"])
            mime = chosen.get("mime_type", "image/jpeg")
            suffix = ".jpg" if "jpeg" in mime else ".png"
            fd, tmp_path = _tmp_gen.mkstemp(suffix=suffix, prefix="scene_gen_")
            try:
                _os_gen.write(fd, image_bytes)
            finally:
                _os_gen.close(fd)

            gcs_key = f"projects/{project_id}/generated/{_uuid4_gen()}{suffix}"
            src_url = await _gcs_gen.upload_file(tmp_path, gcs_key, mime)
            _os_gen.unlink(tmp_path)

            with contextlib.suppress(Exception):
                await on_event({"type": "creative_block", "block": {"type": "image", "content": chosen["content"], "mime_type": mime}})

            return {"status": "ok", "src": src_url}
        except Exception as exc:
            logger.warning("generate_image_for_scene failed: %s", exc)
            return {"error": str(exc)}

    if name == "generate_storyboard":
        brief_gsb = args.get("brief", "")
        art_style_gsb = args.get("art_style", "manga")
        num_scenes_gsb = min(max(int(args.get("num_scenes", 4)), 3), 6)

        prompt_gsb = (
            f"Create a {num_scenes_gsb}-panel manga story for: {brief_gsb}. "
            f"Art style: {art_style_gsb}."
        )
        try:
            from services.gemini.interleaved import generate_creative_package as _gen_sb_v
            blocks_gsb, _ = await _gen_sb_v(prompt_gsb, mode="manga", art_style=art_style_gsb)

            drafts_gsb: list[dict] = []
            pending_caption_gsb = ""
            for block_gsb in blocks_gsb:
                if block_gsb.get("type") == "text":
                    pending_caption_gsb = block_gsb["content"]
                elif block_gsb.get("type") == "image":
                    panel_block_gsb = {
                        "type": "panel",
                        "content": block_gsb["content"],
                        "mime_type": block_gsb.get("mime_type", "image/jpeg"),
                        "caption": pending_caption_gsb,
                    }
                    with contextlib.suppress(Exception):
                        await on_event({"type": "creative_block", "block": panel_block_gsb})
                    drafts_gsb.append({
                        "image_b64": block_gsb["content"],
                        "mime_type": block_gsb.get("mime_type", "image/jpeg"),
                        "description": pending_caption_gsb or f"Panel {len(drafts_gsb) + 1}",
                    })
                    pending_caption_gsb = ""

            # Upload each panel to GCS; store only URLs (no base64 in Firestore)
            import base64 as _b64_gsb, os as _os_gsb
            from uuid import uuid4 as _uuid4_gsb
            from services.storage import gcs as _gcs_gsb
            from services.storage import firestore_db as _fdb_gsb

            draft_urls_gsb: list[dict] = []
            for i_gsb, draft_gsb in enumerate(drafts_gsb):
                mime_gsb = draft_gsb.get("mime_type", "image/jpeg")
                suffix_gsb = ".jpg" if "jpeg" in mime_gsb else ".png"
                tmp_gsb = f"/tmp/sb_draft_{_uuid4_gsb().hex}{suffix_gsb}"
                with open(tmp_gsb, "wb") as _f_gsb:
                    _f_gsb.write(_b64_gsb.b64decode(draft_gsb["image_b64"]))
                gcs_key_gsb = f"projects/{project_id}/storyboard_draft_{i_gsb}{suffix_gsb}"
                url_gsb = await _gcs_gsb.upload_file(tmp_gsb, gcs_key_gsb, mime_gsb)
                with contextlib.suppress(OSError):
                    _os_gsb.unlink(tmp_gsb)
                draft_urls_gsb.append({"src": url_gsb, "mime_type": mime_gsb, "description": draft_gsb["description"]})

            project_data["_storyboard_draft_urls"] = draft_urls_gsb
            project_data.pop("_storyboard_drafts", None)
            await _fdb_gsb.save_project(project_id, project_data)

            return {
                "status": "ok",
                "count": len(draft_urls_gsb),
                "descriptions": [d_gsb["description"] for d_gsb in draft_urls_gsb],
            }
        except Exception as _gsb_exc:
            logger.warning("generate_storyboard (voice) failed: %s", _gsb_exc)
            return {"error": str(_gsb_exc)}

    if name == "rename_project":
        new_title_rn = str(args.get("title", "")).strip()[:120]
        if not new_title_rn:
            return {"error": "title is required"}
        try:
            from services.storage import firestore_db as _fdb_rn
            project_data["hook"] = new_title_rn
            await _fdb_rn.save_project(project_id, project_data)
            with contextlib.suppress(Exception):
                await on_event({"type": "project_renamed", "hook": new_title_rn})
            return {"status": "ok", "title": new_title_rn}
        except Exception as _rn_exc:
            logger.warning("rename_project (voice) failed: %s", _rn_exc)
            return {"error": str(_rn_exc)}

    if name == "set_video_metadata":
        vm_title = str(args.get("title", "")).strip()[:100]
        vm_desc  = str(args.get("description", "")).strip()[:5000]
        vm_tags  = [str(t).strip().lstrip("#") for t in (args.get("hashtags") or []) if t][:30]
        try:
            from services.storage import firestore_db as _fdb_vm
            _script_vm = project_data.setdefault("script", {})
            _sc_vm = _script_vm.setdefault("social_copy", {})
            _meta_vm = {"title": vm_title, "caption": vm_desc, "hashtags": vm_tags}
            for _pl in ("youtube", "youtube_shorts", "instagram", "instagram_reels", "tiktok"):
                _sc_vm[_pl] = _meta_vm
            if vm_title:
                project_data["hook"] = vm_title
            await _fdb_vm.save_project(project_id, project_data)
            with contextlib.suppress(Exception):
                await on_event({"type": "project_renamed", "hook": vm_title})
            return {"status": "ok", "title": vm_title, "hashtags": vm_tags}
        except Exception as _vm_exc:
            logger.warning("set_video_metadata (voice) failed: %s", _vm_exc)
            return {"error": str(_vm_exc)}

    if name == "build_timeline_from_storyboard":
        duration_tl_v = int(args.get("scene_duration_seconds", 4))
        draft_urls_tl = project_data.get("_storyboard_draft_urls", [])
        if not draft_urls_tl:
            return {"error": "No storyboard found. Call generate_storyboard first."}
        try:
            commands_tl_v = [
                {
                    "kind": "insert_media_asset",
                    "args": {
                        "src": d_tl_v["src"],
                        "start_seconds": i_tl_v * duration_tl_v,
                        "duration_seconds": duration_tl_v,
                        "media_kind": "image",
                        "name": f"Scene {i_tl_v + 1}",
                        "track_name": f"Scene {i_tl_v + 1}",
                    },
                }
                for i_tl_v, d_tl_v in enumerate(draft_urls_tl)
            ]
            source_json_v = current_project_json or {}
            patched_v, applied_v, errors_v = await _project_commands(source_json_v, commands_tl_v, editor_context, uid=uid)
            if errors_v:
                return {"error": f"Some commands rejected: {'; '.join(errors_v)}"}
            if not applied_v:
                return {"error": "No commands applied."}
            await _apply_live_edits(
                project_id=project_id,
                project_data=project_data,
                patched_project_json=patched_v,
                applied_changes=applied_v,
                editor_context=editor_context,
            )
            # Emit project_json so the frontend player updates without requiring a page refresh
            await on_event({
                "type": "applied",
                "project_json": patched_v,
                "changes": applied_v,
                "message": f"Built timeline with {len(commands_tl_v)} scenes.",
            })
            return {"status": "ok", "scenes_added": len(commands_tl_v), "total_duration_seconds": len(commands_tl_v) * duration_tl_v}
        except Exception as _tl_v_exc:
            logger.warning("build_timeline_from_storyboard (voice) failed: %s", _tl_v_exc)
            return {"error": str(_tl_v_exc)}

    if name == "edit_selected_image":
        instruction_ei = args.get("instruction", "")
        element_id_ei = args.get("element_id", "")
        try:
            import base64 as _b64_ei
            import os as _os_ei
            from uuid import uuid4 as _uuid4_ei
            from services.gemini.interleaved import _invoke_interleaved_with_image as _gen_ei
            from services.storage import gcs as _gcs_ei

            _ec_ei = editor_context or {}

            # Resolve element_id: only use explicitly selected element (no fallbacks)
            if not element_id_ei:
                _sel_ei = (_ec_ei.get("selected_element_ids") or [])
                element_id_ei = _sel_ei[0] if _sel_ei else ""

            if not element_id_ei:
                return {
                    "status": "error",
                    "error": "No image selected. Please click a scene on the timeline first, then try again.",
                }

            # Fetch image from selected element src only — no screen share fallback
            source_b64_ei: str | None = None
            if current_project_json and element_id_ei:
                for _track_ei in (current_project_json.get("tracks") or []):
                    for _el_ei in (_track_ei.get("elements") or []):
                        if _el_ei.get("id") == element_id_ei:
                            _src_ei = (_el_ei.get("props") or {}).get("src") or _el_ei.get("src")
                            if _src_ei and not _src_ei.startswith("data:"):
                                import httpx as _httpx_ei
                                async with _httpx_ei.AsyncClient(timeout=10) as _c_ei:
                                    _r_ei = await _c_ei.get(_src_ei)
                                    source_b64_ei = _b64_ei.b64encode(_r_ei.content).decode()
                            break

            if not source_b64_ei:
                return {
                    "status": "error",
                    "error": "Could not load the selected image — make sure a scene with an image is selected.",
                }

            edit_prompt_ei = (
                f"Edit this image as instructed: {instruction_ei}. "
                "Preserve the overall composition and subject. Apply only the requested changes. "
                "Output exactly one edited image. 9:16 vertical format."
            )
            blocks_ei = await asyncio.to_thread(_gen_ei, edit_prompt_ei, source_b64_ei)
            image_blocks_ei = [b for b in blocks_ei if b.get("type") == "image"]
            if not image_blocks_ei:
                return {"status": "error", "error": "Model returned no edited image — try rephrasing the instruction."}

            chosen_ei = image_blocks_ei[0]
            img_bytes_ei = _b64_ei.b64decode(chosen_ei["content"])
            mime_ei = chosen_ei.get("mime_type", "image/jpeg")
            suffix_ei = ".jpg" if "jpeg" in mime_ei else ".png"
            tmp_ei = f"/tmp/edit_{_uuid4_ei().hex}{suffix_ei}"
            with open(tmp_ei, "wb") as f_ei:
                f_ei.write(img_bytes_ei)
            gcs_key_ei = f"projects/{project_id}/edited/{_uuid4_ei().hex}{suffix_ei}"
            src_url_ei = await _gcs_ei.upload_file(tmp_ei, gcs_key_ei, mime_ei)
            with contextlib.suppress(OSError):
                _os_ei.unlink(tmp_ei)
            with contextlib.suppress(Exception):
                await on_event({"type": "creative_block", "block": {"type": "image", "content": chosen_ei["content"], "mime_type": mime_ei}})

            # Auto-replace selected element — no confirmation card needed
            try:
                _ar_patched, _ar_applied, _ar_errors = await _project_commands(
                    current_project_json or {},
                    [{"kind": "replace_selected_media", "args": {"src": src_url_ei}}],
                    editor_context,
                    uid=uid,
                )
                if _ar_applied and not _ar_errors:
                    await _apply_live_edits(
                        project_id=project_id,
                        project_data=project_data,
                        patched_project_json=_ar_patched,
                        applied_changes=_ar_applied,
                        editor_context=editor_context,
                    )
                    return {"status": "ok", "src": src_url_ei, "replaced": True}
            except Exception as _ar_exc:
                logger.warning("edit_selected_image auto-replace failed: %s", _ar_exc)

            return {"status": "ok", "src": src_url_ei}
        except Exception as exc:
            logger.warning("edit_selected_image failed: %s", exc)
            return {"error": str(exc)}

    if name == "propose_scripts":
        proposals_gsb = args.get("proposals", [])
        with contextlib.suppress(Exception):
            await on_event({"type": "script_proposals", "proposals": proposals_gsb})
        return {"status": "ok", "count": len(proposals_gsb)}

    if name == "generate_thumbnail_options":
        from services.gemini.interleaved import generate_thumbnail_options as _gen_thumbs

        live_state = get_live_state() if get_live_state else {}
        hook = project_data.get("hook", "")
        brief = args.get("brief", "")
        art_style = args.get("art_style", "realism")
        count = min(3, max(1, int(args.get("count", 1))))
        reference_b64 = live_state.get("latest_screen_frame_b64")

        try:
            options = await _gen_thumbs(
                hook=hook,
                brief=brief,
                reference_image_b64=reference_b64,
                art_style=art_style,
                count=count,
            )
            result_options = []
            for i, opt in enumerate(options):
                with contextlib.suppress(Exception):
                    await on_event({
                        "type": "thumbnail_option",
                        "index": i,
                        "image_b64": opt["image_b64"],
                        "mime_type": opt.get("mime_type", "image/jpeg"),
                    })
                result_options.append({"index": i, "mime_type": opt.get("mime_type", "image/jpeg")})
            # Upload each draft to GCS; store only URLs in Firestore (no base64 in Firestore)
            import os as _os_td, base64 as _b64_td
            from uuid import uuid4 as _uuid4_td
            from services.storage import gcs as _gcs_td
            from services.storage import firestore_db as _fdb_td

            draft_urls: list[str] = []
            for i, opt in enumerate(options):
                mime_td = opt.get("mime_type", "image/jpeg")
                suffix_td = ".jpg" if "jpeg" in mime_td else ".png"
                tmp_td = f"/tmp/thumb_draft_{_uuid4_td().hex}{suffix_td}"
                with open(tmp_td, "wb") as f:
                    f.write(_b64_td.b64decode(opt["image_b64"]))
                gcs_key_td = f"projects/{project_id}/thumbnail_draft_{i}{suffix_td}"
                url_td = await _gcs_td.upload_file(tmp_td, gcs_key_td, mime_td)
                with contextlib.suppress(OSError):
                    _os_td.unlink(tmp_td)
                draft_urls.append(url_td)

            project_data["_thumbnail_draft_urls"] = draft_urls
            project_data.pop("_thumbnail_drafts", None)  # remove old broken format if present
            await _fdb_td.save_project(project_id, project_data)  # full doc save (correct)
            return {"status": "ok", "option_count": len(options), "options": result_options}
        except Exception as exc:
            logger.warning("generate_thumbnail_options failed: %s", exc)
            return {"error": str(exc)}

    if name == "set_thumbnail":
        option_index = int(args.get("option_index", 0))
        draft_urls = project_data.get("_thumbnail_draft_urls", [])
        if not draft_urls or option_index >= len(draft_urls):
            return {"error": "No thumbnail options available — call generate_thumbnail_options first."}

        try:
            from services.storage import firestore_db as _fdb_st

            thumbnail_url = draft_urls[option_index]
            project_data["thumbnail_url"] = thumbnail_url
            project_data.pop("_thumbnail_draft_urls", None)
            project_data.pop("_thumbnail_drafts", None)  # clean up old format
            await _fdb_st.save_project(project_id, project_data)

            with contextlib.suppress(Exception):
                await on_event({"type": "thumbnail_applied", "thumbnail_url": thumbnail_url})

            return {"status": "ok", "thumbnail_url": thumbnail_url}
        except Exception as exc:
            logger.warning("set_thumbnail failed: %s", exc)
            return {"error": str(exc)}

    return {"error": f"Unknown tool: {name}"}


def _update_transcript_buffer(parts: list[str], text: str | None) -> str:
    """Merge incremental transcript fragments without duplicating whole-turn text."""
    normalized = (text or "").strip()
    if not normalized:
        return " ".join(parts).strip()

    current = " ".join(parts).strip()
    if not current:
        parts[:] = [normalized]
    elif normalized == current or current.startswith(normalized):
        pass
    elif normalized.startswith(current):
        parts[:] = [normalized]
    else:
        parts.append(normalized)

    return " ".join(parts).strip()


async def run_edit_voice_agent(
    project_id: str,
    project_data: dict,
    audio_queue: asyncio.Queue[VoiceRealtimeEvent],
    get_live_state: Callable[[], dict] | None,
    on_event: Callable[[dict], Coroutine],
    on_audio: Callable[[bytes], Coroutine],  # replaces async generator yield
    on_ready: Callable[[VoiceLiveTransport], Coroutine] | None = None,
    decision_queue: asyncio.Queue | None = None,
    uid: str = "",
    frame_queue: asyncio.Queue | None = None,
) -> None:
    """Run the Scout edit voice session with reconnect recovery for Gemini API stalls."""
    from google.genai import types
    from services.gemini.client import get_client

    transport = _resolve_live_transport()
    client = get_client(force_api_key=transport == "gemini_api")
    draft_commands: list[dict] = []
    session_restarted = False
    _client_closed: list[bool] = [False]  # set when client sends "done"

    while True:
        live_config = _build_voice_config(project_data, transport)
        session_turn: dict[str, str | None] = {
            "input_turn_id": None,
            "response_turn_id": None,
        }
        pending_turn_ids: deque[str] = deque()
        loop = asyncio.get_running_loop()
        stall_deadline: float | None = None
        stall_turn_id: str | None = None

        logger.info(
            "Scout edit voice session starting: project=%s transport=%s",
            project_id,
            transport,
        )

        try:
            async with client.aio.live.connect(model=_LIVE_MODEL, config=live_config) as session:
                if session_restarted:
                    with contextlib.suppress(Exception):
                        await on_event({"type": "session_restarted", "transport": transport})
                elif on_ready is not None:
                    await on_ready(transport)

                def _current_response_turn_id() -> str | None:
                    if session_turn["response_turn_id"] is not None:
                        return session_turn["response_turn_id"]
                    if pending_turn_ids:
                        session_turn["response_turn_id"] = pending_turn_ids[0]
                        return session_turn["response_turn_id"]
                    return session_turn["input_turn_id"]

                def _arm_stall_watch(turn_id: str | None) -> None:
                    nonlocal stall_deadline, stall_turn_id
                    if transport != "gemini_api":
                        return
                    stall_turn_id = turn_id
                    stall_deadline = loop.time() + _STALL_TIMEOUT_SECONDS
                    logger.debug(
                        "Scout edit Live stall watch armed turn=%s timeout=%ss",
                        turn_id,
                        _STALL_TIMEOUT_SECONDS,
                    )

                def _clear_stall_watch(reason: str, turn_id: str | None) -> None:
                    nonlocal stall_deadline, stall_turn_id
                    if transport != "gemini_api" or stall_deadline is None:
                        return
                    logger.debug(
                        "Scout edit Live stall watch cleared turn=%s reason=%s",
                        turn_id,
                        reason,
                    )
                    stall_deadline = None
                    stall_turn_id = None

                async def _client_to_gemini() -> None:
                    """Drain audio_queue and forward typed realtime events to Gemini."""
                    while True:
                        event = await audio_queue.get()
                        if event["kind"] == "activity_start":
                            session_turn["input_turn_id"] = event.get("turn_id")
                        elif event["kind"] == "activity_end":
                            turn_id = event.get("turn_id")
                            if turn_id:
                                pending_turn_ids.append(turn_id)
                            _arm_stall_watch(turn_id)
                        elif event["kind"] == "screen_share_started":
                            # Wait for ~2 frames to arrive at 1 FPS before triggering analysis
                            await asyncio.sleep(2.0)
                            await session.send_client_content(
                                turns=[{
                                    "role": "user",
                                    "parts": [{
                                        "text": (
                                            "The user just enabled screen sharing. "
                                            "Look at what you can see on their screen and describe 1\u20132 specific things you notice "
                                            "about their video project \u2014 visual issues, layout, caption positioning, "
                                            "music fit, or anything that could be improved. "
                                            "Be specific and concise. Maximum 2 sentences."
                                        ),
                                    }],
                                }],
                                turn_complete=True,
                            )
                            await on_event({"type": "screen_analysis_started"})
                        elif event["kind"] == "send_text":
                            text = event.get("text", "")
                            if text:
                                await session.send_client_content(
                                    turns=[{"role": "user", "parts": [{"text": text}]}],
                                    turn_complete=True,
                                )
                                await on_event({"type": "screen_analysis_started"})
                        elif event["kind"] == "done":
                            session_turn["input_turn_id"] = None

                        with contextlib.suppress(Exception):
                            await _send_realtime_event(
                                session,
                                event,
                                allow_audio_stream_end=False,
                            )

                        if event["kind"] == "done":
                            _client_closed[0] = True
                            return

                async def _stall_monitor() -> None:
                    while True:
                        await asyncio.sleep(0.1)
                        if stall_deadline is None:
                            continue
                        if loop.time() >= stall_deadline:
                            logger.warning(
                                "Scout edit Live stall detected turn=%s transport=%s",
                                stall_turn_id,
                                transport,
                            )
                            raise _VoiceSessionRestartRequired(stall_turn_id)

                async def _gemini_to_client() -> None:
                    """Receive from Gemini forever. Never breaks on turn_complete."""
                    tool_queue: asyncio.Queue = asyncio.Queue()
                    user_parts: list[str] = []
                    agent_parts: list[str] = []

                    async def _process_tools() -> None:
                        """Process tool calls from a non-blocking queue."""
                        while True:
                            fc = await tool_queue.get()
                            try:
                                args = dict(fc.args) if fc.args else {}
                                logger.info("Scout edit tool call: %s(%s)", fc.name, list(args.keys()))
                                live_state = get_live_state() if get_live_state else {}
                                result = await _dispatch_voice_tool(
                                    fc.name,
                                    args,
                                    project_id,
                                    project_data,
                                    draft_commands,
                                    live_state.get("project_json"),
                                    live_state.get("editor_context"),
                                    on_event,
                                    decision_queue=None,
                                    get_live_state=get_live_state,
                                    uid=uid,
                                )
                                with contextlib.suppress(Exception):
                                    await on_event({"type": "tool_event", "name": fc.name, **result})
                                gemini_result = _compact_tool_result_for_gemini(fc.name, result)
                                with contextlib.suppress(Exception):
                                    await session.send_tool_response(
                                        function_responses=[types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": gemini_result},
                                        )]
                                    )
                            finally:
                                tool_queue.task_done()

                    tool_task = asyncio.create_task(_process_tools())
                    try:
                        while True:  # re-enter receive() after each turn for multi-turn sessions
                            async for response in session.receive():
                                server_content = getattr(response, "server_content", None)
                                response_turn_id = _current_response_turn_id()
                                model_turn = getattr(server_content, "model_turn", None) if server_content else None
                                model_parts = list(getattr(model_turn, "parts", []) or [])

                                out_t = getattr(server_content, "output_transcription", None) if server_content else None
                                if out_t and getattr(out_t, "text", None):
                                    text = _update_transcript_buffer(agent_parts, out_t.text)
                                    _clear_stall_watch("output_transcription", response_turn_id)
                                    logger.debug(
                                        "Scout edit Live agent transcript turn=%s text=%s",
                                        response_turn_id,
                                        out_t.text.strip(),
                                    )
                                    with contextlib.suppress(Exception):
                                        await on_event({
                                            "type": "agent_transcript",
                                            "text": text,
                                            "turn_id": response_turn_id,
                                        })

                                in_t = getattr(server_content, "input_transcription", None) if server_content else None
                                if in_t and getattr(in_t, "text", None):
                                    text = _update_transcript_buffer(user_parts, in_t.text)
                                    _clear_stall_watch("input_transcription", response_turn_id)
                                    logger.debug(
                                        "Scout edit Live user transcript turn=%s text=%s",
                                        response_turn_id,
                                        in_t.text.strip(),
                                    )
                                    with contextlib.suppress(Exception):
                                        await on_event({
                                            "type": "user_transcript",
                                            "text": text,
                                            "turn_id": response_turn_id,
                                        })

                                emitted_audio = False
                                emitted_text_from_parts = False
                                for part in model_parts:
                                    inline_data = getattr(part, "inline_data", None)
                                    audio_bytes = getattr(inline_data, "data", None) if inline_data else None
                                    if isinstance(audio_bytes, (bytes, bytearray)) and audio_bytes:
                                        emitted_audio = True
                                        _clear_stall_watch("model_audio", response_turn_id)
                                        with contextlib.suppress(Exception):
                                            await on_audio(bytes(audio_bytes))

                                if model_parts and not (out_t and getattr(out_t, "text", None)):
                                    for part in model_parts:
                                        text = getattr(part, "text", None)
                                        if isinstance(text, str) and text.strip() and not getattr(part, "thought", False):
                                            merged = _update_transcript_buffer(agent_parts, text)
                                            emitted_text_from_parts = True
                                            _clear_stall_watch("model_text", response_turn_id)
                                            with contextlib.suppress(Exception):
                                                await on_event({
                                                    "type": "agent_transcript",
                                                    "text": merged,
                                                    "turn_id": response_turn_id,
                                                })

                                if not model_parts and response.data:
                                    _clear_stall_watch("response_audio", response_turn_id)
                                    with contextlib.suppress(Exception):
                                        await on_audio(response.data)

                                if not model_parts and not (out_t and getattr(out_t, "text", None)):
                                    text = getattr(response, "text", None)
                                    if text and text.strip():
                                        merged = _update_transcript_buffer(agent_parts, text)
                                        emitted_text_from_parts = True
                                        _clear_stall_watch("response_text", response_turn_id)
                                        with contextlib.suppress(Exception):
                                            await on_event({
                                                "type": "agent_transcript",
                                                "text": merged,
                                                "turn_id": response_turn_id,
                                            })

                                if server_content and getattr(server_content, "interrupted", False):
                                    logger.info("Scout edit Live interrupted turn=%s", response_turn_id)
                                    _clear_stall_watch("interrupted", response_turn_id)
                                    with contextlib.suppress(Exception):
                                        await on_event({
                                            "type": "interrupted",
                                            "turn_id": response_turn_id,
                                        })

                                if server_content and getattr(server_content, "generation_complete", False):
                                    logger.info("Scout edit Live generation_complete turn=%s", response_turn_id)
                                    _clear_stall_watch("generation_complete", response_turn_id)
                                    with contextlib.suppress(Exception):
                                        await on_event({
                                            "type": "generation_complete",
                                            "turn_id": response_turn_id,
                                        })

                                tool_call = getattr(response, "tool_call", None)
                                if tool_call:
                                    _clear_stall_watch("tool_call", response_turn_id)
                                    for fc in tool_call.function_calls:
                                        await tool_queue.put(fc)

                                turn_complete = (
                                    getattr(server_content, "turn_complete", False) if server_content else False
                                )
                                if turn_complete:
                                    completed_turn_id = response_turn_id
                                    logger.info(
                                        "Scout edit Live turn_complete turn=%s user_parts=%d agent_parts=%d",
                                        completed_turn_id,
                                        len(user_parts),
                                        len(agent_parts),
                                    )
                                    _clear_stall_watch("turn_complete", completed_turn_id)
                                    with contextlib.suppress(Exception):
                                        await on_event({
                                            "type": "turn_complete",
                                            "turn_id": completed_turn_id,
                                        })
                                    user_parts.clear()
                                    agent_parts.clear()
                                    if pending_turn_ids and pending_turn_ids[0] == completed_turn_id:
                                        pending_turn_ids.popleft()
                                    elif completed_turn_id in pending_turn_ids:
                                        pending_turn_ids.remove(completed_turn_id)
                                    session_turn["response_turn_id"] = None

                    except Exception as exc:
                        message = str(exc)
                        if "Operation is not implemented, or supported, or enabled" in message:
                            raise RuntimeError(
                                "Gemini Live rejected the current voice session configuration. "
                                "Retry once; if it persists, use the text agent while we keep the live session on the minimal supported config."
                            ) from exc
                        raise
                    finally:
                        await tool_queue.join()
                        tool_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await tool_task

                async def _send_frames() -> None:
                    """Forward screen frames from frame_queue to Gemini Live as video blobs."""
                    if frame_queue is None:
                        return
                    try:
                        while True:
                            frame_bytes = await frame_queue.get()
                            if frame_bytes is None:
                                return
                            await session.send_realtime_input(
                                video=types.Blob(data=frame_bytes, mime_type="image/jpeg")
                            )
                    except Exception as exc:
                        logger.warning("Scout edit frame send task aborted: %s", exc)

                client_task = asyncio.create_task(_client_to_gemini())
                gemini_task = asyncio.create_task(_gemini_to_client())
                stall_task = asyncio.create_task(_stall_monitor()) if transport == "gemini_api" else None
                frames_task = asyncio.create_task(_send_frames()) if frame_queue is not None else None

                tasks = {client_task, gemini_task}
                if stall_task is not None:
                    tasks.add(stall_task)

                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                # frames_task is a support task — cancel it alongside any pending tasks
                if frames_task is not None and not frames_task.done():
                    pending = set(pending) | {frames_task}

                for task in pending:
                    task.cancel()
                for task in pending:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

                for task in done:
                    exc = task.exception()
                    if exc is not None:
                        raise exc

                if client_task in done:
                    break
                if gemini_task in done:
                    break
                if stall_task is not None and stall_task in done:
                    raise RuntimeError("Voice session ended unexpectedly during stall monitoring.")

            if _client_closed[0]:
                logger.info("Scout edit voice session ended (client closed): project=%s", project_id)
                return
            logger.warning(
                "Scout edit voice session: Gemini closed unexpectedly, restarting: project=%s",
                project_id,
            )
            with contextlib.suppress(Exception):
                await on_event({"type": "session_recovering"})
            session_restarted = True
            # No return — falls through to outer while True → new Gemini Live session

        except _VoiceSessionRestartRequired as exc:
            logger.warning(
                "Scout edit voice session recovering: project=%s turn=%s transport=%s",
                project_id,
                exc.turn_id,
                transport,
            )
            draft_commands.clear()
            with contextlib.suppress(Exception):
                await on_event({"type": "session_recovering", "turn_id": exc.turn_id})
            session_restarted = True
            continue
