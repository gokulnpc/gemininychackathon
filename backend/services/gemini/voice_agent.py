"""Scout Voice Agent — bidirectional Live API conversational agent.

WebSocket: /api/v1/voice-agent

Scout speaks with the user via Gemini Live API (AUDIO in + AUDIO out), gathers
creative requirements through a friendly back-and-forth, then kicks off the full
Content Factory pipeline in the background.

All EXISTING endpoints (generate-script, generate-video, live-voice) are unchanged.
This is a new, additive flow.

Tools available to Scout during the conversation:
  - start_video_generation  → creates project + runs script agent + video pipeline
  - get_past_videos         → returns recent projects for context
  - suggest_next_content    → analyses a past video and proposes a part 2

Audio protocol (same as gemini_live.py for the user side):
  In:  PCM16, 16 kHz, mono
  Out: PCM16, 24 kHz, mono  (Gemini's default TTS output rate)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MODEL = "gemini-2.0-flash-live-001"

# ── Scout system prompt ────────────────────────────────────────────────────────

_SCOUT_SYSTEM = """You are Scout, Content Factory's AI creative director.
Your job: have a SHORT, friendly voice conversation to understand what video the user wants, then kick off production.

Conversation flow:
1. Greet warmly and introduce yourself in 1 sentence.
2. Ask ONE question at a time — start with topic, then platform (Instagram, TikTok, or YouTube Shorts), then style preference.
3. Once you have topic + platform, briefly confirm back what you heard and ask if they're ready to generate.
4. Call start_video_generation to kick off the pipeline immediately after confirmation.
5. Tell the user their video is being created and will be ready in about 5 minutes.
6. If the user asks about past videos, call get_past_videos first before responding.
7. If asked what to make next or about a specific video, call suggest_next_content.
8. If the user wants to see visual concepts before committing, call generate_visual_preview with a detailed brief and the matching mode (storybook for stories, marketing for brands, social_content for social media posts).
9. After generate_visual_preview completes, briefly describe what Maya created in 1 sentence, then ask if they want to proceed to full video generation.

Rules:
- Keep EVERY response under 2 sentences. Voice responses must be short.
- Never ask more than one question per turn.
- Be warm, direct, and specific — like a trusted creative colleague.
- When the user says goodbye or thanks you, end the conversation gracefully."""

# ── Live API config ────────────────────────────────────────────────────────────

def _build_live_config():
    """Build LiveConnectConfig with Scout's tools and AUDIO output modality."""
    from google.genai import types

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=_SCOUT_SYSTEM,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="start_video_generation",
                description=(
                    "Start generating a video for the user. "
                    "Call this ONLY after the user has confirmed their topic and platform."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "topic": types.Schema(
                            type="string",
                            description="The video topic or idea as described by the user.",
                        ),
                        "platform": types.Schema(
                            type="string",
                            description="Target platform: instagram_reels | tiktok | youtube_shorts",
                        ),
                        "niche": types.Schema(
                            type="string",
                            description="Content niche: horror, finance, fitness, food, tech, travel, motivation, etc.",
                        ),
                        "art_style": types.Schema(
                            type="string",
                            description="Visual style: realism | ghibli | comic | polaroid | disney | painting | creepy_comic",
                        ),
                        "video_duration": types.Schema(
                            type="integer",
                            description="Duration in seconds: 15, 30, or 60",
                        ),
                        "user_email": types.Schema(
                            type="string",
                            description="Optional email address for notification when video is ready.",
                        ),
                    },
                    required=["topic", "platform"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_past_videos",
                description="Get the user's recent video projects — status, hooks, and platforms.",
                parameters=types.Schema(
                    type="object",
                    properties={
                        "limit": types.Schema(
                            type="integer",
                            description="Number of recent projects to retrieve (default 5).",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="suggest_next_content",
                description=(
                    "Analyse a past video project and suggest what to make next "
                    "(e.g. a series part 2 or a different angle on the same topic)."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "project_id": types.Schema(
                            type="string",
                            description="The project_id of the past video to analyse.",
                        ),
                    },
                    required=["project_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="generate_visual_preview",
                description=(
                    "Ask Maya (our Creative Director) to generate a visual concept — "
                    "text + images — for the user's idea. Call this when the user wants to "
                    "see what their content could look like before committing to full video generation."
                ),
                parameters=types.Schema(
                    type="object",
                    properties={
                        "brief": types.Schema(
                            type="string",
                            description="Creative brief: topic, audience, tone, goals.",
                        ),
                        "mode": types.Schema(
                            type="string",
                            description="storybook | marketing | educational | social_content",
                        ),
                        "art_style": types.Schema(
                            type="string",
                            description="Visual style: realism | ghibli | comic | polaroid | disney | painting | creepy_comic",
                        ),
                    },
                    required=["brief", "mode"],
                ),
            ),
        ])],
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=100_000,
            sliding_window=types.SlidingWindow(target_tokens=80_000),
        ),
    )


# ── Tool implementations ───────────────────────────────────────────────────────

async def _tool_get_past_videos(limit: int = 5) -> dict:
    """Fetch recent projects from Firestore for Scout's context."""
    from services.storage import firestore_db

    try:
        projects = await firestore_db.list_projects(limit=limit)
        return {
            "videos": [
                {
                    "project_id": p.get("project_id", ""),
                    "status":     p.get("status", "unknown"),
                    "hook":       p.get("hook", ""),
                    "platforms":  p.get("platforms", []),
                    "created_at": p.get("created_at", ""),
                    "video_urls": p.get("video_urls", {}),
                }
                for p in projects
            ]
        }
    except Exception as exc:
        logger.warning("get_past_videos failed: %s", exc)
        return {"videos": [], "error": str(exc)}


async def _tool_generate_visual_preview(
    brief: str,
    mode: str = "social_content",
    art_style: str | None = None,
    on_event: Callable | None = None,
) -> dict:
    """Invoke Maya (Creative Director) and stream each block to the browser."""
    try:
        from services.gemini import interleaved as gemini_interleaved

        logger.info("Visual preview starting (mode=%s, art_style=%s)", mode, art_style)
        raw_blocks, _ = await gemini_interleaved.generate_creative_package(
            brief=brief,
            mode=mode,
            art_style=art_style,
        )

        if on_event:
            for i, block in enumerate(raw_blocks):
                try:
                    await on_event({
                        "type": "creative_block",
                        "block": block,
                        "block_index": i,
                        "total_blocks": len(raw_blocks),
                    })
                except Exception:
                    pass  # WebSocket may close mid-stream

        n_images = sum(1 for b in raw_blocks if b["type"] == "image")
        n_text = sum(1 for b in raw_blocks if b["type"] == "text")
        logger.info("Visual preview complete — %d blocks (%d images, %d text)", len(raw_blocks), n_images, n_text)
        return {
            "status": "completed",
            "total_blocks": len(raw_blocks),
            "total_images": n_images,
            "total_text_blocks": n_text,
        }

    except Exception as exc:
        logger.warning("generate_visual_preview failed: %s", exc)
        return {"error": str(exc)}


async def _tool_suggest_next_content(project_id: str) -> dict:
    """Analyse a past project and suggest a follow-up video."""
    from services.storage import firestore_db

    try:
        project = await firestore_db.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        hook = project.get("hook", "")
        niche = project.get("niche", "general")
        platform = (project.get("platforms") or ["instagram_reels"])[0]
        return {
            "previous_hook": hook,
            "suggestion": (
                f"Build on '{hook}' — make a part 2 that goes one level deeper "
                f"into the story or reveals the outcome."
            ),
            "recommended_niche": niche,
            "recommended_platform": platform,
            "recommended_art_style": project.get("art_style", "realism"),
        }
    except Exception as exc:
        logger.warning("suggest_next_content failed: %s", exc)
        return {"error": str(exc)}


async def _tool_start_video_generation(
    topic: str,
    platform: str,
    niche: str = "general",
    art_style: str = "realism",
    video_duration: int = 30,
    user_email: str = "",
    on_event: Callable | None = None,
) -> dict:
    """Create a project, run Scout (ADK) for the script, then run the video pipeline.

    Returns immediately with project_id — pipeline continues in background.
    When done: calls on_event({"type":"video_ready",...}) if WebSocket is still open,
    otherwise sends a Sendgrid email if user_email was provided.
    """
    from uuid import uuid4
    from services.storage import firestore_db
    from services.gemini.agent import generate_script_with_agent

    # Validate and normalise platform
    _valid_platforms = {"instagram_reels", "tiktok", "youtube_shorts"}
    if platform not in _valid_platforms:
        platform = "instagram_reels"

    # Clamp duration
    if video_duration not in (15, 30, 60):
        video_duration = 30

    project_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await firestore_db.save_project(project_id, {
        "project_id":  project_id,
        "status":      "queued",
        "created_at":  now,
        "platforms":   [platform],
        "niche":       niche,
        "art_style":   art_style,
        "hook":        "",
        "user_email":  user_email,
        "source":      "voice_agent",
    })

    async def _run_pipeline():
        try:
            logger.info("Voice agent pipeline starting: project=%s topic=%.60s", project_id, topic)
            await firestore_db.save_project(project_id, {"status": "in_progress"})

            # ── Stage 1: Scout ADK agent generates the script ─────────────────
            script = await generate_script_with_agent(
                transcript=topic,
                target_platforms=[platform],
                niche=niche,
                art_style=art_style,
                video_duration=video_duration,
            )

            hook_text = script.get("hook", {}).get("text", "")
            await firestore_db.save_project(project_id, {
                "hook":          hook_text,
                "scenes_count":  len(script.get("scenes", [])),
                "status":        "script_ready",
            })
            logger.info("Voice agent script ready: project=%s hook=%.60s", project_id, hook_text)

            # ── Stage 2: Video pipeline ────────────────────────────────────────
            # Import here to avoid circular deps and keep startup fast
            from uuid import UUID
            from models.schemas import (
                ScriptGenerationResponse, Platform, CaptionStyleEnum, MusicPreset
            )
            from services.pipeline_runner import run_pipeline_stages

            _platform_map = {
                "instagram_reels":  Platform.instagram_reels,
                "tiktok":           Platform.tiktok,
                "youtube_shorts":   Platform.youtube_shorts,
            }

            script_resp = ScriptGenerationResponse(**script)
            script_resp.project_id = UUID(project_id)

            _, video_urls, _, thumbnail_url, _ = await run_pipeline_stages(
                project_id=UUID(project_id),
                transcript=topic,
                series=None,
                series_id=None,
                target_platforms=[_platform_map[platform]],
                style="modern_energetic",
                video_duration=video_duration,
                caption_style_override=CaptionStyleEnum.beast.value,
                brand_voice=None,
                cta_preference=None,
                work_dir=f"/tmp/voice_agent/{project_id}",
                pre_generated_script=script_resp,
            )

            video_url = next(iter(video_urls.values()), "")
            await firestore_db.save_project(project_id, {
                "status":        "completed",
                "video_urls":    video_urls,
                "thumbnail_url": thumbnail_url,
                "completed_at":  datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Voice agent pipeline complete: project=%s url=%s", project_id, video_url)

            # ── Notify ────────────────────────────────────────────────────────
            event = {
                "type":       "video_ready",
                "project_id": project_id,
                "video_url":  video_url,
                "hook":       hook_text,
            }
            if on_event:
                try:
                    await on_event(event)
                except Exception:
                    pass  # WebSocket may be closed — fall through to email

            if user_email and not on_event:
                _send_email_notification(user_email, project_id, hook_text)

        except Exception as exc:
            logger.exception("Voice agent pipeline failed: project=%s error=%s", project_id, exc)
            try:
                await firestore_db.save_project(project_id, {
                    "status": "failed",
                    "error":  str(exc),
                })
            except Exception:
                pass

    asyncio.create_task(_run_pipeline())

    return {
        "status":     "started",
        "project_id": project_id,
        "message":    "Video generation started! Your script is being written now and the full video will be ready in about 5 minutes.",
    }


def _send_email_notification(email: str, project_id: str, hook: str) -> None:
    """Fire-and-forget Sendgrid notification when video is ready."""
    try:
        import sendgrid
        import os
        from sendgrid.helpers.mail import Mail

        api_key = os.environ.get("SENDGRID_API_KEY", "")
        if not api_key:
            return

        message = Mail(
            from_email="scout@contentfactory.ai",
            to_emails=email,
            subject="Your video is ready! 🎬",
            html_content=(
                f"<p>Hey! Your Content Factory video is ready.</p>"
                f"<p><b>Hook:</b> {hook}</p>"
                f"<p>Project ID: {project_id}</p>"
                f"<p>Open the app to preview and publish your video.</p>"
            ),
        )
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        sg.send(message)
        logger.info("Sendgrid notification sent to %s for project %s", email, project_id)
    except Exception as exc:
        logger.warning("Sendgrid notification failed: %s", exc)


# ── Tool dispatcher ────────────────────────────────────────────────────────────

async def _dispatch_tool(name: str, args: dict, on_event: Callable) -> dict:
    """Route a Live API function_call to the correct Python tool."""
    if name == "start_video_generation":
        return await _tool_start_video_generation(on_event=on_event, **args)
    if name == "get_past_videos":
        return await _tool_get_past_videos(**{k: v for k, v in args.items() if k == "limit"})
    if name == "suggest_next_content":
        return await _tool_suggest_next_content(project_id=args.get("project_id", ""))
    if name == "generate_visual_preview":
        return await _tool_generate_visual_preview(on_event=on_event, **args)
    return {"error": f"Unknown tool: {name}"}


# ── Main entry point ───────────────────────────────────────────────────────────

async def run_voice_agent(
    audio_chunks: AsyncIterator[bytes],
    on_event: Callable[[dict], Coroutine],
):
    """Async generator — yields PCM16 audio bytes from Scout (the agent's voice).

    Concurrently:
    - Streams user PCM16 audio IN to Gemini Live
    - Yields Scout PCM16 audio OUT to the WebSocket caller
    - Calls on_event(dict) for JSON metadata events (transcripts, tool events, notifications)

    Args:
        audio_chunks:  Async iterator of raw PCM16 bytes (16 kHz mono) from the browser.
        on_event:      Async callback; called with JSON-serialisable dicts for the browser.
    """
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    live_config = _build_live_config()

    logger.info("Scout voice agent session starting")

    async with client.aio.live.connect(model=MODEL, config=live_config) as session:

        async def _send_audio() -> None:
            async for chunk in audio_chunks:
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

        send_task = asyncio.create_task(_send_audio())

        async for response in session.receive():
            # ── Scout's voice audio → forward to browser as binary WS frames ──
            if response.data:
                yield response.data

            # ── Scout's text transcript → JSON event for UI sidebar ───────────
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
                    logger.info("Scout tool call: %s(%s)", fc.name, list(args.keys()))

                    result = await _dispatch_tool(fc.name, args, on_event)

                    # Notify browser of tool event
                    try:
                        await on_event({"type": "tool_event", "name": fc.name, **result})
                    except Exception:
                        pass

                    # Return result to Scout so it can continue the conversation
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

    logger.info("Scout voice agent session ended")
