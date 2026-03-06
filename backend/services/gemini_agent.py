"""Gemini Agent — agentic script generation for Content Factory.

Replaces claude_agent.py. Identical public interface.

Gemini 3 Pro acts as the creative director, orchestrating the same 5-tool
ReAct loop using Gemini native function calling:
  - search_trending_hooks   → Gemini Reasoning researches viral hook patterns
  - analyze_brand_voice     → style rules from art style + brand guidelines
  - optimize_for_platform   → pacing/CTA check against platform best practices
  - validate_script_quality → Gemini Reasoning independently scores the draft
  - finalize_script         → output sink that ends the agent loop
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

from services import gemini_reasoning
from services.retry import call_with_retry

logger = logging.getLogger(__name__)

# Upgrade to gemini-3.0-pro when GA; gemini-2.5-pro is current best
MODEL = "gemini-2.5-pro"
MAX_TURNS = 14

# ── Reuse all pure-Python tool handlers from the original agent ───────────────

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
            f"'{art_style}' art style for Veo video generation."
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
    if not any(c in hook for c in ("?", "!", "...")):
        score -= 8; critique.append("Hook lacks emotional punctuation")
    if not scenes:
        score -= 40; critique.append("No scenes generated")
    total_words = sum(len(s.get("voiceover_text", "").split()) for s in scenes)
    estimated = total_words / 2.5
    if abs(estimated - target_duration) > 10:
        score -= 8; critique.append(f"Estimated {estimated:.0f}s vs target {target_duration}s")
    final = max(0, min(100, score))
    return {
        "score": final, "passed": final >= 70,
        "critique": critique or ["Script quality looks solid!"],
        "estimated_duration_seconds": round(estimated, 1) if scenes else 0,
        "recommendation": "Call finalize_script." if final >= 70 else f"Revise (score={final}/100, need ≥70).",
    }


# ── Gemini function declarations ──────────────────────────────────────────────

_TOOL_DECLARATIONS = [
    {
        "name": "search_trending_hooks",
        "description": "Find viral hook patterns and opening lines for a content niche.",
        "parameters": {
            "type": "object",
            "properties": {
                "niche": {"type": "string", "description": "Content niche, e.g. weather, finance, fitness"},
                "platform": {"type": "string", "enum": ["instagram_reels", "tiktok", "youtube_shorts"]},
                "style": {"type": "string", "description": "Video style e.g. modern_energetic, dramatic"},
            },
            "required": ["niche", "platform"],
        },
    },
    {
        "name": "analyze_brand_voice",
        "description": "Convert art style and brand voice guidelines into concrete writing rules.",
        "parameters": {
            "type": "object",
            "properties": {
                "art_style": {"type": "string", "description": "realism, ghibli, comic, creepy_comic, painting, polaroid, disney"},
                "series_name": {"type": "string"},
                "niche": {"type": "string"},
                "brand_voice": {"type": "string"},
            },
            "required": ["art_style"],
        },
    },
    {
        "name": "optimize_for_platform",
        "description": "Check draft hook and CTA against platform best practices.",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["instagram_reels", "tiktok", "youtube_shorts"]},
                "current_hook": {"type": "string"},
                "current_cta": {"type": "string"},
                "video_duration": {"type": "integer"},
                "scenes": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["platform", "current_hook", "current_cta"],
        },
    },
    {
        "name": "validate_script_quality",
        "description": "Score the complete script 0-100. Score ≥70 → call finalize_script.",
        "parameters": {
            "type": "object",
            "properties": {
                "hook": {"type": "string"},
                "scenes": {"type": "array", "items": {"type": "object"}},
                "cta": {"type": "string"},
                "target_duration": {"type": "integer"},
                "platform": {"type": "string"},
            },
            "required": ["hook", "scenes", "cta"],
        },
    },
    {
        "name": "finalize_script",
        "description": "Submit the final approved script. Call ONLY after validate_script_quality returns score ≥70.",
        "parameters": {
            "type": "object",
            "properties": {
                "hook": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "duration": {"type": "integer"}},
                    "required": ["text"],
                },
                "scenes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_id": {"type": "integer"},
                            "duration_seconds": {"type": "integer"},
                            "visual_prompt": {"type": "string"},
                            "voiceover_text": {"type": "string"},
                            "emotion": {"type": "string"},
                            "text_overlay": {"type": "string"},
                            "transition_to_next": {"type": "string"},
                        },
                        "required": ["scene_id", "duration_seconds", "visual_prompt", "voiceover_text", "emotion"],
                    },
                },
                "cta": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "type": {"type": "string"}},
                    "required": ["text"],
                },
                "social_copy": {"type": "object"},
                "quality_score": {"type": "number"},
                "agent_reasoning": {"type": "string"},
                "character_description": {
                    "type": "string",
                    "description": "Consistent physical description of the main character/subject used across all scene images.",
                },
            },
            "required": ["hook", "scenes", "cta"],
        },
    },
]


# ── Tool dispatcher ────────────────────────────────────────────────────────────

async def _dispatch(tool_name: str, inputs: dict) -> dict:
    if tool_name == "search_trending_hooks":
        niche = inputs.get("niche", "default")
        platform = inputs.get("platform", "instagram_reels")

        # Tier 1: Gemini Reasoning for deep hook analysis
        gemini_result = await gemini_reasoning.research_hooks(
            niche=niche,
            platform=platform,
            style=inputs.get("style", "modern_energetic"),
        )
        if gemini_result and gemini_result.get("hooks"):
            guidelines = _PLATFORM_GUIDELINES.get(platform, _PLATFORM_GUIDELINES["instagram_reels"])
            result = {**gemini_result, "platform_guidelines": guidelines}
        else:
            # Tier 2: curated library fallback
            result = _tool_search_trending_hooks(**inputs)

        # Tier 3: inject high-scoring hooks from Firestore feedback (non-blocking)
        try:
            from services import feedback_store
            top_hooks = await feedback_store.get_top_hooks(niche=niche)
            if top_hooks:
                result["proven_hooks_from_history"] = [
                    {"hook": h.get("hook_text"), "quality_score": h.get("quality_score")}
                    for h in top_hooks
                ]
        except Exception:
            pass  # feedback is advisory — never block script generation

        return result

    if tool_name == "analyze_brand_voice":
        return _tool_analyze_brand_voice(**inputs)

    if tool_name == "optimize_for_platform":
        return _tool_optimize_for_platform(**inputs)

    if tool_name == "validate_script_quality":
        # Gemini Reasoning acts as independent critic (not the script author self-grading)
        gemini_result = await gemini_reasoning.score_script(
            hook=inputs.get("hook", ""),
            scenes=inputs.get("scenes", []),
            cta=inputs.get("cta", ""),
            platform=inputs.get("platform", "instagram_reels"),
            target_duration=inputs.get("target_duration", 30),
        )
        if gemini_result and "score" in gemini_result:
            score = gemini_result.get("score", 70)
            passed = gemini_result.get("passed", score >= 70)
            return {
                "score": score, "passed": passed,
                "critique": [gemini_result.get("top_weakness", ""), gemini_result.get("reasoning", "")[:200]],
                "estimated_duration_seconds": 0,
                "recommendation": (
                    "Call finalize_script — quality validated by Gemini."
                    if passed
                    else f"Revise: {gemini_result.get('top_weakness', 'improve quality')} (score={score}/100)"
                ),
                "top_strength": gemini_result.get("top_strength", ""),
                "scored_by": "gemini",
            }
        return _tool_validate_script_quality(**inputs)

    return {"error": f"Unknown tool: {tool_name}"}


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
    # One new image every 2 seconds — drives the scene count for the pipeline
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
            "generated_by": "gemini-agent + gemini-reasoning",
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
) -> dict:
    """Run a Gemini agent loop to generate a high-quality video script.

    Drop-in replacement for claude_agent.generate_script_with_agent().
    Same arguments, same return shape.
    """
    from google.genai import types

    from services.gemini_client import get_client

    client = get_client()

    platform = target_platforms[0] if target_platforms else "instagram_reels"
    inferred_niche = niche or _infer_niche(transcript)
    scene_count = _recommended_scene_count(video_duration)
    target_words = int(video_duration * 2.5)

    system = (
        f"You are Content Factory's expert script director. Transform the creator's voice memo "
        f"into a viral {video_duration}-second marketing video script optimised for {platform}.\n\n"
        f"Use your tools strategically:\n"
        f"1. Call search_trending_hooks for niche=\"{inferred_niche}\"\n"
        f"2. Call analyze_brand_voice for art_style=\"{art_style}\"\n"
        f"3. Draft: one hook + {scene_count} scenes + one CTA\n"
        f"4. Call optimize_for_platform to check pacing and CTA\n"
        f"5. Call validate_script_quality — if score < 70, revise and re-validate\n"
        f"6. Call finalize_script ONLY when score ≥ 70\n\n"
        f"HARD CONSTRAINTS:\n"
        f"• Total voiceover ≈ {target_words} words across {scene_count} scenes\n"
        f"• Each scene = exactly 2 seconds of screen time\n"
        f"• Each visual_prompt must be 60+ words using this cinematic template:\n"
        f"  'A [shot type] of [subject + detailed appearance], [action/expression], "
        f"set in [specific environment]. Illuminated by [lighting description], creating "
        f"a [mood/atmosphere]. [Camera/lens details]. [Key textures and details]. "
        f"{art_style} art style.'\n"
        f"• character_description: write ONE consistent physical description of the "
        f"main character/subject (appearance, clothing, features) — used to keep all "
        f"images visually consistent.\n"
        f"• Hook must land within the platform's hook window — punchy and specific\n"
        f"• CTA: {cta_preference or 'choose the highest-converting CTA for ' + platform}\n"
        f"• Format: {video_format}\n"
        f"• Never call finalize_script with quality score < 70"
    )

    if reddit_context and reddit_context.get("top_topics"):
        topics = "\n".join(f"  • {t}" for t in reddit_context["top_topics"][:6])
        subreddits = ", ".join(f"r/{s}" for s in reddit_context.get("subreddits_searched", []))
        system += (
            f"\n\nTRENDING ON REDDIT RIGHT NOW ({subreddits}):\n{topics}\n"
            "Use these live trends to sharpen your hook angle and script perspective."
        )

    tool = types.Tool(function_declarations=_TOOL_DECLARATIONS)
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[tool],
    )

    # Start conversation
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=(
                f"Create a {video_duration}s {platform} script about this topic:\n\n"
                f"{transcript}\n\n"
                f"Niche: {inferred_niche} | Style: {style} | Art: {art_style}"
            ))],
        )
    ]

    finalized: dict | None = None
    turns = 0

    logger.info(
        "Gemini agent starting: platform=%s niche=%s duration=%ds model=%s",
        platform, inferred_niche, video_duration, MODEL,
    )

    while turns < MAX_TURNS and finalized is None:
        response = await call_with_retry(
            client.models.generate_content,
            model=MODEL,
            contents=contents,
            config=config,
        )
        turns += 1

        candidate = response.candidates[0]
        contents.append(candidate.content)  # add model turn to history

        # Count function calls in this turn
        fc_parts = [p for p in candidate.content.parts if hasattr(p, "function_call") and p.function_call and p.function_call.name]
        logger.info("Gemini turn %d/%d: %d function call(s)", turns, MAX_TURNS, len(fc_parts))

        if not fc_parts:
            logger.warning("Gemini stopped without calling finalize_script")
            break

        # Execute all function calls and collect results
        result_parts = []
        for part in fc_parts:
            fc = part.function_call
            tool_name = fc.name
            tool_inputs = dict(fc.args) if fc.args else {}

            logger.info("Gemini → tool: %s  inputs: %s", tool_name, str(tool_inputs)[:160])

            if tool_name == "finalize_script":
                finalized = tool_inputs
                result = {"status": "accepted", "message": "Script finalised."}
            else:
                result = await _dispatch(tool_name, tool_inputs)

            result_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": result},
                    )
                )
            )

        contents.append(types.Content(role="user", parts=result_parts))

    if finalized is None:
        raise RuntimeError(
            f"Gemini agent did not call finalize_script within {MAX_TURNS} turns. "
            "Check GEMINI_API_KEY and model availability."
        )

    logger.info("Gemini agent completed in %d turns — quality_score=%s", turns, finalized.get("quality_score"))
    return _build_response(finalized, platform, video_duration)
