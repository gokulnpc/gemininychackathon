"""Gemini generate_content text runtime for Scout's edit workflow."""

from __future__ import annotations

import logging

from .commands import (
    _build_proposal_from_commands,
)
from .constants import _EDIT_SYSTEM, _TEXT_MODEL
from .context import _summarize_editor_context
from .env import settings_env
from .projector import _apply_live_edits, _project_commands

logger = logging.getLogger(__name__)

_TOOL_DECLARATIONS = None


def _get_tool_declarations():
    """Lazily build FunctionDeclaration list (avoids import cost at module load)."""
    global _TOOL_DECLARATIONS
    if _TOOL_DECLARATIONS is not None:
        return _TOOL_DECLARATIONS
    from google.genai import types

    _TOOL_DECLARATIONS = [
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
            description="Apply all queued edits to the live timeline and save them. Call ONCE after drafting all commands.",
            parameters=types.Schema(type="object", properties={}),
        ),
    ]
    return _TOOL_DECLARATIONS


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

    from google.genai import types
    from services.gemini.client import get_client
    from .voice_runtime import _dispatch_voice_tool

    settings_env()

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
        "Do NOT try to render or export - the user will export when ready."
    )

    labels: dict[str, str] = {
        "get_project_info": "Checking your current video settings...",
        "get_editor_context": "Checking your current editor selection...",
        "get_user_assets": "Looking up your media assets...",
        "draft_edit_command": "Drafting edit command...",
        "apply_live_edits": "Building proposal...",
        "generate_style_preview": "Generating style preview...",
    }

    client = get_client()
    draft_commands: list[dict] = []
    events_buffer: list[dict] = []
    proposal_yielded = False
    proposal: dict = {}
    agent_last_text: str = ""

    async def _on_event(event: dict) -> None:
        events_buffer.append(event)

    # Build initial message
    initial_parts: list[types.Part] = [types.Part(text=instruction)]
    screenshot = (editor_context or {}).get("screenshot") or {}
    image_b64 = screenshot.get("image_b64")
    if image_b64:
        import base64
        image_bytes = base64.b64decode(image_b64)
        mime = screenshot.get("mime_type", "image/png")
        initial_parts.append(types.Part(inline_data=types.Blob(data=image_bytes, mime_type=mime)))

    contents: list[types.Content] = [
        types.Content(role="user", parts=initial_parts)
    ]

    gen_config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=_get_tool_declarations())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    logger.info("Text edit agent starting: project=%s instruction=%.60s", project_id, instruction)

    try:
        for _turn in range(12):
            response = await client.aio.models.generate_content(
                model=_TEXT_MODEL,
                contents=contents,
                config=gen_config,
            )

            candidate = response.candidates[0]
            contents.append(candidate.content)

            # Capture any text the agent produced (clarifying questions, capabilities, etc.)
            text_parts = [
                p.text for p in (candidate.content.parts or [])
                if getattr(p, "text", None)
            ]
            if text_parts:
                agent_last_text = " ".join(text_parts).strip()

            function_calls = [
                p.function_call
                for p in (candidate.content.parts or [])
                if getattr(p, "function_call", None)
            ]

            if not function_calls:
                break  # Agent finished without tool calls (may have responded with text)

            function_response_parts: list[types.Part] = []

            for fc in function_calls:
                args = dict(fc.args) if fc.args else {}
                logger.info("Scout edit tool call: %s(%s)", fc.name, list(args.keys()))

                # Intercept apply_live_edits: build proposal without auto-applying
                if fc.name == "apply_live_edits":
                    if draft_commands:
                        proposal = _build_proposal_from_commands(draft_commands)
                        yield {"type": "proposal", "proposal": proposal}
                        proposal_yielded = True
                    function_response_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": {"status": "proposal_sent"}},
                        )
                    ))
                    continue

                if fc.name in labels:
                    yield {"type": "agent_step", "tool": fc.name, "message": labels[fc.name]}

                # Flush buffered events from async tools (e.g. generate_style_preview)
                while events_buffer:
                    yield events_buffer.pop(0)

                result = await _dispatch_voice_tool(
                    fc.name,
                    args,
                    project_id,
                    project_data,
                    draft_commands,
                    current_project_json,
                    editor_context,
                    _on_event,
                    uid=uid,
                )

                # Flush events emitted during dispatch
                while events_buffer:
                    yield events_buffer.pop(0)

                function_response_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": result},
                    )
                ))

            contents.append(types.Content(role="user", parts=function_response_parts))

            if proposal_yielded:
                break

        # Flush any remaining buffered events
        while events_buffer:
            yield events_buffer.pop(0)

        # Fallback: if agent never called apply_live_edits, build proposal from accumulated draft_commands
        if not proposal_yielded:
            if not draft_commands:
                # Agent gave a clarifying question or capabilities list — show the text, not an error
                msg = agent_last_text or "Agent did not queue any changes - try rephrasing your request."
                yield {"type": "complete", "message": msg, "project_json": None, "changes": {}}
                return
            proposal = _build_proposal_from_commands(draft_commands)
            yield {"type": "proposal", "proposal": proposal}

        logger.info("Text edit agent built proposal: project=%s commands=%d", project_id, len(proposal.get("commands", [])))
        yield {"type": "complete", "message": proposal.get("summary", ""), "project_json": None, "changes": {}}

    except Exception as exc:
        logger.exception("Text edit agent failed: project=%s", project_id)
        yield {"type": "error", "message": str(exc)}
