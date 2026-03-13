"""Gemini Live voice runtime for Scout's edit workflow."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Coroutine

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
                        "kind": types.Schema(type="string", description="set_caption_style | set_background_music | set_music_volume | set_voiceover_volume | add_text_overlay | update_selected_text | move_selected_element | replace_selected_media | insert_media_asset | trim_selected_element | delete_selected_element | add_hook_title"),
                        "args": types.Schema(type="string", description='JSON-encoded command arguments, e.g. {"preset": "breathing_shadows"} or {"volume": 0.3}'),
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
        ])],
    )


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
        return {
            "hook":             project_data.get("hook", ""),
            "caption_style":    project_data.get("caption_style", "beast"),
            "background_music": project_data.get("background_music", "none"),
            "music_volume":     project_data.get("music_volume", 0.15),
            "platforms":        project_data.get("platforms", ["instagram_reels"]),
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

    return {"error": f"Unknown tool: {name}"}


async def run_edit_voice_agent(
    project_id: str,
    project_data: dict,
    audio_chunks: AsyncIterator[bytes],
    get_live_state: Callable[[], dict] | None,
    on_event: Callable[[dict], Coroutine],
    decision_queue: asyncio.Queue | None = None,
    uid: str = "",
):
    """Yield PCM16 audio for the edit session while streaming JSON tool/transcript events."""
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    live_config = _build_voice_config(project_data)
    draft_commands: list[dict] = []

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

        user_transcript_parts: list[str] = []
        agent_transcript_parts: list[str] = []

        try:
            async for response in session.receive():
                if response.data:
                    yield response.data

                server_content = getattr(response, "server_content", None)
                output_transcription = getattr(server_content, "output_transcription", None) if server_content else None
                if output_transcription and getattr(output_transcription, "text", None):
                    try:
                        agent_transcript_parts.append(output_transcription.text.strip())
                        await on_event({"type": "agent_transcript", "text": " ".join(agent_transcript_parts)})
                    except Exception:
                        pass
                else:
                    text = getattr(response, "text", None)
                    if text and text.strip():
                        try:
                            agent_transcript_parts.append(text.strip())
                            await on_event({"type": "agent_transcript", "text": " ".join(agent_transcript_parts)})
                        except Exception:
                            pass

                input_transcription = getattr(server_content, "input_transcription", None) if server_content else None
                if input_transcription and getattr(input_transcription, "text", None):
                    try:
                        user_transcript_parts.append(input_transcription.text.strip())
                        await on_event({"type": "user_transcript", "text": " ".join(user_transcript_parts)})
                    except Exception:
                        pass

                if server_content and getattr(server_content, "interrupted", False):
                    try:
                        await on_event({"type": "interrupted"})
                    except Exception:
                        pass

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
                            draft_commands,
                            live_state.get("project_json"),
                            live_state.get("editor_context"),
                            on_event,
                            decision_queue=decision_queue,
                            get_live_state=get_live_state,
                            uid=uid,
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

                turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
                if turn_complete:
                    user_transcript_parts = []
                    agent_transcript_parts = []
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

