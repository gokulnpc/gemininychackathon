"""Integration tests for services/gemini/reasoning.py — real Gemini API calls.

Requires: GEMINI_API_KEY in .env (or Vertex AI ADC on GCP).
All tests skip gracefully if credentials are unavailable.

Usage:
    cd backend && .venv/bin/python tests/integration/test_reasoning.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.reasoning import (
    _ART_STYLES,
    auto_configure_series,
    research_hooks,
    score_script,
)

_SAMPLE_TRANSCRIPT = (
    "A 25-year-old named Marcus discovers his reflection doesn't mimic him anymore. "
    "It starts doing things on its own, mouthing words he can't hear. One night it "
    "reaches through the glass. By morning, Marcus is gone — but the reflection stays."
)

_SAMPLE_SCENES = [
    {"scene_id": 1, "duration_seconds": 4, "voiceover_text": "Marcus noticed the reflection first"},
    {"scene_id": 2, "duration_seconds": 5, "voiceover_text": "It mouthed words he could not hear"},
    {"scene_id": 3, "duration_seconds": 4, "voiceover_text": "One night it reached through the glass"},
    {"scene_id": 4, "duration_seconds": 4, "voiceover_text": "By morning Marcus was gone forever"},
]


def _check_credentials() -> bool:
    from config import get_settings
    settings = get_settings()
    return bool(settings.gemini_api_key or settings.use_vertex_ai)


# ── research_hooks ────────────────────────────────────────────────────────────

async def test_real_research_hooks():
    """Real Gemini call — hook research for horror/instagram_reels."""
    if not _check_credentials():
        print("  ⚠ SKIP: GEMINI_API_KEY not set")
        return

    result = await research_hooks("horror", "instagram_reels", style="creepy_dark")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result, "Expected non-empty result"
    assert result.get("scored_by") == "gemini", f"Missing scored_by: {result}"

    hooks = result.get("hooks", [])
    assert isinstance(hooks, list), f"hooks must be a list, got {type(hooks)}"
    assert len(hooks) > 0, "Expected at least one hook"

    for hook in hooks:
        assert "text" in hook, f"Hook missing 'text': {hook}"
        assert hook["text"], "Hook text must not be empty"

    print(f"  ✓ {len(hooks)} hooks generated")
    print(f"\n  {'TYPE':<15} {'HOOK TEXT'}")
    print(f"  {'─'*15} {'─'*50}")
    for h in hooks:
        print(f"  {h.get('type', '?'):<15} {h.get('text', '')[:60]}")


# ── score_script ──────────────────────────────────────────────────────────────

async def test_real_score_script():
    """Real Gemini call — evaluate a sample horror script."""
    if not _check_credentials():
        print("  ⚠ SKIP: GEMINI_API_KEY not set")
        return

    result = await score_script(
        hook="Your reflection just did something you didn't do.",
        scenes=_SAMPLE_SCENES,
        cta="Follow to see what happens next.",
        platform="instagram_reels",
        target_duration=30,
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result, "Expected non-empty result"
    assert result.get("scored_by") == "gemini"

    score = result.get("score")
    assert isinstance(score, (int, float)), f"score must be numeric, got {type(score)}"
    assert 0 <= score <= 100, f"score out of range: {score}"

    passed = result.get("passed")
    assert isinstance(passed, bool), f"passed must be bool, got {type(passed)}"

    print(f"  ✓ script scored {score}/100  passed={passed}")
    print(f"  strength: {result.get('top_strength', '?')}")
    print(f"  weakness: {result.get('top_weakness', '?')}")
    print(f"  recommendation: {result.get('recommendation', '?')}")


# ── auto_configure_series ─────────────────────────────────────────────────────

async def test_real_auto_configure_series():
    """Real Gemini call — auto-generate a series config from the sample transcript."""
    if not _check_credentials():
        print("  ⚠ SKIP: GEMINI_API_KEY not set")
        return

    result = await auto_configure_series(
        transcript=_SAMPLE_TRANSCRIPT,
        target_platforms=["instagram_reels", "tiktok"],
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result, "Expected non-empty result"
    assert result.get("configured_by") == "gemini"

    required_keys = {
        "series_name", "niche", "art_style", "caption_style",
        "background_music", "voice_id", "voice_name",
        "video_duration", "video_format", "target_platforms",
    }
    missing = required_keys - result.keys()
    assert not missing, f"Missing required keys: {missing}"

    assert result["art_style"] in _ART_STYLES, (
        f"art_style '{result['art_style']}' not in valid list: {_ART_STYLES}"
    )
    assert isinstance(result.get("music_volume"), (int, float)), "music_volume must be numeric"
    assert 0.05 <= result["music_volume"] <= 0.50, f"music_volume out of range: {result['music_volume']}"

    print(f"  ✓ series configured: '{result['series_name']}'")
    print(f"  niche:         {result.get('niche')}")
    print(f"  art_style:     {result.get('art_style')}")
    print(f"  caption_style: {result.get('caption_style')}")
    print(f"  voice:         {result.get('voice_name')}")
    print(f"  duration:      {result.get('video_duration')}")
    print(f"  format:        {result.get('video_format')}")
    print(f"  music:         {result.get('background_music')} @ {result.get('music_volume')}")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    tests = [
        test_real_research_hooks,
        test_real_score_script,
        test_real_auto_configure_series,
    ]
    passed = failed = 0

    for fn in tests:
        print(f"\n[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
