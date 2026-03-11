"""Gemini Reasoning — content intelligence agent for Content Factory.

Replaces nemotron.py. Identical public interface.

Gemini 3 Pro replaces Nemotron nano for three reasoning tasks:
  - research_hooks()         → multi-step hook analysis for niche + platform
  - score_script()           → independent, unbiased script quality evaluation
  - auto_configure_series()  → multi-agent reasoning to auto-generate series config
"""

from __future__ import annotations

import json
import logging
import os
import re
from uuid import uuid4

from services.gemini.models import MODELS
from services.infra.retry import call_with_retry

logger = logging.getLogger(__name__)

MODEL = MODELS.reasoning


def _get_client():
    """Return a configured Gemini client (Vertex AI on GCP, API key locally)."""
    from services.gemini.client import get_client
    return get_client()


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a Gemini response."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


async def research_hooks(niche: str, platform: str, style: str = "modern_energetic") -> dict:
    """Gemini: reason about viral hook patterns for this niche + platform.

    Drop-in replacement for nemotron.research_hooks().
    Same return shape: {"reasoning": ..., "hooks": [...], "platform_insight": ..., "scored_by": "gemini"}
    """
    client = _get_client()
    if not client:
        logger.warning("Gemini Reasoning: GEMINI_API_KEY not set — skipping hook research")
        return {}

    prompt = f"""You are a viral content analyst specializing in short-form video hooks.

Analyze and reason step-by-step about the best hook patterns for:
- Content niche: {niche}
- Platform: {platform}
- Style: {style}

Think through this carefully:
1. What does the target audience in '{niche}' care about most?
2. What emotional triggers drive shares on {platform}?
3. What hook patterns have the highest watch-through rate for this niche?
4. Write 3 ready-to-use, highly specific hooks adapted to this EXACT niche

Respond ONLY with a JSON object:
{{
  "reasoning": "Your step-by-step analysis",
  "hooks": [
    {{"text": "specific hook text", "type": "mystery|warning|correction|insider|story|revelation", "why_it_works": "psychological reason"}},
    {{"text": "specific hook text", "type": "type", "why_it_works": "reason"}},
    {{"text": "specific hook text", "type": "type", "why_it_works": "reason"}}
  ],
  "platform_insight": "One key behavioral insight about {platform} users in this niche",
  "recommended_hook_index": 0
}}"""

    try:
        response = await call_with_retry(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
        )
        content = response.text
        logger.info("Gemini research_hooks: got %d chars", len(content))

        result = _extract_json(content)
        if result:
            result["scored_by"] = "gemini"
            logger.info("Gemini hooks: %d hooks generated", len(result.get("hooks", [])))
            return result

        return {"reasoning": content, "hooks": [], "scored_by": "gemini"}

    except Exception as e:
        logger.warning("Gemini research_hooks failed: %s", e)
        return {}


async def score_script(
    hook: str,
    scenes: list,
    cta: str,
    platform: str = "instagram_reels",
    target_duration: int = 30,
) -> dict:
    """Gemini: independently evaluate script quality with step-by-step reasoning.

    Drop-in replacement for nemotron.score_script().
    Same return shape including "scored_by": "gemini"
    """
    client = _get_client()
    if not client:
        logger.warning("Gemini Reasoning: GEMINI_API_KEY not set — skipping script scoring")
        return {}

    scenes_text = "\n".join(
        f"  Scene {s.get('scene_id', i + 1)} ({s.get('duration_seconds', '?')}s): "
        f"{s.get('voiceover_text', '')}"
        for i, s in enumerate(scenes)
    )

    prompt = f"""You are an expert viral content evaluator with deep knowledge of {platform} behavior.

Evaluate this short-form video script with rigorous step-by-step reasoning:

HOOK: "{hook}"

SCENES:
{scenes_text}

CTA: "{cta}"

Platform: {platform}
Target duration: {target_duration}s

Score each dimension (be strict — average scripts score 60-75, great ones 80+):
1. HOOK (30 pts): Immediate curiosity or emotion in ≤2 seconds?
2. STORY ARC (40 pts): Natural build? Tension → payoff? Voiceover flow?
3. CTA (20 pts): Specific, platform-appropriate, emotionally motivated?
4. PACING (10 pts): Word count matches {target_duration}s (~{int(target_duration * 2.5)} words)?

Respond ONLY with JSON:
{{
  "score": <integer 0-100>,
  "hook_score": <integer 0-30>,
  "story_score": <integer 0-40>,
  "cta_score": <integer 0-20>,
  "pacing_score": <integer 0-10>,
  "passed": <true if score >= 70>,
  "reasoning": "Detailed step-by-step evaluation",
  "top_strength": "The single strongest element",
  "top_weakness": "The single most important thing to improve",
  "recommendation": "Call finalize_script" or "Revise: [specific instruction]"
}}"""

    try:
        response = await call_with_retry(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
        )
        content = response.text
        logger.info("Gemini score_script: got %d chars", len(content))

        result = _extract_json(content)
        if result:
            result["scored_by"] = "gemini"
            logger.info("Gemini score: %s/100 passed=%s", result.get("score"), result.get("passed"))
            return result

        return {"score": 70, "passed": True, "reasoning": content, "scored_by": "gemini"}

    except Exception as e:
        logger.warning("Gemini score_script failed: %s", e)
        return {}


async def auto_configure_series(
    transcript: str,
    target_platforms: list[str] | None = None,
    reddit_context: dict | None = None,
    analytics_context: dict | None = None,
) -> dict:
    """Gemini: analyze a raw idea and auto-generate a complete series config.

    Drop-in replacement for nemotron.auto_configure_series().
    Same return shape, configured_by = "gemini"
    """
    client = _get_client()
    if not client:
        logger.warning("Gemini Reasoning: GEMINI_API_KEY not set — skipping auto_configure_series")
        return {}

    platforms_hint = ", ".join(target_platforms) if target_platforms else "instagram_reels"

    reddit_section = ""
    if reddit_context and reddit_context.get("top_topics"):
        topics = reddit_context["top_topics"]
        subreddits = ", ".join(f"r/{s}" for s in reddit_context.get("subreddits_searched", []))
        bullet_topics = "\n".join(f"  • {t}" for t in topics[:8])
        reddit_section = f"""
REDDIT TRENDING SIGNAL (live data from {subreddits}):
{bullet_topics}
Use these to identify the most engaging angle and pick the best video format for current audience interest.
"""

    analytics_section = ""
    if analytics_context:
        art_rows = analytics_context.get("art_style_performance", [])
        niche_rows = analytics_context.get("top_niches", [])
        total_runs = analytics_context.get("total_runs", 0)
        if art_rows or niche_rows:
            art_lines = "\n".join(
                f"  {i+1}. {r['art_style']} — avg quality: {r.get('avg_quality', '?')}/100 ({r.get('runs', '?')} runs)"
                for i, r in enumerate(art_rows[:5])
            )
            niche_lines = "\n".join(
                f"  {i+1}. {r['niche']} — avg quality: {r.get('avg_quality', '?')}/100 ({r.get('runs', '?')} runs)"
                for i, r in enumerate(niche_rows[:5])
            )
            analytics_section = f"""
DATABRICKS PERFORMANCE INTELLIGENCE ({total_runs} historical pipeline runs):
Best art styles: {art_lines or 'No data yet'}
Best niches: {niche_lines or 'No data yet'}
Strongly prefer art styles with highest historical quality scores.
"""

    prompt = f"""You are a creative content strategist. Analyze this transcript and auto-configure a complete short-form video series.

TRANSCRIPT:
\"\"\"{transcript}\"\"\"

TARGET PLATFORMS: {platforms_hint}
{reddit_section}{analytics_section}
Work through this as 5 specialized sub-agents:

**Sub-agent 1 — Content Analyst:** Core topic, niche, emotional tone
**Sub-agent 2 — Audience Profiler:** Target audience, platform behavior
**Sub-agent 3 — Creative Director:** Pick art_style from EXACTLY one of:
  "realism" | "creepy_comic" | "ghibli" | "comic" | "painting" | "polaroid" | "disney"
**Sub-agent 4 — Platform Strategist:**
  target_platforms from: ["instagram_reels", "tiktok", "youtube_shorts"]
  video_duration from EXACTLY one of: "15-30" | "30-40" | "60+"
  video_format from EXACTLY one of: "storytelling" | "what_if" | "five_things" | "random_fact"
**Sub-agent 5 — Production Designer:**
  caption_style from EXACTLY one of: "beast" | "bold_stroke" | "karaoke" | "majestic" | "red_highlight" | "sleek" | "elegant"
  background_music from EXACTLY one of: "breathing_shadows" | "quiet_before_storm" | "brilliant_symphony" | "happy_rhythm" | "peaceful_vibes" | "none"
  voice_id + voice_name from EXACTLY one of:
    "TxGEqnHWrfWFTfGW9XjX" / "Josh" = young conversational casual
    "pNInz6obpgDQGcFmaJgB" / "Adam" = deep authoritative serious
    "21m00Tcm4TlvDq8ikWAM" / "Rachel" = calm lifestyle wellness
    "EXAVITQu4vr4xnSDxMaL" / "Bella" = soft gentle mindful
    "VR6AewLTigWG4xSOukaG" / "Arnold" = crisp educational informative
  music_volume: float 0.10–0.30
  series_name: punchy 2-3 word name

Respond ONLY with JSON:
{{
  "series_name": "...",
  "niche": "...",
  "art_style": "...",
  "caption_style": "...",
  "background_music": "...",
  "music_volume": 0.20,
  "voice_id": "...",
  "voice_name": "...",
  "video_duration": "...",
  "video_format": "...",
  "target_platforms": ["..."],
  "reasoning": "5-6 sentences explaining each sub-agent decision"
}}"""

    try:
        response = await call_with_retry(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
        )
        content = response.text
        logger.info("Gemini auto_configure_series: got %d chars", len(content))

        result = _extract_json(content)
        if result:
            result["configured_by"] = "gemini"
            logger.info(
                "Gemini auto-config: series=%r art=%s music=%s voice=%s",
                result.get("series_name"), result.get("art_style"),
                result.get("background_music"), result.get("voice_name"),
            )
            return result

        logger.warning("Gemini auto_configure_series: could not parse JSON")
        return {}

    except Exception as e:
        logger.warning("Gemini auto_configure_series failed: %s", e)
        return {}


# ── Second ADK agent: auto_configure_series_adk ────────────────────────────────
# Showcases multi-agent architecture: 5 specialist sub-agents as ADK tools.

_ART_STYLES = ["realism", "creepy_comic", "ghibli", "comic", "painting", "polaroid", "disney"]
_CAPTION_STYLES = ["beast", "bold_stroke", "karaoke", "majestic", "red_highlight", "sleek", "elegant"]
_MUSIC_PRESETS = ["breathing_shadows", "quiet_before_storm", "brilliant_symphony", "happy_rhythm", "peaceful_vibes", "none"]
_VOICES = [
    {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "voice_name": "Josh",   "profile": "young conversational casual"},
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "voice_name": "Adam",   "profile": "deep authoritative serious"},
    {"voice_id": "21m00Tcm4TlvDq8ikWAM", "voice_name": "Rachel", "profile": "calm lifestyle wellness"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "voice_name": "Bella",  "profile": "soft gentle mindful"},
    {"voice_id": "VR6AewLTigWG4xSOukaG", "voice_name": "Arnold", "profile": "crisp educational informative"},
]


def _analyze_content(transcript: str, target_platforms: str) -> dict:
    """Sub-agent 1 — Content Analyst: identify niche, tone, and key topic from transcript.

    Args:
        transcript: Raw transcript or idea text to analyze.
        target_platforms: Comma-separated target platform names.
    """
    return {
        "transcript_length": len(transcript),
        "platforms": target_platforms,
        "instruction": (
            "Identify: (1) the core niche/topic category, (2) emotional tone "
            "(exciting/calm/dramatic/educational/funny), (3) target audience age range, "
            "(4) content angle (story/facts/how-to/opinion). Return as structured analysis."
        ),
    }


def _profile_audience(niche: str, primary_platform: str) -> dict:
    """Sub-agent 2 — Audience Profiler: describe target audience and platform behavior.

    Args:
        niche: Content niche identified by the Content Analyst.
        primary_platform: Primary target platform (instagram_reels, tiktok, youtube_shorts).
    """
    platform_behaviors = {
        "instagram_reels": "Saves and shares drive reach; hook in 2s; 15-30s optimal",
        "tiktok": "Re-hooks needed at 5s and 15s; duets/stitches amplify; 15-60s",
        "youtube_shorts": "Subscription intent; can build context over 3-5 scenes; 30-60s",
    }
    return {
        "niche": niche,
        "platform": primary_platform,
        "platform_behavior": platform_behaviors.get(primary_platform, platform_behaviors["instagram_reels"]),
        "art_style_options": _ART_STYLES,
        "instruction": "Based on niche + platform behavior, recommend the ideal viewer profile and content tone.",
    }


def _select_creative_style(niche: str, emotional_tone: str, analytics_hint: str = "") -> dict:
    """Sub-agent 3 — Creative Director: pick art style, caption style, and background music.

    Args:
        niche: Content niche (horror, finance, fitness, etc.).
        emotional_tone: Tone from Content Analyst (exciting, calm, dramatic, educational, funny).
        analytics_hint: Optional performance data string to bias style selection.
    """
    return {
        "niche": niche,
        "emotional_tone": emotional_tone,
        "analytics_hint": analytics_hint or "No historical data",
        "available_art_styles": _ART_STYLES,
        "available_caption_styles": _CAPTION_STYLES,
        "available_music": _MUSIC_PRESETS,
        "instruction": (
            "Pick EXACTLY one art_style, one caption_style, one background_music. "
            "Return choices with a one-sentence rationale for each."
        ),
    }


def _select_production_config(primary_platform: str, emotional_tone: str) -> dict:
    """Sub-agent 4 — Platform Strategist: select voice, video duration, and format.

    Args:
        primary_platform: Target platform (instagram_reels, tiktok, youtube_shorts).
        emotional_tone: Tone from Content Analyst.
    """
    return {
        "platform": primary_platform,
        "emotional_tone": emotional_tone,
        "available_voices": _VOICES,
        "duration_options": ["15-30", "30-40", "60+"],
        "format_options": ["storytelling", "what_if", "five_things", "random_fact"],
        "instruction": (
            "Choose voice_id + voice_name that matches the emotional tone. "
            "Choose video_duration and video_format that suit the platform and tone. "
            "Recommend music_volume between 0.10 and 0.30."
        ),
    }


async def _commit_series_config(
    series_name: str,
    niche: str,
    art_style: str,
    caption_style: str,
    background_music: str,
    music_volume: float,
    voice_id: str,
    voice_name: str,
    video_duration: str,
    video_format: str,
    target_platforms_json: str,
    reasoning: str,
    tool_context=None,
) -> dict:
    """Sub-agent 5 — Production Designer: commit final series configuration.

    Call ONLY after all four other sub-agents have been consulted.

    Args:
        series_name: Punchy 2-3 word series name.
        niche: Content niche.
        art_style: Chosen art style (must be one of the available options).
        caption_style: Chosen caption style.
        background_music: Chosen music preset.
        music_volume: Music volume between 0.10 and 0.30.
        voice_id: ElevenLabs voice ID string.
        voice_name: Human-readable voice name.
        video_duration: Duration range string (15-30, 30-40, or 60+).
        video_format: Format string (storytelling, what_if, five_things, random_fact).
        target_platforms_json: JSON array string of platform names.
        reasoning: 3-5 sentence explanation of all decisions.
    """
    try:
        target_platforms = json.loads(target_platforms_json) if target_platforms_json else ["instagram_reels"]
    except json.JSONDecodeError:
        target_platforms = ["instagram_reels"]

    config = {
        "series_name": series_name,
        "niche": niche,
        "art_style": art_style,
        "caption_style": caption_style,
        "background_music": background_music,
        "music_volume": float(music_volume),
        "voice_id": voice_id,
        "voice_name": voice_name,
        "video_duration": video_duration,
        "video_format": video_format,
        "target_platforms": target_platforms,
        "reasoning": reasoning,
        "configured_by": "google-adk",
    }
    if tool_context is not None:
        tool_context.state["series_config"] = config
    return {"status": "accepted", "message": "Series configuration committed."}


async def auto_configure_series_adk(
    transcript: str,
    target_platforms: list[str] | None = None,
    reddit_context: dict | None = None,
    analytics_context: dict | None = None,
) -> dict:
    """ADK multi-agent version of auto_configure_series.

    5 specialist sub-agents collaborate as ADK tools to auto-generate a complete
    series config from a raw transcript. Drop-in replacement — same return shape,
    configured_by = 'google-adk'.
    """
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import ToolContext
    from google.genai import types as genai_types

    from config import get_settings
    settings = get_settings()

    if settings.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.vertex_ai_location)
    elif settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)

    platforms_str = ", ".join(target_platforms) if target_platforms else "instagram_reels"

    reddit_hint = ""
    if reddit_context and reddit_context.get("top_topics"):
        topics = "\n".join(f"  • {t}" for t in reddit_context["top_topics"][:6])
        reddit_hint = f"\n\nTRENDING ON REDDIT:\n{topics}"

    analytics_hint = ""
    if analytics_context:
        art_rows = analytics_context.get("art_style_performance", [])
        if art_rows:
            analytics_hint = "Best performing art styles: " + ", ".join(
                f"{r['art_style']} ({r.get('avg_quality', '?')}/100)"
                for r in art_rows[:3]
            )

    system = (
        "You are the Content Factory series configurator. "
        "Use your 5 specialist sub-agent tools IN ORDER to analyse a transcript "
        "and produce a complete series configuration:\n\n"
        "1. Call _analyze_content — identify niche and tone\n"
        "2. Call _profile_audience — understand the target viewer\n"
        "3. Call _select_creative_style — pick art style, captions, music\n"
        "4. Call _select_production_config — pick voice, duration, format\n"
        "5. Call _commit_series_config — commit ALL decisions\n\n"
        "You MUST call all five tools and commit before finishing."
    )

    app_name = "content-factory-config"
    user_id = "series-configurator"
    session_id = str(uuid4())

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    agent = Agent(
        name="series_configurator",
        model=MODEL,
        instruction=system,
        tools=[
            _analyze_content,
            _profile_audience,
            _select_creative_style,
            _select_production_config,
            _commit_series_config,
        ],
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=(
            f"Configure a video series for this transcript:\n\n{transcript}\n\n"
            f"Target platforms: {platforms_str}{reddit_hint}"
            + (f"\n\nAnalytics hint: {analytics_hint}" if analytics_hint else "")
        ))],
    )

    logger.info("ADK series configurator starting (platforms=%s)", platforms_str)

    try:
        async for _event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            pass

        session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        config = (session.state or {}).get("series_config")
        if config:
            logger.info(
                "ADK series config: series=%r art=%s voice=%s",
                config.get("series_name"), config.get("art_style"), config.get("voice_name"),
            )
            return config

        logger.warning("ADK series configurator: _commit_series_config was not called — falling back")

    except Exception as exc:
        logger.debug("ADK series configurator traceback", exc_info=True)
        logger.warning(
            "ADK series configurator failed (%s): %s — falling back to single-call",
            type(exc).__name__, exc,
        )

    # Fall back to the original single-call implementation
    return await auto_configure_series(transcript, target_platforms, reddit_context, analytics_context)
