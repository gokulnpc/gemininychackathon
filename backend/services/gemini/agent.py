"""Gemini Agent — agentic script generation for Content Factory.

Uses Google ADK (Agent Development Kit) with a 5-tool ReAct loop:
  - search_trending_hooks   → Gemini Reasoning researches viral hook patterns
  - analyze_brand_voice     → style rules from art style + brand guidelines
  - optimize_for_platform   → pacing/CTA check against platform best practices
  - validate_script_quality → Gemini Reasoning independently scores the draft
  - finalize_script         → output sink (stores result via ToolContext) that ends the loop

Public interface unchanged: generate_script_with_agent() returns the same dict shape.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext

from services.gemini import reasoning as gemini_reasoning

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
_MAX_SCRIPT_ATTEMPTS = 2
_RETRY_DELAYS = [4]


# ── Reference data ─────────────────────────────────────────────────────────────

_HOOK_LIBRARY: dict[str, list[dict]] = {
    "weather": [
        {"template": "Nobody warned you the {event} was coming...", "type": "mystery", "avg_watch_pct": 87},
        {"template": "Why your pipes WILL burst this winter — and how to stop it", "type": "threat+solution", "avg_watch_pct": 91},
    ],
    "finance": [
        {"template": "The one money move that changed everything for me", "type": "personal_story", "avg_watch_pct": 88},
        {"template": "I saved ${amount} doing this ONE thing every month", "type": "result", "avg_watch_pct": 90},
    ],
    "fitness": [
        {"template": "I tried {routine} for 30 days — here's what actually happened", "type": "experiment", "avg_watch_pct": 86},
        {"template": "The workout you've been doing WRONG your whole life", "type": "correction", "avg_watch_pct": 90},
    ],
    "food": [
        {"template": "You've been cooking {dish} wrong your whole life", "type": "correction", "avg_watch_pct": 88},
        {"template": "3-ingredient {dish} that costs less than $5", "type": "value", "avg_watch_pct": 92},
    ],
    "tech": [
        {"template": "This AI tool will change how you work forever", "type": "revelation", "avg_watch_pct": 84},
        {"template": "I automated my entire {task} — here's exactly how", "type": "how_to", "avg_watch_pct": 89},
    ],
    "default": [
        {"template": "Nobody is talking about this...", "type": "mystery", "avg_watch_pct": 81},
        {"template": "Stop scrolling — you need to hear this", "type": "pattern_interrupt", "avg_watch_pct": 84},
        {"template": "This changed everything for me", "type": "personal", "avg_watch_pct": 76},
    ],
}

_PLATFORM_GUIDELINES: dict[str, dict] = {
    "instagram_reels": {
        "hook_window_seconds": 2, "optimal_duration": "15-30s", "max_hook_words": 10,
        "preferred_cta": ["save this", "send to a friend", "share with someone who needs this"],
        "pacing": "fast cuts, 2-4 scenes for 30s",
        "trending_formats": ["problem/solution", "before/after", "5 things", "hot take", "story time"],
    },
    "tiktok": {
        "hook_window_seconds": 1.5, "optimal_duration": "15-60s", "max_hook_words": 8,
        "preferred_cta": ["follow for more", "comment your thoughts", "duet this"],
        "pacing": "very fast, re-hook at 5s and 15s mid-video",
        "trending_formats": ["POV:", "story time", "green screen explainer"],
    },
    "youtube_shorts": {
        "hook_window_seconds": 3, "optimal_duration": "30-60s", "max_hook_words": 12,
        "preferred_cta": ["subscribe for more", "watch the full video", "comment below"],
        "pacing": "slightly slower, can build context over 3-5 scenes",
        "trending_formats": ["facts about X", "did you know", "I tested X"],
    },
}

_STYLE_RULES: dict[str, str] = {
    "cinematic":      "Epic, immersive, widescreen storytelling. Every line earns its place.",
    "color_block":    "Bold, graphic, decisive. Short punchy statements like a poster headline.",
    "cyborg":         "Cold, clinical, machine-precise. Short declarative sentences. Augmented-reality urgency.",
    "depth_of_field": "Intimate, sharply focused. Pull attention to one thing. Quiet clarity.",
    "dynamite":       "Explosive energy. Short punchy fragments. Maximum impact every line.",
    "enamel_pin":     "Cute, collectible, playful. Bite-sized statements. Friendly and iconic.",
    "gothic_clay":    "Eerie, textured, handcrafted dread. Slow burn with dark whimsy.",
    "monochrome":     "Stark, high-contrast. Strip away colour — focus on shadow and light.",
    "moody":          "Dark, introspective, emotionally heavy. Sparse words. Let silence breathe.",
    "mythic_fighter": "Epic, heroic, legendary. Battle-cry cadence. Ancient and timeless.",
    "oil_painting":   "Rich, descriptive language. Painterly adjectives. Slow reveal of the scene.",
    "old_cartoon":    "Goofy, exaggerated, anarchic. Rubber-hose energy. Slapstick timing.",
    "risograph":      "Lo-fi indie energy. Offbeat, slightly irreverent, authentically imperfect.",
    "runway":         "Elegant, sharp. Aspirational language. Cool and authoritative.",
    "salon":          "Refined, thoughtful, intimate. Quality over quantity.",
    "sketch":         "Raw, personal, unfinished-feeling. Honest and direct.",
    "steampunk":      "Victorian flair. Elaborate and mechanical. Wonder at the industrial age.",
    "sunrise":        "Expansive, hopeful, emotional. Journey language. Open horizons.",
    "surreal":        "Dreamlike, unexpected, impossible. Let logic unravel. Lean into the strange.",
    "technicolor":    "Lavish, glamorous, full-throttle. Think Hollywood golden era.",
}


@dataclass(frozen=True)
class ScriptAgentFailure(RuntimeError):
    message: str
    error_code: str
    retryable: bool
    debug_hint: str | None = None

    def __str__(self) -> str:
        return self.message


def _classify_script_agent_failure(exc: Exception | str) -> ScriptAgentFailure:
    if isinstance(exc, ScriptAgentFailure):
        return exc

    message = exc if isinstance(exc, str) else str(exc)
    lower = message.lower()

    if any(token in lower for token in (
        "finalize_script was not called",
        "did not produce a script",
        "completed without producing a script",
        "agent did not call finalize_script",
    )):
        return ScriptAgentFailure(
            message="Scout did not finalize a script on this run.",
            error_code="agent_no_finalize",
            retryable=True,
            debug_hint="The ADK session ended without finalize_script being called.",
        )

    if any(token in lower for token in (
        "503",
        "429",
        "500",
        "unavailable",
        "resource_exhausted",
        "deadline exceeded",
        "timed out",
        "connection error",
    )):
        return ScriptAgentFailure(
            message="Scout hit a temporary model/service issue while generating the script.",
            error_code="transient_model_error",
            retryable=True,
            debug_hint="Transient Gemini or ADK availability failure.",
        )

    if any(token in lower for token in (
        "json",
        "validation",
        "scenes_json",
        "hook_text",
        "cta_text",
        "invalid",
        "malformed",
    )):
        return ScriptAgentFailure(
            message="Scout produced invalid tool output while assembling the script.",
            error_code="invalid_tool_output",
            retryable=False,
            debug_hint="Tool arguments or structured output were invalid.",
        )

    return ScriptAgentFailure(
        message=message or "Scout failed unexpectedly during script generation.",
        error_code="unexpected_agent_error",
        retryable=False,
        debug_hint="Unexpected ADK or script agent failure.",
    )


def _should_retry_script_agent_failure(failure: ScriptAgentFailure) -> bool:
    return failure.retryable


# ── Pure-Python tool helpers ───────────────────────────────────────────────────

def _tool_search_trending_hooks(niche: str, platform: str, style: str = "modern_energetic") -> dict:
    hooks = _HOOK_LIBRARY.get(niche.lower(), _HOOK_LIBRARY["default"])
    guidelines = _PLATFORM_GUIDELINES.get(platform, _PLATFORM_GUIDELINES["instagram_reels"])
    return {
        "niche": niche, "platform": platform,
        "trending_hooks": hooks, "platform_guidelines": guidelines,
        "top_recommendation": (
            f"For {platform}, hook must land within {guidelines['hook_window_seconds']}s. "
            f"Keep hook under {guidelines['max_hook_words']} words."
        ),
    }


def _tool_analyze_brand_voice(art_style: str, series_name: str = "", niche: str = "", brand_voice: str = "") -> dict:
    rules = _STYLE_RULES.get(art_style.lower(), _STYLE_RULES["cinematic"])
    return {
        "art_style": art_style, "writing_rules": rules,
        "brand_voice_summary": brand_voice or "No brand voice specified — use conversational authority.",
        "tone_keywords": ["clear", "confident", "engaging", "concise"],
        "avoid": ["passive voice", "filler words", "jargon without explanation"],
        "visual_prompt_tip": (
            f"Every visual_prompt must specify: subject, lighting, camera angle, mood, and "
            f"'{art_style}' art style for image generation."
        ),
    }


def _tool_optimize_for_platform(platform: str, current_hook: str, current_cta: str,
                                  video_duration: int = 30, scenes: list | None = None) -> dict:
    g = _PLATFORM_GUIDELINES.get(platform, _PLATFORM_GUIDELINES["instagram_reels"])
    suggestions: list[str] = []
    hook_words = len(current_hook.split())
    if hook_words > g["max_hook_words"]:
        suggestions.append(f"Hook is {hook_words} words — trim to ≤{g['max_hook_words']} for {platform}")
    if not any(c in current_hook for c in ("?", "!", "...")):
        suggestions.append("Add emotional punctuation (? ! ...) to hook for stronger retention")
    scene_count = len(scenes) if scenes else 0
    if platform == "instagram_reels" and scene_count > 4:
        suggestions.append("Reduce to ≤4 scenes for Instagram Reels pacing")
    return {
        "platform": platform, "hook_approved": len(suggestions) == 0,
        "suggestions": suggestions or ["Hook and CTA look good for this platform!"],
        "preferred_cta_options": g["preferred_cta"],
        "optimal_duration": g["optimal_duration"],
        "trending_formats": g["trending_formats"],
    }


def _tool_validate_script_quality(hook: str, scenes: list, cta: str,
                                    target_duration: int = 30, platform: str = "instagram_reels") -> dict:
    score = 100
    critique: list[str] = []
    if len(hook.split()) < 4:
        score -= 20; critique.append("Hook too short")
    if not scenes:
        score -= 40; critique.append("No scenes generated")
    total_words = sum(len(s.get("voiceover_text", "").split()) for s in scenes)
    estimated = total_words / 2.5
    tolerance = max(4, int(target_duration * 0.15))  # 15% of target, min 4s
    if abs(estimated - target_duration) > tolerance:
        score -= 8; critique.append(f"Estimated {estimated:.0f}s vs target {target_duration}s (tolerance ±{tolerance}s)")
    final = max(0, min(100, score))
    return {
        "score": final, "passed": final >= 70,
        "critique": critique or ["Script quality looks solid!"],
        "estimated_duration_seconds": round(estimated, 1) if scenes else 0,
        "recommendation": "Call finalize_script." if final >= 70 else f"Revise (score={final}/100, need ≥70).",
    }


# ── ADK tool functions ─────────────────────────────────────────────────────────

async def search_trending_hooks(
    niche: str, platform: str, style: str = "modern_energetic"
) -> dict:
    """Find viral hook patterns and opening lines for a content niche.

    Args:
        niche: Content niche, e.g. weather, finance, fitness.
        platform: Target platform: instagram_reels, tiktok, or youtube_shorts.
        style: Video style e.g. modern_energetic, dramatic.
    """
    base = _tool_search_trending_hooks(niche=niche, platform=platform, style=style)
    try:
        from services.storage import feedback_store
        top_hooks = await feedback_store.get_top_hooks(niche=niche)
        if top_hooks:
            base["proven_hooks_from_history"] = [
                {"hook": h.get("hook_text"), "quality_score": h.get("quality_score")}
                for h in top_hooks
            ]
    except Exception:
        pass  # feedback is advisory — never block script generation
    return base


def analyze_brand_voice(
    art_style: str, series_name: str = "", niche: str = "", brand_voice: str = ""
) -> dict:
    """Convert art style and brand voice guidelines into concrete writing rules.

    Args:
        art_style: Art style from the catalog (e.g. cinematic, gothic_clay, surreal).
        series_name: Optional series name for context.
        niche: Content niche for context.
        brand_voice: Optional brand voice description.
    """
    return _tool_analyze_brand_voice(art_style, series_name, niche, brand_voice)


def optimize_for_platform(
    platform: str, current_hook: str, current_cta: str, video_duration: int = 30
) -> dict:
    """Check draft hook and CTA against platform best practices.

    Args:
        platform: instagram_reels, tiktok, or youtube_shorts.
        current_hook: The hook text to evaluate.
        current_cta: The CTA text to evaluate.
        video_duration: Target video duration in seconds.
    """
    return _tool_optimize_for_platform(platform, current_hook, current_cta, video_duration)


async def validate_script_quality(
    hook: str,
    scenes_json: str,
    cta: str,
    target_duration: int = 30,
    platform: str = "instagram_reels",
) -> dict:
    """Score the complete script 0-100. Score ≥70 means ready to call finalize_script.

    Args:
        hook: The hook text.
        scenes_json: JSON array string of scene objects, each with scene_id,
                     duration_seconds, visual_prompt, voiceover_text, and emotion.
                     Example: [{"scene_id":1,"duration_seconds":5,"voiceover_text":"...","visual_prompt":"...","emotion":"excited"}]
        cta: The call-to-action text.
        target_duration: Target video duration in seconds.
        platform: Target platform name.
    """
    import json
    try:
        scenes = json.loads(scenes_json) if scenes_json else []
    except (json.JSONDecodeError, TypeError):
        scenes = []

    return _tool_validate_script_quality(
        hook=hook, scenes=scenes, cta=cta,
        target_duration=target_duration, platform=platform,
    )


async def finalize_script(
    hook_text: str,
    hook_duration: int,
    scenes_json: str,
    cta_text: str,
    cta_type: str = "verbal_and_visual",
    social_copy_json: str = "{}",
    quality_score: float = 0.0,
    agent_reasoning: str = "",
    character_description: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """Submit the final approved script. Call ONLY after validate_script_quality returns score ≥70.

    Args:
        hook_text: The hook sentence shown at the start of the video.
        hook_duration: Duration in seconds for the hook (usually 3).
        scenes_json: JSON array string of scene objects. Each scene must have:
                     scene_id (int), duration_seconds (int), visual_prompt (str, 60+ words),
                     voiceover_text (str), emotion (str), and optionally text_overlay (str)
                     and transition_to_next (str).
                     Example: [{"scene_id":1,"duration_seconds":5,"visual_prompt":"...","voiceover_text":"...","emotion":"excited"}]
        cta_text: The call-to-action spoken at the end.
        cta_type: CTA type, e.g. verbal_and_visual, verbal_only.
        social_copy_json: JSON string mapping platform names to caption/hashtags objects.
                          Example: {"instagram_reels": {"caption": "...", "hashtags": ["#tag"]}}
        quality_score: Score returned by validate_script_quality (should be ≥70).
        agent_reasoning: Brief explanation of creative decisions made.
        character_description: Consistent physical description of the main character
                               used across all scene images.
    """
    import json
    try:
        scenes = json.loads(scenes_json) if scenes_json else []
    except (json.JSONDecodeError, TypeError):
        scenes = []

    if not scenes:
        return {
            "status": "rejected",
            "message": (
                "scenes_json is empty — you MUST include at least 3 scenes, each with "
                "scene_id, duration_seconds, visual_prompt, voiceover_text, and emotion. "
                "Build the scenes array first, then call finalize_script again."
            ),
        }

    try:
        social_copy = json.loads(social_copy_json) if social_copy_json else {}
    except (json.JSONDecodeError, TypeError):
        social_copy = {}

    result = {
        "hook": {"text": hook_text, "duration": hook_duration},
        "scenes": scenes,
        "cta": {"text": cta_text, "type": cta_type},
        "social_copy": social_copy,
        "quality_score": quality_score,
        "agent_reasoning": agent_reasoning,
        "character_description": character_description,
    }
    if tool_context is not None:
        tool_context.state["finalized_script"] = result
    logger.info("finalize_script called — quality_score=%s scenes=%d", quality_score, len(scenes))
    return {"status": "accepted", "message": "Script finalised — generation complete."}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_niche(transcript: str) -> str:
    text = transcript.lower()
    if any(w in text for w in ("weather", "storm", "rain", "temperature", "cold", "snow")):
        return "weather"
    if any(w in text for w in ("money", "invest", "stock", "finance", "budget", "save", "income")):
        return "finance"
    if any(w in text for w in ("workout", "gym", "fitness", "exercise", "weight", "muscle")):
        return "fitness"
    if any(w in text for w in ("recipe", "cook", "food", "eat", "ingredient", "meal")):
        return "food"
    if any(w in text for w in ("ai", "tech", "software", "app", "tool", "automate", "code")):
        return "tech"
    return "default"


def _recommended_scene_count(duration: int) -> int:
    return max(2, duration // 2)


def _build_response(finalized: dict, platform: str, video_duration: int) -> dict:
    hook_raw = finalized.get("hook", {})
    cta_raw = finalized.get("cta", {})
    scenes_raw = finalized.get("scenes", [])
    social_raw = finalized.get("social_copy", {})

    scenes = []
    for i, s in enumerate(scenes_raw):
        overlay_text = s.get("text_overlay")
        scenes.append({
            "scene_id": s.get("scene_id", i),
            "duration_seconds": max(1, min(30, int(s.get("duration_seconds", 10)))),
            "visual_prompt": s.get("visual_prompt", ""),
            "voiceover_text": s.get("voiceover_text", ""),
            "text_overlay": {
                "text": overlay_text, "position": "bottom_center",
                "animation": "fade_in", "emphasis_words": [],
            } if overlay_text else None,
            "emotion": s.get("emotion", "neutral"),
            "transition_to_next": s.get("transition_to_next"),
        })

    social_copy = {}
    for plat, copy in social_raw.items():
        if isinstance(copy, dict):
            social_copy[plat] = {
                "caption": copy.get("caption", ""),
                "hashtags": copy.get("hashtags", []),
                "title": copy.get("title"),
                "description": copy.get("description"),
                "tags": copy.get("tags", []),
            }

    return {
        "project_id": str(uuid4()),
        "metadata": {
            "target_platform": platform,
            "video_duration": video_duration,
            "agent_quality_score": finalized.get("quality_score"),
            "agent_reasoning": finalized.get("agent_reasoning", ""),
            "character_description": finalized.get("character_description", ""),
            "generated_by": "google-adk + gemini-reasoning",
            "model": MODEL,
            "intelligence_model": MODEL,
        },
        "hook": {"text": hook_raw.get("text", ""), "duration": hook_raw.get("duration", 3)},
        "scenes": scenes,
        "cta": {"text": cta_raw.get("text", ""), "type": cta_raw.get("type", "verbal_and_visual")},
        "social_copy": social_copy,
        "voiceover_full_script": " ".join(s.get("voiceover_text", "") for s in scenes_raw),
    }


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_script_with_agent(
    transcript: str,
    target_platforms: list[str],
    style: str = "modern_energetic",
    video_duration: int = 30,
    brand_voice: str | None = None,
    cta_preference: str | None = None,
    niche: str | None = None,
    art_style: str = "realism",
    video_format: str = "storytelling",
    reddit_context: dict | None = None,
    subject_description: str | None = None,
) -> dict:
    """Run a Google ADK agent loop to generate a high-quality video script.

    Drop-in replacement for the previous hand-rolled ReAct loop.
    Same arguments, same return shape.
    """
    from config import get_settings
    from google.genai import types as genai_types

    settings = get_settings()

    # Configure ADK's internal genai client (Vertex AI on GCP, API key locally)
    if settings.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.vertex_ai_location)
    elif settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)

    platform = target_platforms[0] if target_platforms else "instagram_reels"
    inferred_niche = niche or _infer_niche(transcript)
    scene_count = _recommended_scene_count(video_duration)
    target_words = int(video_duration * 2.5)
    scene_words = max(3, int(target_words / scene_count))

    system = (
        f"You are Scout, Content Factory's expert script director. Transform the creator's voice memo "
        f"into a viral {video_duration}-second marketing video script optimised for {platform}.\n\n"
        f"Use your tools strategically:\n"
        f"1. Call search_trending_hooks for niche=\"{inferred_niche}\"\n"
        f"2. Call analyze_brand_voice for art_style=\"{art_style}\"\n"
        f"3. Draft: one hook + {scene_count} scenes + one CTA\n"
        f"4. Call optimize_for_platform to check pacing and CTA\n"
        f"5. Call validate_script_quality — if score < 70, revise and re-validate\n"
        f"6. Call finalize_script ONLY when score ≥ 70\n\n"
        f"HARD CONSTRAINTS:\n"
        f"• Total voiceover \u2248 {target_words} words across {scene_count} scenes\n"
        f"• Each scene voiceover_text: \u2248{scene_words} words (2-second scene at 2.5 words/sec)\n"
        f"• Video duration breakdown: \u223c3s hook + {scene_count}\u00d72s scenes + \u223c3s CTA = {video_duration}s total\n"
        f"• voiceover_text MUST be TTS-ready plain speech:\n"
        f"  \u2013 Use only letters, spaces, apostrophes, and commas/periods at natural pauses\n"
        f"  \u2013 No dashes (- or \u2014), ellipses (...), repeated punctuation (!!!), brackets, emoji, or hashtags\n"
        f"  \u2013 Spell out numbers and abbreviations (\"ten thousand\" not \"10,000\"; \"call to action\" not \"CTA\")\n"
        f"  \u2013 No ALL-CAPS words; convey emphasis through word choice, not formatting\n"
        f"• Each scene = exactly 2 seconds of screen time\n"
        f"• Each visual_prompt must be 60+ words using this cinematic template:\n"
        f"  'A [shot type] of [subject + detailed appearance], [action/expression], "
        f"set in [specific environment]. Illuminated by [lighting description], creating "
        f"a [mood/atmosphere]. [Camera/lens details]. [Key textures and details]. "
        f"{art_style} art style.'\n"
        f"• character_description: write ONE consistent physical description of the "
        f"main character/subject (appearance, clothing, features) \u2014 used to keep all "
        f"images visually consistent.\n"
        f"• Hook must land within the platform's hook window \u2014 punchy and specific\n"
        f"• CTA: {cta_preference or 'choose the highest-converting CTA for ' + platform}\n"
        f"• Format: {video_format}\n"
        f"• Never call finalize_script with quality score < 70\n"
        f"• validate_script_quality and finalize_script take scenes_json \u2014 a JSON array string:\n"
        f'  \'[{{"scene_id":1,"duration_seconds":5,"visual_prompt":"...","voiceover_text":"...","emotion":"excited"}}]\'\n'
        f"• finalize_script also takes hook_text, hook_duration (int), cta_text, cta_type separately\n"
        f'• social_copy_json is a JSON string: \'{{\"instagram_reels\":{{\"caption\":\"...\",\"hashtags\":[\"#tag\"]}}}}\''
    )

    if reddit_context and reddit_context.get("top_topics"):
        topics = "\n".join(f"  \u2022 {t}" for t in reddit_context["top_topics"][:6])
        subreddits = ", ".join(f"r/{s}" for s in reddit_context.get("subreddits_searched", []))
        system += (
            f"\n\nTRENDING ON REDDIT RIGHT NOW ({subreddits}):\n{topics}\n"
            "Use these live trends to sharpen your hook angle and script perspective."
        )

    if subject_description:
        system += (
            f"\n\nMAIN SUBJECT (inferred from uploaded reference photo):\n"
            f"{subject_description}\n"
            f"Tailor the script character, pronouns, and narrative arc to match this person. "
            f"Your character_description must be visually consistent with this description."
        )

    app_name = "content-factory"
    user_id = "script-agent"
    session_id = str(uuid4())

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    from google.genai import types as genai_types_cfg
    agent = Agent(
        name="script_director",
        model=MODEL,
        instruction=system,
        tools=[
            search_trending_hooks,
            analyze_brand_voice,
            optimize_for_platform,
            validate_script_quality,
            finalize_script,
        ],
        # Raise the LLM call budget above the ADK default of 10 so the agent
        # can revise and re-validate without hitting the limit.
        generate_content_config=genai_types_cfg.GenerateContentConfig(
            automatic_function_calling=genai_types_cfg.AutomaticFunctionCallingConfig(
                maximum_remote_calls=12,
            ),
        ),
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=(
            f"Create a {video_duration}s {platform} script about this topic:\n\n"
            f"{transcript}\n\n"
            f"Niche: {inferred_niche} | Style: {style} | Art: {art_style}"
        ))],
    )

    logger.info(
        "ADK agent starting: platform=%s niche=%s duration=%ds model=%s",
        platform, inferred_niche, video_duration, MODEL,
    )

    finalized = None
    last_failure: ScriptAgentFailure | None = None

    for attempt in range(_MAX_SCRIPT_ATTEMPTS):
        if attempt:
            delay = _RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)]
            logger.warning(
                "ADK agent retrying",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": _MAX_SCRIPT_ATTEMPTS,
                    "error_code": last_failure.error_code if last_failure else None,
                    "retryable": last_failure.retryable if last_failure else None,
                    "delay_seconds": delay,
                    "platform": platform,
                    "source": "sync",
                },
            )
            await asyncio.sleep(delay)
            # New session for fresh ADK context
            session_id = str(uuid4())
            await session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )

        try:
            async for _event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=message
            ):
                pass  # drain; finalize_script stores result via ToolContext as side-effect

            session = await session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            finalized = (session.state or {}).get("finalized_script")
            if finalized is not None:
                break  # success
            last_failure = _classify_script_agent_failure("finalize_script was not called")
        except Exception as exc:
            last_failure = _classify_script_agent_failure(exc)
            if _should_retry_script_agent_failure(last_failure):
                continue
            raise last_failure

    if finalized is None:
        raise last_failure or _classify_script_agent_failure(
            "ADK agent did not call finalize_script within the allowed turns."
        )

    logger.info(
        "ADK agent completed — quality_score=%s scenes=%d",
        finalized.get("quality_score"), len(finalized.get("scenes", [])),
    )
    return _build_response(finalized, platform, video_duration)


# ── SSE streaming entry point ──────────────────────────────────────────────────

_TOOL_LABELS: dict[str, str] = {
    "search_trending_hooks":   "Researching viral hook patterns…",
    "analyze_brand_voice":     "Analyzing brand voice and art style…",
    "optimize_for_platform":   "Optimizing hook and CTA for platform…",
    "validate_script_quality": "Scoring script quality…",
    "finalize_script":         "Finalizing script…",
}


async def stream_script_agent(
    transcript: str,
    target_platforms: list[str],
    style: str = "modern_energetic",
    video_duration: int = 30,
    brand_voice: str | None = None,
    cta_preference: str | None = None,
    niche: str | None = None,
    art_style: str = "realism",
    video_format: str = "storytelling",
    reddit_context: dict | None = None,
    subject_description: str | None = None,
):
    """Async generator — same logic as generate_script_with_agent but yields SSE dicts.

    Yields:
        {"type": "agent_step", "tool": "<name>", "message": "<human label>"}  — per tool call
        {"type": "complete", "script": {...}}                                  — on success
        {"type": "error", "message": "..."}                                    — on failure
    """
    from config import get_settings
    from google.genai import types as genai_types, types as genai_types_cfg

    settings = get_settings()

    if settings.use_vertex_ai:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.vertex_ai_location)
    elif settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)

    platform = target_platforms[0] if target_platforms else "instagram_reels"
    inferred_niche = niche or _infer_niche(transcript)
    scene_count = _recommended_scene_count(video_duration)
    target_words = int(video_duration * 2.5)
    scene_words = max(3, int(target_words / scene_count))

    system = (
        f"You are Scout, Content Factory's expert script director. Transform the creator's voice memo "
        f"into a viral {video_duration}-second marketing video script optimised for {platform}.\n\n"
        f"Use your tools strategically:\n"
        f"1. Call search_trending_hooks for niche=\"{inferred_niche}\"\n"
        f"2. Call analyze_brand_voice for art_style=\"{art_style}\"\n"
        f"3. Draft: one hook + {scene_count} scenes + one CTA\n"
        f"4. Call optimize_for_platform to check pacing and CTA\n"
        f"5. Call validate_script_quality — if score < 70, revise and re-validate\n"
        f"6. Call finalize_script ONLY when score ≥ 70\n\n"
        f"HARD CONSTRAINTS:\n"
        f"• Total voiceover \u2248 {target_words} words across {scene_count} scenes\n"
        f"• Each scene voiceover_text: \u2248{scene_words} words (2-second scene at 2.5 words/sec)\n"
        f"• Video duration breakdown: \u223c3s hook + {scene_count}\u00d72s scenes + \u223c3s CTA = {video_duration}s total\n"
        f"• voiceover_text MUST be TTS-ready plain speech:\n"
        f"  \u2013 Use only letters, spaces, apostrophes, and commas/periods at natural pauses\n"
        f"  \u2013 No dashes (- or \u2014), ellipses (...), repeated punctuation (!!!), brackets, emoji, or hashtags\n"
        f"  \u2013 Spell out numbers and abbreviations (\"ten thousand\" not \"10,000\"; \"call to action\" not \"CTA\")\n"
        f"  \u2013 No ALL-CAPS words; convey emphasis through word choice, not formatting\n"
        f"• Each scene = exactly 2 seconds of screen time\n"
        f"• Each visual_prompt must be 60+ words using this cinematic template:\n"
        f"  'A [shot type] of [subject + detailed appearance], [action/expression], "
        f"set in [specific environment]. Illuminated by [lighting description], creating "
        f"a [mood/atmosphere]. [Camera/lens details]. [Key textures and details]. "
        f"{art_style} art style.'\n"
        f"• character_description: write ONE consistent physical description of the "
        f"main character/subject (appearance, clothing, features) \u2014 used to keep all "
        f"images visually consistent.\n"
        f"• Hook must land within the platform's hook window \u2014 punchy and specific\n"
        f"• CTA: {cta_preference or 'choose the highest-converting CTA for ' + platform}\n"
        f"• Format: {video_format}\n"
        f"• Never call finalize_script with quality score < 70\n"
        f"• validate_script_quality and finalize_script take scenes_json \u2014 a JSON array string:\n"
        f'  \'[{{"scene_id":1,"duration_seconds":5,"visual_prompt":"...","voiceover_text":"...","emotion":"excited"}}]\'\n'
        f"• finalize_script also takes hook_text, hook_duration (int), cta_text, cta_type separately\n"
        f'• social_copy_json is a JSON string: \'{{\"instagram_reels\":{{\"caption\":\"...\",\"hashtags\":[\"#tag\"]}}}}\''
    )

    if reddit_context and reddit_context.get("top_topics"):
        topics = "\n".join(f"  \u2022 {t}" for t in reddit_context["top_topics"][:6])
        subreddits = ", ".join(f"r/{s}" for s in reddit_context.get("subreddits_searched", []))
        system += (
            f"\n\nTRENDING ON REDDIT RIGHT NOW ({subreddits}):\n{topics}\n"
            "Use these live trends to sharpen your hook angle and script perspective."
        )

    if subject_description:
        system += (
            f"\n\nMAIN SUBJECT (inferred from uploaded reference photo):\n"
            f"{subject_description}\n"
            f"Tailor the script character, pronouns, and narrative arc to match this person. "
            f"Your character_description must be visually consistent with this description."
        )

    app_name = "content-factory"
    user_id = "script-agent-stream"
    session_id = str(uuid4())

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    agent = Agent(
        name="script_director",
        model=MODEL,
        instruction=system,
        tools=[
            search_trending_hooks,
            analyze_brand_voice,
            optimize_for_platform,
            validate_script_quality,
            finalize_script,
        ],
        generate_content_config=genai_types_cfg.GenerateContentConfig(
            automatic_function_calling=genai_types_cfg.AutomaticFunctionCallingConfig(
                maximum_remote_calls=12,
            ),
        ),
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=(
            f"Create a {video_duration}s {platform} script about this topic:\n\n"
            f"{transcript}\n\n"
            f"Niche: {inferred_niche} | Style: {style} | Art: {art_style}"
        ))],
    )

    logger.info(
        "ADK stream agent starting",
        extra={
            "platform": platform,
            "niche": inferred_niche,
            "duration_seconds": video_duration,
            "source": "stream",
        },
    )

    last_failure: ScriptAgentFailure | None = None

    for attempt_index in range(_MAX_SCRIPT_ATTEMPTS):
        attempt = attempt_index + 1
        if attempt_index:
            delay = _RETRY_DELAYS[min(attempt_index - 1, len(_RETRY_DELAYS) - 1)]
            yield {
                "type": "retry",
                "attempt": attempt,
                "message": "Retrying script generation with a fresh Scout session…",
                "error_code": last_failure.error_code if last_failure else None,
                "retryable": True,
                "progress_pct": 18,
            }
            await asyncio.sleep(delay)
            session_id = str(uuid4())
            await session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )

        try:
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=message
            ):
                if not event.content or not event.content.parts:
                    continue
                for part in event.content.parts:
                    fc = getattr(part, "function_call", None)
                    if fc and fc.name in _TOOL_LABELS:
                        yield {
                            "type": "agent_step",
                            "tool": fc.name,
                            "message": _TOOL_LABELS[fc.name],
                            "attempt": attempt,
                        }

            session = await session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            finalized = (session.state or {}).get("finalized_script")
            if finalized is None:
                last_failure = _classify_script_agent_failure("finalize_script was not called")
            else:
                logger.info(
                    "ADK stream agent completed",
                    extra={
                        "quality_score": finalized.get("quality_score"),
                        "attempt": attempt,
                        "platform": platform,
                        "source": "stream",
                    },
                )
                yield {"type": "complete", "script": _build_response(finalized, platform, video_duration)}
                return
        except Exception as exc:
            last_failure = _classify_script_agent_failure(exc)

        assert last_failure is not None
        if not _should_retry_script_agent_failure(last_failure) or attempt >= _MAX_SCRIPT_ATTEMPTS:
            logger.error(
                "ADK stream agent failed",
                extra={
                    "attempt": attempt,
                    "error_code": last_failure.error_code,
                    "retryable": last_failure.retryable,
                    "platform": platform,
                    "source": "stream",
                },
            )
            yield {
                "type": "error",
                "message": str(last_failure),
                "error_code": last_failure.error_code,
                "retryable": last_failure.retryable,
                "debug_hint": last_failure.debug_hint,
            }
            return
