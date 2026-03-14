"""Generate-script router — unified endpoint for all three input flows.

POST /api/v1/projects/{project_id}/generate-script

Flow is determined by the `source` field:

  source="voice"   (Flow 1) — User records a voice memo.
                              Gemini multimodal transcribes the audio and detects
                              the speaker's emotional tone. Tone feeds into the
                              agent as a style signal.

  source="text"    (Flow 2) — User types their idea directly.
                              Text goes straight to the Gemini script agent.

  source="preset"  (Flow 3) — User selects a content preset (Horror stories,
                              history, true crime, etc.) and optionally adds a
                              topic angle. Reddit trending posts for the niche
                              are fetched and injected into the agent as live
                              context. User fills all video settings manually.

All three flows converge at the same Gemini 2.5 Pro agentic script loop
(search_trending_hooks → analyze_brand_voice → optimize → validate → finalize).

The returned ScriptGenerationResponse is shown to the user for review.
They can regenerate as many times as needed, then call /generate-video.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from datetime import datetime, timezone
from uuid import UUID

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from deps.auth import get_current_user

from models.schemas import (
    ArtStyle,
    GenerateScriptRequest,
    MusicPreset,
    PresetKey,
    QueueScriptRequest,
    ScriptGenerationResponse,
    ScriptSource,
    SeriesConfig,
    VideoFormat,
    VideoDurationRange,
)
from routers.projects.catalog import DURATION_MAP
from services.storage import firestore_db, gcs
from services.integrations import reddit
from services.infra import task_queue
from services.gemini.agent import generate_script_with_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["script"])


# ── Preset definitions ─────────────────────────────────────────────────────────
# Moved here from preset_process.py — only used for the generate-script preset flow.

_PRESETS: dict[PresetKey, dict] = {
    PresetKey.scary_stories: {
        "name": "Horror stories",
        "niche": "horror",
        "topic": (
            "Create a chilling scary story with atmospheric dread and suspense. "
            "Focus on psychological horror, the unknown, or supernatural elements "
            "that leave the viewer unsettled. Build tension slowly and deliver a "
            "shocking or haunting conclusion."
        ),
    },
    PresetKey.history: {
        "name": "History",
        "niche": "history",
        "topic": (
            "Share a fascinating, lesser-known historical event or story that most "
            "people don't know about. Choose something dramatic, surprising, or that "
            "changed the course of history. Span ancient to modern times."
        ),
    },
    PresetKey.true_crime: {
        "name": "True Crime",
        "niche": "true_crime",
        "topic": (
            "Tell a gripping true crime story about a real case — a mystery, "
            "unsolved disappearance, or notorious crime. Focus on the facts, "
            "the investigation, and the human drama. Keep it compelling and factual."
        ),
    },
    PresetKey.stoic_motivation: {
        "name": "Stoic Motivation",
        "niche": "motivation",
        "topic": (
            "Share powerful stoic philosophy wisdom and life lessons that can help "
            "people overcome adversity, build resilience, and live with purpose. "
            "Reference Marcus Aurelius, Epictetus, or Seneca. Make it actionable "
            "and deeply motivating."
        ),
    },
    PresetKey.marketing_business: {
        "name": "Marketing & Business",
        "niche": "business",
        "topic": (
            "Share a powerful marketing insight, business growth strategy, or "
            "entrepreneurship lesson. Include a real-world example or case study. "
            "Make it practical, data-driven, and immediately actionable for "
            "founders, marketers, and business owners."
        ),
    },
    PresetKey.tech_innovation: {
        "name": "Tech & Innovation",
        "niche": "technology",
        "topic": (
            "Explain a cutting-edge technology, AI breakthrough, or innovation "
            "that is changing the world right now. Break down complex concepts "
            "simply. Focus on the real-world impact and what it means for the future."
        ),
    },
}

# Detected tone → VideoStyle mapping for the voice flow
_TONE_TO_STYLE: dict[str, str] = {
    "excited":       "modern_energetic",
    "urgent":        "modern_energetic",
    "dramatic":      "dramatic",
    "storytelling":  "modern_energetic",
    "calm":          "minimal",
    "conversational": "fun",
    "authoritative": "corporate",
}


@router.post("/projects/{project_id}/generate-plot-options")
async def generate_plot_options(
    project_id: UUID,
    request: GenerateScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate 3 brief story/plot direction options for the user to choose from.

    Fast single Gemini call (not the full agentic loop).
    Returns 3 options with a short title and 2-3 sentence summary each.
    """
    import asyncio
    from google.genai import types
    from services.gemini.client import get_client

    # Resolve transcript (same logic as generate_script)
    transcript: str

    if request.source == ScriptSource.voice:
        if not request.audio_base64:
            raise HTTPException(status_code=422, detail="audio_base64 is required when source=voice")
        from services.gemini import audio as gemini_audio
        try:
            result = await gemini_audio.transcribe_with_tone(
                audio_b64=request.audio_base64,
                audio_format=request.audio_format,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
        transcript = result["transcript"]

    elif request.source == ScriptSource.text:
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(status_code=422, detail="transcript is required when source=text")
        transcript = request.transcript.strip()

    elif request.source == ScriptSource.preset:
        if not request.preset:
            raise HTTPException(status_code=422, detail="preset is required when source=preset")
        preset_def = _PRESETS[request.preset]
        transcript = preset_def["topic"]
        if request.topic_hint and request.topic_hint.strip():
            transcript = f"{transcript}\n\nSpecific angle: {request.topic_hint.strip()}"

    else:
        raise HTTPException(status_code=422, detail=f"Unknown source: {request.source}")

    # ── Reddit context (non-fatal) ─────────────────────────────────────────────
    reddit_ctx: dict = {}
    try:
        reddit_ctx = await reddit.fetch_trending(niche=None, transcript=transcript)
    except Exception as _reddit_err:
        logger.debug("Reddit fetch skipped for plot options: %s", _reddit_err)

    reddit_section = ""
    if reddit_ctx.get("top_topics"):
        topics = "\n".join(f"- {t}" for t in reddit_ctx["top_topics"][:6])
        reddit_section = (
            f"\n\nTRENDING TOPICS RIGHT NOW (from Reddit):\n{topics}\n"
            "Use these as fresh inspiration angles where relevant to the brief."
        )

    # ── Image subject inference (non-fatal) ───────────────────────────────────
    subject_section = ""
    if request.user_reference_image_b64:
        import base64
        import os
        import tempfile
        from services.gemini.image import describe_reference_subject
        tmp_path: str | None = None
        try:
            img_bytes = base64.b64decode(request.user_reference_image_b64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name
            subject_description = await describe_reference_subject(tmp_path)
            if subject_description:
                subject_section = (
                    f"\n\nSubject context (person in user's reference photo): {subject_description}\n"
                    "Tailor the plot directions to feature or involve this person naturally."
                )
        except Exception as _img_err:
            logger.debug("Image inference skipped for plot options: %s", _img_err)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    avoid_section = ""
    if request.previous_options:
        joined = "\n".join(f"- {o}" for o in request.previous_options)
        avoid_section = (
            f"\n\nThe following plot directions were ALREADY shown to the user — "
            f"do NOT repeat or closely resemble them:\n{joined}\n"
            "Generate 3 COMPLETELY DIFFERENT angles."
        )

    prompt = (
        "You are a creative director for short-form video content.\n\n"
        "Based on the following content brief, generate exactly 3 DISTINCT story/plot directions "
        "for a short-form video. Each option must be meaningfully different — vary the angle, "
        "tone, narrative hook, or emotional journey.\n\n"
        f"Content brief:\n{transcript}"
        f"{reddit_section}"
        f"{subject_section}"
        f"{avoid_section}"
        "\n\nRespond ONLY with a valid JSON array, no markdown, no explanation:\n"
        '[{"id":1,"title":"Short title 4-6 words","summary":"2-3 sentence description."},'
        '{"id":2,"title":"Short title 4-6 words","summary":"2-3 sentence description."},'
        '{"id":3,"title":"Short title 4-6 words","summary":"2-3 sentence description."}]'
    )

    def _generate():
        client = get_client()
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json",
            ),
        )
        return response.text

    try:
        raw = await asyncio.to_thread(_generate)
        options = json.loads(raw)
        if not isinstance(options, list):
            raise ValueError("Expected a JSON array")
        return {"options": options[:3]}
    except Exception as e:
        logger.exception("generate-plot-options failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Plot options generation failed: {e}")


@router.post("/projects/{project_id}/generate-script", response_model=ScriptGenerationResponse)
async def generate_script(
    project_id: UUID,
    request: GenerateScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate a video script — supports voice, text, and preset input modes.

    Returns the script for user review. Call /generate-video once approved.
    Can be called multiple times to regenerate.
    """
    # ── Step 1: Resolve transcript + style from source ─────────────────────────
    transcript: str
    style: str = request.style.value
    reddit_ctx: dict = {}
    niche: str | None = None

    if request.source == ScriptSource.voice:
        if not request.audio_base64:
            raise HTTPException(status_code=422, detail="audio_base64 is required when source=voice")

        from services.gemini import audio as gemini_audio
        try:
            result = await gemini_audio.transcribe_with_tone(
                audio_b64=request.audio_base64,
                audio_format=request.audio_format,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.exception("Gemini audio transcription failed for project %s", project_id)
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

        transcript = result["transcript"]
        detected_tone = result.get("detected_tone", "conversational")
        style = _TONE_TO_STYLE.get(detected_tone, request.style.value)
        logger.info("Voice flow: %d chars transcribed, tone=%s → style=%s", len(transcript), detected_tone, style)

    elif request.source == ScriptSource.text:
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(status_code=422, detail="transcript is required when source=text")
        transcript = request.transcript.strip()

    elif request.source == ScriptSource.preset:
        if not request.preset:
            raise HTTPException(status_code=422, detail="preset is required when source=preset")

        preset_def = _PRESETS[request.preset]
        niche = preset_def["niche"]
        transcript = preset_def["topic"]
        if request.topic_hint and request.topic_hint.strip():
            transcript = f"{transcript}\n\nSpecific angle: {request.topic_hint.strip()}"

        # Fetch Reddit trending topics for this niche — inject as agent context
        try:
            reddit_ctx = await reddit.fetch_trending(niche=niche, transcript=transcript)
            n_posts = len(reddit_ctx.get("hot_posts", [])) + len(reddit_ctx.get("controversial_posts", []))
            logger.info("Reddit context: niche=%s, %d posts", niche, n_posts)
        except Exception as reddit_err:
            logger.warning("Reddit research failed (non-fatal): %s", reddit_err)

    else:
        raise HTTPException(status_code=422, detail=f"Unknown source: {request.source}")

    # ── Step 2: Resolve video config (series overrides manual fields) ──────────
    series: SeriesConfig | None = None
    if request.series_id:
        try:
            config_data = await gcs.load_json(f"series/{request.series_id}/config.json")
            series = SeriesConfig(**config_data)
            logger.info("Loaded series config %s (%s)", request.series_id, series.series_name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

    # Effective values — series wins over manual request fields
    art_style    = series.art_style.value       if series else request.art_style.value
    video_format = series.video_format.value    if series else request.video_format.value
    effective_niche = series.niche              if series else niche
    video_duration = (
        DURATION_MAP.get(series.video_duration.value, request.video_duration)
        if series else request.video_duration
    )

    # ── Step 3: Gemini agentic script generation ───────────────────────────────
    try:
        script_data = await generate_script_with_agent(
            transcript=transcript,
            target_platforms=[p.value for p in request.target_platforms],
            style=style,
            video_duration=video_duration,
            brand_voice=request.brand_voice,
            cta_preference=request.cta_preference,
            niche=effective_niche,
            art_style=art_style,
            video_format=video_format,
            reddit_context=reddit_ctx or None,
        )
    except Exception as e:
        logger.exception("Script generation failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Script generation failed: {e}")

    script = ScriptGenerationResponse(**script_data)
    script.project_id = project_id
    return script


@router.post("/projects/{project_id}/generate-script-stream")
async def generate_script_stream(
    project_id: UUID,
    request: GenerateScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Stream Scout (ADK agent) progress as SSE, then deliver the final script.

    Each SSE event is one JSON dict:
      data: {"type":"agent_step","tool":"search_trending_hooks","message":"Researching…"}
      data: {"type":"agent_step","tool":"finalize_script","message":"Finalizing script…"}
      data: {"type":"complete","script":{...}}
      data: {"type":"error","message":"..."}
    """
    # ── Step 1: Resolve transcript + style (identical to generate_script) ──────
    transcript: str
    style: str = request.style.value
    reddit_ctx: dict = {}
    niche: str | None = None

    if request.source == ScriptSource.voice:
        if not request.audio_base64:
            raise HTTPException(status_code=422, detail="audio_base64 is required when source=voice")
        from services.gemini import audio as gemini_audio
        try:
            result = await gemini_audio.transcribe_with_tone(
                audio_b64=request.audio_base64,
                audio_format=request.audio_format,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
        transcript = result["transcript"]
        detected_tone = result.get("detected_tone", "conversational")
        style = _TONE_TO_STYLE.get(detected_tone, request.style.value)

    elif request.source == ScriptSource.text:
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(status_code=422, detail="transcript is required when source=text")
        transcript = request.transcript.strip()

    elif request.source == ScriptSource.preset:
        if not request.preset:
            raise HTTPException(status_code=422, detail="preset is required when source=preset")
        preset_def = _PRESETS[request.preset]
        niche = preset_def["niche"]
        transcript = preset_def["topic"]
        if request.topic_hint and request.topic_hint.strip():
            transcript = f"{transcript}\n\nSpecific angle: {request.topic_hint.strip()}"
        try:
            reddit_ctx = await reddit.fetch_trending(niche=niche, transcript=transcript)
        except Exception as reddit_err:
            logger.warning("Reddit research failed (non-fatal): %s", reddit_err)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown source: {request.source}")

    # Inject user-selected plot direction as a preamble so the agent follows it
    if request.plot_summary:
        transcript = (
            f"User selected this story direction: {request.plot_summary}\n\n"
            f"Content context: {transcript}"
        )

    # Inject character role hint when user has uploaded a reference photo
    if request.user_character_role:
        transcript = (
            f"Character context: The user will appear as '{request.user_character_role}' in the video "
            f"(they uploaded a reference photo of themselves). Write scenes that portray this character "
            f"consistently with their role.\n\n{transcript}"
        )

    # ── Step 2: Resolve video config ───────────────────────────────────────────
    series = None
    if request.series_id:
        try:
            config_data = await gcs.load_json(f"series/{request.series_id}/config.json")
            series = SeriesConfig(**config_data)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Series '{request.series_id}' not found: {e}")

    art_style    = series.art_style.value    if series else request.art_style.value
    video_format = series.video_format.value if series else request.video_format.value
    effective_niche = series.niche           if series else niche
    video_duration = (
        DURATION_MAP.get(series.video_duration.value, request.video_duration)
        if series else request.video_duration
    )

    # ── Step 3: Stream ADK agent events ────────────────────────────────────────
    from services.gemini.agent import stream_script_agent

    async def event_gen():
        try:
            async for event in stream_script_agent(
                transcript=transcript,
                target_platforms=[p.value for p in request.target_platforms],
                style=style,
                video_duration=video_duration,
                brand_voice=request.brand_voice,
                cta_preference=request.cta_preference,
                niche=effective_niche,
                art_style=art_style,
                video_format=video_format,
                reddit_context=reddit_ctx or None,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("SSE script stream failed for project %s", project_id)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{project_id}/queue-script", status_code=202)
async def queue_script(project_id: UUID, request: QueueScriptRequest, current_user: dict = Depends(get_current_user)):
    """Queue async script generation for a project.

    Saves all config to Firestore, offloads voice audio to GCS if needed,
    then enqueues a Cloud Tasks job. Returns 202 immediately.
    Poll GET /api/v1/projects/{id}/status for progress.
    """
    pid = str(project_id)
    now = datetime.now(timezone.utc).isoformat()

    if request.source == ScriptSource.voice and not request.audio_base64:
        raise HTTPException(status_code=422, detail="audio_base64 is required when source=voice")
    if request.source == ScriptSource.text and not (request.transcript or "").strip():
        raise HTTPException(status_code=422, detail="transcript is required when source=text")
    if request.source == ScriptSource.preset and not request.preset:
        raise HTTPException(status_code=422, detail="preset is required when source=preset")

    # ── Offload audio to GCS so the worker can download it ──────────────────
    audio_gcs_key: str | None = None
    if request.source == ScriptSource.voice and request.audio_base64:
        audio_bytes = base64.b64decode(request.audio_base64)
        audio_gcs_key = f"user_audio/{pid}/input.{request.audio_format}"
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{request.audio_format}") as f:
                f.write(audio_bytes)
                tmp_path = f.name
            await gcs.upload_file(tmp_path, audio_gcs_key, f"audio/{request.audio_format}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload audio: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── Save config to Firestore (excluding raw audio) ───────────────────────
    config = request.model_dump(exclude={"audio_base64"})
    if request.preset:
        config["preset"] = request.preset.value
    doc: dict = {
        "project_id": pid,
        "uid": current_user["uid"],
        "created_at": now,
        "queued_at": now,
        "status": "queued",
        "current_stage": "Waiting to start",
        "progress_pct": 0,
        "pipeline_config": config,
        "audio_gcs_key": audio_gcs_key,
        "video_urls": {},
    }
    try:
        await firestore_db.save_project(pid, doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save project: {e}")

    # ── Enqueue the script generation task ───────────────────────────────────
    try:
        task_name = await task_queue.enqueue_script_generation(pid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue script generation: {e}")

    logger.info("Script generation queued for project %s (task=%s)", pid, task_name)
    return JSONResponse(status_code=202, content={
        "project_id": pid,
        "status": "queued",
        "poll_url": f"/api/v1/projects/{pid}/status",
    })
