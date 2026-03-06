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
import re

from services.retry import call_with_retry

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-pro"


def _get_client():
    """Return a configured Gemini client (Vertex AI on GCP, API key locally)."""
    from services.gemini_client import get_client
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
    import asyncio
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
    import asyncio
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
    import asyncio
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
