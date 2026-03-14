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
                    "kind": types.Schema(type="string", description="set_background_music | set_music_volume | set_voiceover_volume | add_text_overlay | update_selected_text | move_selected_element | replace_selected_media | insert_media_asset | trim_selected_element | delete_selected_element | add_hook_title"),
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
        types.FunctionDeclaration(
            name="generate_creative_direction",
            description=(
                "Generate a rich creative direction package with mixed text and generated images. "
                "Call when the user wants creative ideas, storyboard concepts, visual direction, "
                "hook suggestions, caption themes, or mood recommendations."
            ),
            parameters=types.Schema(
                type="object",
                properties={
                    "brief": types.Schema(type="string", description="Creative brief."),
                    "mode": types.Schema(type="string", description="social_content | marketing | storybook | educational"),
                    "art_style": types.Schema(type="string", description="realism | ghibli | comic | polaroid | disney | painting | creepy_comic"),
                },
                required=["brief"],
            ),
        ),
        types.FunctionDeclaration(
            name="generate_thumbnail_options",
            description=(
                "Generate 2–3 clickbait AI thumbnail image options for this video. "
                "Call when the user wants a new thumbnail or more eye-catching thumbnail ideas. "
                "Streams each option as a thumbnail_option event."
            ),
            parameters=types.Schema(
                type="object",
                properties={
                    "brief": types.Schema(type="string", description="Extra context about the video (optional)."),
                    "art_style": types.Schema(type="string", description="realism | ghibli | comic | polaroid | disney (default: realism)"),
                    "count": types.Schema(type="integer", description="Number of options to generate (1–3, default 2)."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="set_thumbnail",
            description="Apply one of the generated thumbnail options as the project's permanent thumbnail.",
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
            name="generate_lyria_music",
            description=(
                "Generate AI background music using Lyria for this video. "
                "Call this when the user selects the 'lyria' music option or asks for AI-generated music. "
                "Generates ~30s of unique AI music, saves it to the user's audio library, "
                "and returns a preview URL. After this returns, draft set_background_music with preset='lyria' and call apply_live_edits."
            ),
            parameters=types.Schema(type="object", properties={}),
        ),
        types.FunctionDeclaration(
            name="generate_storyboard",
            description="Generate a visual storyboard from a brief using the interleaved AI model. Produces 3–6 scene images that appear in the chat. Images are cached for building the timeline.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "brief": types.Schema(type=types.Type.STRING, description="What the video is about"),
                    "art_style": types.Schema(type=types.Type.STRING, description="Art style: cinematic, realism, ghibli, etc. Default: cinematic"),
                    "num_scenes": types.Schema(type=types.Type.INTEGER, description="Number of scenes to generate (3–6). Default: 4"),
                },
                required=["brief"],
            ),
        ),
        types.FunctionDeclaration(
            name="build_timeline_from_storyboard",
            description="Takes the storyboard images cached by generate_storyboard, uploads them to GCS, and assembles a sequential timeline. Must call generate_storyboard first.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "scene_duration_seconds": types.Schema(type=types.Type.INTEGER, description="Duration per scene in seconds. Default: 4"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="propose_scripts",
            description=(
                "Present 2-3 short script concept cards to the user so they can pick a story direction. "
                "Call this FIRST when the user wants to create a video, story, comic, or manga from scratch. "
                "Each proposal has a title, hook line, and 2-sentence story arc."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "proposals": types.Schema(
                        type=types.Type.ARRAY,
                        description="2-3 script concept options",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "title": types.Schema(type=types.Type.STRING, description="Short catchy concept title"),
                                "hook":  types.Schema(type=types.Type.STRING, description="Opening hook — 1 punchy sentence"),
                                "arc":   types.Schema(type=types.Type.STRING, description="Story arc summary — 2 sentences"),
                            },
                            required=["title", "hook", "arc"],
                        ),
                    ),
                },
                required=["proposals"],
            ),
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
        "generate_lyria_music": "Generating AI music with Lyria...",
        "generate_creative_direction": "Generating creative direction...",
        "generate_thumbnail_options": "Generating thumbnail options...",
        "set_thumbnail": "Applying thumbnail...",
        "generate_image_for_scene": "Generating AI image...",
        "generate_storyboard": "Generating storyboard...",
        "build_timeline_from_storyboard": "Building timeline...",
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

                # generate_lyria_music: generate AI music, save to user assets, yield preview
                if fc.name == "generate_lyria_music":
                    yield {"type": "agent_step", "tool": "generate_lyria_music", "message": "Generating AI music with Lyria..."}
                    yield {"type": "lyria_generating"}
                    lyria_result: dict = {"status": "error", "error": "Lyria not available"}
                    try:
                        import os as _os
                        from datetime import datetime as _dt, timezone as _tz
                        from uuid import uuid4 as _uuid4
                        from config import get_settings as _get_settings
                        from services.media import lyria as _lyria_svc
                        from services.storage import gcs as _gcs
                        from services.storage.assets import resolve_asset_url as _resolve_url

                        _cfg = _get_settings()
                        _wav_path = await _lyria_svc.generate_music(
                            music_preset="lyria",
                            project_id=_cfg.google_cloud_project,
                            location=_cfg.vertex_ai_location,
                        )
                        _asset_id = str(_uuid4())
                        _filename = f"lyria_{_asset_id[:8]}.wav"
                        _gcs_key = f"user_assets/{uid}/music/{_asset_id}/{_filename}"
                        await _gcs.upload_file(_wav_path, _gcs_key, "audio/wav")
                        _os.unlink(_wav_path)

                        _meta = {
                            "id": _asset_id,
                            "uid": uid,
                            "filename": _filename,
                            "content_type": "audio/wav",
                            "uploaded_at": _dt.now(_tz.utc).isoformat(),
                            "gcs_key": _gcs_key,
                        }
                        await _gcs.store_json(_meta, f"user_assets/{uid}/music/{_asset_id}/meta.json")

                        _preview_url = await _resolve_url(uid, "music", _asset_id)
                        lyria_result = {"status": "generated", "asset_id": _asset_id, "preview_url": _preview_url or ""}
                        if _preview_url:
                            yield {"type": "lyria_ready", "url": _preview_url, "asset_id": _asset_id}
                    except Exception as _lyria_exc:
                        logger.warning("generate_lyria_music failed: %s", _lyria_exc)
                        lyria_result = {"status": "error", "error": str(_lyria_exc)}
                    function_response_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": lyria_result},
                        )
                    ))
                    continue

                # generate_storyboard: generate interleaved storyboard images, cache in project_data
                if fc.name == "generate_storyboard":
                    yield {"type": "agent_step", "tool": "generate_storyboard", "message": "Generating storyboard..."}
                    storyboard_result: dict = {"status": "error", "error": "Storyboard generation failed"}
                    try:
                        from services.gemini.interleaved import generate_creative_package as _gen_sb

                        brief_sb = fc.args.get("brief", "") if fc.args else ""
                        art_style_sb = fc.args.get("art_style", "cinematic") if fc.args else "cinematic"
                        num_scenes_sb = min(max(int((fc.args or {}).get("num_scenes", 4)), 3), 6)

                        prompt_sb = (
                            f"Create a {num_scenes_sb}-panel manga story for: {brief_sb}. "
                            f"Art style: {art_style_sb}."
                        )
                        blocks_sb, _ = await _gen_sb(prompt_sb, mode="manga", art_style=art_style_sb)

                        drafts_sb: list[dict] = []
                        pending_caption_sb = ""
                        for block_sb in blocks_sb:
                            if block_sb.get("type") == "text":
                                pending_caption_sb = block_sb["content"]
                            elif block_sb.get("type") == "image":
                                panel_block_sb = {
                                    "type": "panel",
                                    "content": block_sb["content"],
                                    "mime_type": block_sb.get("mime_type", "image/jpeg"),
                                    "caption": pending_caption_sb,
                                }
                                yield {"type": "creative_block", "block": panel_block_sb}
                                drafts_sb.append({
                                    "image_b64": block_sb["content"],
                                    "mime_type": block_sb.get("mime_type", "image/jpeg"),
                                    "description": pending_caption_sb or f"Scene {len(drafts_sb) + 1}",
                                })
                                pending_caption_sb = ""

                        project_data["_storyboard_drafts"] = drafts_sb
                        storyboard_result = {
                            "status": "ok",
                            "count": len(drafts_sb),
                            "descriptions": [d_sb["description"] for d_sb in drafts_sb],
                        }
                    except Exception as _sb_exc:
                        logger.warning("generate_storyboard failed: %s", _sb_exc)
                        storyboard_result = {"status": "error", "error": str(_sb_exc)}
                    function_response_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": storyboard_result},
                        )
                    ))
                    continue

                # build_timeline_from_storyboard: upload cached storyboard images to GCS, assemble timeline
                if fc.name == "build_timeline_from_storyboard":
                    yield {"type": "agent_step", "tool": "build_timeline_from_storyboard", "message": "Building timeline..."}
                    timeline_result: dict = {"status": "error", "error": "Timeline build failed"}
                    try:
                        import base64 as _b64_tl
                        import os as _os_tl
                        from uuid import uuid4 as _uuid4_tl
                        from services.storage import gcs as _gcs_tl

                        drafts_tl = project_data.get("_storyboard_drafts", [])
                        if not drafts_tl:
                            timeline_result = {"status": "error", "message": "No storyboard found. Call generate_storyboard first."}
                        else:
                            duration_tl = int((fc.args or {}).get("scene_duration_seconds", 4))
                            commands_tl: list[dict] = []

                            for i_tl, draft_tl in enumerate(drafts_tl):
                                img_bytes_tl = _b64_tl.b64decode(draft_tl["image_b64"])
                                mime_tl = draft_tl.get("mime_type", "image/png")
                                suffix_tl = ".jpg" if "jpeg" in mime_tl else ".png"
                                tmp_path_tl = f"/tmp/storyboard_{_uuid4_tl().hex}{suffix_tl}"
                                with open(tmp_path_tl, "wb") as _f_tl:
                                    _f_tl.write(img_bytes_tl)
                                gcs_key_tl = f"projects/{project_id}/storyboard/{_uuid4_tl().hex}{suffix_tl}"
                                src_url_tl = await _gcs_tl.upload_file(tmp_path_tl, gcs_key_tl, mime_tl)
                                try:
                                    _os_tl.unlink(tmp_path_tl)
                                except Exception:
                                    pass

                                commands_tl.append({
                                    "kind": "insert_media_asset",
                                    "args": {
                                        "src": src_url_tl,
                                        "start_seconds": i_tl * duration_tl,
                                        "duration_seconds": duration_tl,
                                        "media_kind": "image",
                                        "name": f"Scene {i_tl + 1}",
                                    },
                                })

                            source_json_tl = current_project_json or {}
                            patched_tl, applied_tl, errors_tl = await _project_commands(
                                source_json_tl, commands_tl, editor_context, uid=uid
                            )
                            if errors_tl:
                                timeline_result = {"status": "error", "message": f"Some commands rejected: {'; '.join(errors_tl)}"}
                            elif not applied_tl:
                                timeline_result = {"status": "error", "message": "No commands were applied."}
                            else:
                                await _apply_live_edits(
                                    project_id=project_id,
                                    project_data=project_data,
                                    patched_project_json=patched_tl,
                                    applied_changes=applied_tl,
                                    editor_context=editor_context,
                                )
                                timeline_result = {
                                    "status": "ok",
                                    "scenes_added": len(commands_tl),
                                    "total_duration_seconds": len(commands_tl) * duration_tl,
                                }
                    except Exception as _tl_exc:
                        logger.warning("build_timeline_from_storyboard failed: %s", _tl_exc)
                        timeline_result = {"status": "error", "error": str(_tl_exc)}
                    function_response_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": timeline_result},
                        )
                    ))
                    continue

                # propose_scripts: emit story concept cards to the user
                if fc.name == "propose_scripts":
                    proposals_ps = (fc.args or {}).get("proposals", [])
                    yield {"type": "script_proposals", "proposals": proposals_ps}
                    function_response_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": {"status": "ok", "count": len(proposals_ps)}},
                        )
                    ))
                    continue

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
