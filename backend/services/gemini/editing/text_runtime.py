"""ADK text runtime for Scout's edit workflow."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover - import fallback for test envs
    ToolContext = object  # type: ignore[misc,assignment]

from .commands import (
    _build_proposal_from_commands,
    _build_proposal_from_pending_edits,
    _queue_pending_edits,
)
from .constants import _EDIT_SYSTEM, _TEXT_MODEL
from .context import _summarize_editor_context
from .env import settings_env
from .projector import _apply_live_edits, _project_commands

logger = logging.getLogger(__name__)


async def run_edit_text_agent(
    project_id: str,
    project_data: dict,
    instruction: str,
    current_project_json: dict | None = None,
    editor_context: dict | None = None,
    mode: str = "plan",
    commands: list[dict] | None = None,
    uid: str = "",
):
    """Yield SSE-ready dicts for the text-based quick-action editor."""
    if mode == "apply" and commands:
        yield {"type": "agent_step", "tool": "project_commands", "message": "Applying confirmed edits to timeline..."}
        source_json = current_project_json or {}
        try:
            patched, applied, errors = await _project_commands(source_json, commands, editor_context, uid=uid)
        except Exception as exc:
            yield {"type": "error", "message": f"Command projection failed: {exc}"}
            return
        if errors:
            yield {"type": "error", "message": f"Some commands were rejected: {'; '.join(errors)}"}
            return
        if not applied:
            yield {"type": "error", "message": "No commands were applied - check that your selection is correct."}
            return
        try:
            result = await _apply_live_edits(
                project_id=project_id,
                project_data=project_data,
                patched_project_json=patched,
                applied_changes=applied,
                editor_context=editor_context,
            )
        except Exception as exc:
            logger.warning("Failed to save applied commands: %s", exc)
            result = {
                "message": "Failed to save changes.",
                "changes": applied,
                "project_json": patched,
                "editor_context": _summarize_editor_context(editor_context),
                "requires_export": True,
            }
        proposal_id = next(
            (str(command.get("proposal_id")) for command in commands if "proposal_id" in command),
            "",
        )
        yield {"type": "applied", "proposal_id": proposal_id, **result}
        yield {"type": "complete", **result}
        return

    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    settings_env()

    app_name = "edit-agent"
    user_id = "user"
    session_id = str(uuid4())

    creative_blocks_buffer: list[dict] = []

    def generate_style_preview(
        brief: str,
        art_style: str | None = None,
        tool_context: ToolContext = None,
    ) -> dict:
        """Generate 3 preview images showing style/concept options.
        Emits creative_preview_option events for each option — one per style variation.
        art_style (optional override): realism|ghibli|comic|polaroid|disney|painting|creepy_comic
        """
        import queue as _std_queue
        from .preview import _generate_multi_preview

        sync_q: _std_queue.Queue = _std_queue.Queue()

        async def _run() -> dict:
            async def _put(event: dict) -> None:
                sync_q.put(event)

            return await _generate_multi_preview(brief=brief, art_style=art_style, on_event=_put)

        result = asyncio.run(_run())
        while not sync_q.empty():
            creative_blocks_buffer.append(sync_q.get_nowait())
        return result

    def get_project_info(tool_context: ToolContext) -> dict:  # noqa: F841
        """Get current caption style, music, and hook for this video."""
        data = tool_context.state.get("project_data", {})
        return {
            "hook": data.get("hook", ""),
            "caption_style": data.get("caption_style", "beast"),
            "background_music": data.get("background_music", "none"),
            "music_volume": data.get("music_volume", 0.15),
            "platforms": data.get("platforms", ["instagram_reels"]),
        }

    def get_editor_context(tool_context: ToolContext) -> dict:  # noqa: F841
        """Return current editor selection/playhead state for context-aware edits."""
        pj = tool_context.state.get("current_project_json")
        context = _summarize_editor_context(tool_context.state.get("editor_context"), project_json=pj)
        if context["has_screenshot"]:
            context["screenshot_note"] = (
                "Screenshot metadata is attached for future multimodal tooling; "
                "this text edit flow currently uses the structured editor state only."
            )
        return context

    def draft_edit_command(
        kind: str,
        args: dict | None = None,
        element_id: str | None = None,
        track_id: str | None = None,
        tool_context: ToolContext = None,
    ) -> dict:
        """Draft a normalized timeline command."""
        drafted = tool_context.state.get("draft_commands", []) if tool_context else []
        command = {"kind": kind, "args": args or {}}
        if element_id:
            command["element_id"] = element_id
        if track_id:
            command["track_id"] = track_id
        drafted.append(command)
        if tool_context:
            tool_context.state["draft_commands"] = drafted
        return {"drafted": command, "note": "Command drafted successfully."}

    def queue_edit(
        caption_style: str | None = None,
        background_music: str | None = None,
        music_volume: float | None = None,
        hook_title: str | None = None,
        hook_duration_seconds: float | None = None,
        move_selected_text_y_delta: float | None = None,
        replace_selected_media_url: str | None = None,
        add_text_overlay: dict | None = None,
        update_selected_text: str | None = None,
        trim_selected_element: dict | None = None,
        delete_selected_element: bool | None = None,
        insert_media_asset: dict | None = None,
        tool_context: ToolContext = None,
    ) -> dict:
        """Legacy compatibility fallback for updating the video project."""
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
                "add_text_overlay": add_text_overlay,
                "update_selected_text": update_selected_text,
                "trim_selected_element": trim_selected_element,
                "delete_selected_element": delete_selected_element,
                "insert_media_asset": insert_media_asset,
            },
            editor_context=tool_context.state.get("editor_context") if tool_context else None,
        )
        if tool_context:
            tool_context.state["pending_edits"] = pending_edits
        if "error" in result:
            return result
        return {
            "queued": result.get("queued", {}),
            "note": "Changes will be applied to the editor instantly. Export to render a new video.",
        }

    def get_user_assets(
        category: str = "images",
        tool_context: ToolContext = None,
    ) -> dict:
        """List the user's uploaded assets for a given category."""
        state = tool_context.state if tool_context else {}
        assets = state.get(f"assets_{category}", [])
        return {"category": category, "assets": assets[:20]}

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
        "Workflow: call get_project_info to see current state; call get_editor_context when selection matters; "
        "call get_user_assets when inserting or replacing media; then call draft_edit_command with the exact changes.\n"
        "(Note: queue_edit is a legacy fallback, prefer draft_edit_command.)\n"
        "Do NOT try to render or export - the user will export when ready."
    )

    initial_state: dict = {
        "project_id": project_id,
        "project_data": project_data,
        "draft_commands": [],
        "pending_edits": {},
        "current_project_json": current_project_json or {},
        "editor_context": editor_context or {},
        "uid": uid,
    }
    if uid:
        try:
            from services.storage.assets import list_user_assets

            tasks = [list_user_assets(uid, category) for category in ("images", "videos", "music", "voice_memos")]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for index, category in enumerate(("images", "videos", "music", "voice_memos")):
                result = results[index]
                if not isinstance(result, Exception):
                    initial_state[f"assets_{category}"] = result
        except Exception:
            pass

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=initial_state,
    )

    agent = Agent(
        name="video_edit_agent",
        model=_TEXT_MODEL,
        instruction=system,
        tools=[get_project_info, get_editor_context, get_user_assets, draft_edit_command, queue_edit, generate_style_preview],
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    instruction_parts: list[genai_types.Part] = [genai_types.Part(text=instruction)]
    screenshot = (editor_context or {}).get("screenshot") or {}
    image_b64 = screenshot.get("image_b64")
    if image_b64:
        import base64
        image_bytes = base64.b64decode(image_b64)
        mime = screenshot.get("mime_type", "image/png")
        instruction_parts.append(genai_types.Part(inline_data=genai_types.Blob(data=image_bytes, mime_type=mime)))
    new_message = genai_types.Content(role="user", parts=instruction_parts)

    labels: dict[str, str] = {
        "get_project_info": "Checking your current video settings...",
        "get_editor_context": "Checking your current editor selection...",
        "get_user_assets": "Looking up your media assets...",
        "draft_edit_command": "Drafting edit command...",
        "queue_edit": "Queuing timeline edit...",
        "generate_style_preview": "Generating style preview...",
    }

    logger.info("ADK edit agent starting: project=%s instruction=%.60s", project_id, instruction)

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            # Flush creative blocks from generate_style_preview
            while creative_blocks_buffer:
                buffered = creative_blocks_buffer.pop(0)
                yield buffered

            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                function_call = getattr(part, "function_call", None)
                if function_call and function_call.name in labels:
                    yield {"type": "agent_step", "tool": function_call.name, "message": labels[function_call.name]}

        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        drafted = (session.state or {}).get("draft_commands", [])
        pending = (session.state or {}).get("pending_edits", {})

        if pending:
            proposal = _build_proposal_from_pending_edits(pending, editor_context)
            drafted.extend(proposal.get("commands", []))

        if not drafted:
            yield {"type": "error", "message": "Agent did not queue any changes - try rephrasing your request."}
            return

        proposal = _build_proposal_from_commands(drafted)
        logger.info("ADK edit agent built proposal: project=%s commands=%d", project_id, len(proposal["commands"]))
        yield {"type": "proposal", "proposal": proposal}
        yield {"type": "complete", "message": proposal["summary"], "project_json": None, "changes": {}}
    except Exception as exc:
        logger.exception("ADK edit agent failed: project=%s", project_id)
        yield {"type": "error", "message": str(exc)}
