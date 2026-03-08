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
import logging
import os
from collections.abc import AsyncIterator, Callable, Coroutine
from uuid import UUID, uuid4

try:
    from google.adk.tools import ToolContext  # needed at module level for nested tool function type annotations
except ImportError:
    ToolContext = object  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

_LIVE_MODEL = "gemini-2.0-flash-live-001"
_TEXT_MODEL = "gemini-2.5-flash"  # faster than 2.5-pro for simple edit reasoning

# ── Scout edit system prompt ────────────────────────────────────────────────────

_EDIT_SYSTEM = """You are Scout, Content Factory's AI video editor.
You are editing an EXISTING completed video. The project info is already loaded — use get_project_info to see the current settings.

Your job:
1. Greet the user warmly, mention the current video's hook in 1 sentence.
2. Ask what they want to change — ONE question only.
3. If they want to SEE visual options (style, mood, look) → call generate_style_preview first.
4. Once you know what to change → call queue_edit with the new caption_style and/or background_music.
5. Confirm the changes in 1 sentence, then call apply_recompose.
6. Tell the user their updated video is ready.

Rules:
- Keep every response under 2 sentences.
- Never ask more than one question per turn.
- generate_style_preview is for SHOWING options only — never for applying changes.
- Only call apply_recompose ONCE per turn, after ALL edits are queued.
- Valid caption styles: bold_stroke, red_highlight, sleek, karaoke, majestic, beast, elegant, clarity
- Valid music presets: happy_rhythm, quiet_before_storm, peaceful_vibes, brilliant_symphony, breathing_shadows, lyria, none"""

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
    from services.gemini_client import get_client

    client = get_client(force_api_key=True)
    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
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


async def _apply_recompose(
    project_id: str,
    project_data: dict,
    pending_edits: dict,
) -> dict:
    """Run the recompose pipeline with queued edits. Single-platform for speed."""
    from models.schemas import CaptionStyleEnum, MusicPreset, Platform
    from services.recompose import recompose_video

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
        system_instruction=system,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="get_project_info",
                description="Get the current video's settings — hook, caption style, music.",
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
                description="Queue caption style and/or music changes. Does NOT apply yet.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "caption_style": types.Schema(type="string", description="bold_stroke | red_highlight | sleek | karaoke | majestic | beast | elegant | clarity"),
                        "background_music": types.Schema(type="string", description="happy_rhythm | quiet_before_storm | peaceful_vibes | brilliant_symphony | breathing_shadows | lyria | none"),
                        "music_volume": types.Schema(type="number", description="0.0–1.0, default 0.15"),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="apply_recompose",
                description="Apply all queued edits. Call ONCE after confirming with the user.",
                parameters=types.Schema(type="object", properties={}),
            ),
        ])],
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=100_000,
            sliding_window=types.SlidingWindow(target_tokens=80_000),
        ),
    )


async def _dispatch_voice_tool(
    name: str,
    args: dict,
    project_id: str,
    project_data: dict,
    pending_edits: dict,
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

    if name == "generate_style_preview":
        return await _generate_quick_preview(
            brief=args.get("brief", "video concept"),
            art_style=args.get("art_style"),
            on_event=on_event,
        )

    if name == "queue_edit":
        if "caption_style" in args and args["caption_style"] in _VALID_CAPTION_STYLES:
            pending_edits["caption_style"] = args["caption_style"]
        if "background_music" in args and args["background_music"] in _VALID_MUSIC_PRESETS:
            pending_edits["background_music"] = args["background_music"]
        if "music_volume" in args:
            pending_edits["music_volume"] = max(0.0, min(1.0, float(args["music_volume"])))
        return {"queued": dict(pending_edits)}

    if name == "apply_recompose":
        if not pending_edits:
            return {"error": "No edits queued. Call queue_edit first."}
        result = await _apply_recompose(project_id, project_data, pending_edits)
        try:
            await on_event({"type": "edit_complete", **result})
        except Exception:
            pass
        return result

    return {"error": f"Unknown tool: {name}"}


async def run_edit_voice_agent(
    project_id: str,
    project_data: dict,
    audio_chunks: AsyncIterator[bytes],
    on_event: Callable[[dict], Coroutine],
):
    """Async generator — yields PCM16 audio (Scout's voice) for the edit session.

    Accepts audio from the browser, streams Scout's voice back, sends JSON events
    for transcripts, tool calls, creative blocks, and edit_complete notifications.
    """
    from google.genai import types
    from services.gemini_client import get_client

    client = get_client(force_api_key=True)
    live_config = _build_voice_config(project_data)

    # Mutable state shared across tool calls within this session
    pending_edits: dict = {}

    logger.info("Scout edit voice session starting: project=%s", project_id)

    async with client.aio.live.connect(model=_LIVE_MODEL, config=live_config) as session:

        async def _send_audio() -> None:
            async for chunk in audio_chunks:
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

        send_task = asyncio.create_task(_send_audio())

        async for response in session.receive():
            # ── Scout's voice → forward to browser ───────────────────────────
            if response.data:
                yield response.data

            # ── Text transcript → sidebar event ──────────────────────────────
            text = getattr(response, "text", None)
            if text and text.strip():
                try:
                    await on_event({"type": "agent_transcript", "text": text.strip()})
                except Exception:
                    pass

            # ── Tool calls ────────────────────────────────────────────────────
            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                for fc in tool_call.function_calls:
                    args = dict(fc.args) if fc.args else {}
                    logger.info("Scout edit tool call: %s(%s)", fc.name, list(args.keys()))

                    result = await _dispatch_voice_tool(
                        fc.name, args, project_id, project_data, pending_edits, on_event
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

            # ── End of session ────────────────────────────────────────────────
            server_content = getattr(response, "server_content", None)
            turn_complete = getattr(server_content, "turn_complete", False) if server_content else False
            if send_task.done() and turn_complete:
                break

        await send_task

    logger.info("Scout edit voice session ended: project=%s", project_id)


# ── Text / SSE mode (ADK) ───────────────────────────────────────────────────────

async def run_edit_text_agent(
    project_id: str,
    project_data: dict,
    instruction: str,
):
    """Async generator — yields SSE-ready dicts for the text-based quick-action editor.

    Uses ADK (Agent + Runner) with gemini-2.5-flash for fast reasoning.
    Yields agent_step progress events then a complete or error event.
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

    def queue_edit(
        caption_style: str | None = None,
        background_music: str | None = None,
        music_volume: float | None = None,
        tool_context: ToolContext = None,
    ) -> dict:
        """Queue caption style and/or background music change. Does NOT apply yet."""
        edits: dict = {}
        if caption_style and caption_style in _VALID_CAPTION_STYLES:
            edits["caption_style"] = caption_style
        elif caption_style:
            return {"error": f"Unknown caption style '{caption_style}'. Valid: {', '.join(sorted(_VALID_CAPTION_STYLES))}"}
        if background_music and background_music in _VALID_MUSIC_PRESETS:
            edits["background_music"] = background_music
        elif background_music:
            return {"error": f"Unknown music preset '{background_music}'. Valid: {', '.join(sorted(_VALID_MUSIC_PRESETS))}"}
        if music_volume is not None:
            edits["music_volume"] = max(0.0, min(1.0, float(music_volume)))
        if tool_context:
            tool_context.state["pending_edits"] = {
                **tool_context.state.get("pending_edits", {}),
                **edits,
            }
        return {"queued": edits}

    async def apply_recompose(tool_context: ToolContext) -> dict:  # noqa: F841
        """Apply all queued edits via the recompose pipeline."""
        pending = tool_context.state.get("pending_edits", {})
        if not pending:
            return {"error": "No edits queued. Call queue_edit first."}
        data = tool_context.state.get("project_data", {})
        pid = tool_context.state.get("project_id", "")
        result = await _apply_recompose(pid, data, pending)
        tool_context.state["result"] = result
        return result

    # ── ADK agent ────────────────────────────────────────────────────────────────

    hook = project_data.get("hook", "your video")
    caption_style = project_data.get("caption_style", "beast")
    background_music = project_data.get("background_music", "none")

    system = (
        f"{_EDIT_SYSTEM}\n\n"
        f"Current project state:\n"
        f"  Hook: \"{hook}\"\n"
        f"  Caption style: {caption_style}\n"
        f"  Background music: {background_music}\n\n"
        "Workflow: call get_project_info → queue_edit → apply_recompose."
    )

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id,
        state={"project_id": project_id, "project_data": project_data, "pending_edits": {}},
    )

    agent = Agent(
        name="video_edit_agent",
        model=_TEXT_MODEL,
        instruction=system,
        tools=[get_project_info, queue_edit, apply_recompose],
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=instruction)],
    )

    _LABELS: dict[str, str] = {
        "get_project_info": "Checking your current video settings…",
        "queue_edit":        "Selecting edit options…",
        "apply_recompose":   "Applying your changes (~30 seconds)…",
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
        result = (session.state or {}).get("result")
        if result:
            logger.info("ADK edit agent completed: project=%s changes=%s", project_id, result.get("changes"))
            yield {"type": "complete", **result}
        else:
            yield {"type": "error", "message": "Agent did not apply any changes — try rephrasing your request."}

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
