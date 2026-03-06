"""Generate-script router — unified endpoint for all three input flows.

POST /api/v1/projects/{project_id}/generate-script

Flow is determined by the `source` field:

  source="voice"   (Flow 1) — User records a voice memo.
                              Gemini multimodal transcribes the audio and detects
                              the speaker's emotional tone. Tone feeds into the
                              agent as a style signal.

  source="text"    (Flow 2) — User types their idea directly.
                              Text goes straight to the Gemini script agent.

  source="preset"  (Flow 3) — User selects a content preset (scary stories,
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

import logging
from uuid import UUID

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import (
    ArtStyle,
    GenerateScriptRequest,
    MusicPreset,
    PresetKey,
    ScriptGenerationResponse,
    ScriptSource,
    SeriesConfig,
    VideoFormat,
    VideoDurationRange,
)
from routers.catalog import DURATION_MAP
from services import gcs, reddit
from services.gemini_agent import generate_script_with_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["script"])


# ── Preset definitions ─────────────────────────────────────────────────────────
# Moved here from preset_process.py — only used for the generate-script preset flow.

_PRESETS: dict[PresetKey, dict] = {
    PresetKey.scary_stories: {
        "name": "Scary Stories",
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


@router.post("/projects/{project_id}/generate-script", response_model=ScriptGenerationResponse)
async def generate_script(project_id: UUID, request: GenerateScriptRequest):
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

        from services import gemini_audio
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
async def generate_script_stream(project_id: UUID, request: GenerateScriptRequest):
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
        from services import gemini_audio
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
    from services.gemini_agent import stream_script_agent

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
