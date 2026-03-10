"""Unit tests for services/gemini/reasoning.py — mocked paths only.

No real GCP/Gemini calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_reasoning.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.reasoning import (
    _ART_STYLES,
    _analyze_content,
    _commit_series_config,
    _extract_json,
    _profile_audience,
    _select_creative_style,
    _select_production_config,
    auto_configure_series,
    research_hooks,
    score_script,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_response(text: str) -> MagicMock:
    """Build a mock Gemini response object with .text set."""
    resp = MagicMock()
    resp.text = text
    return resp


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    return client, _make_response(response_text)


# ── _extract_json — pure function ─────────────────────────────────────────────

def test_extract_json_simple_object():
    result = _extract_json('{"key": "value"}')
    assert result == {"key": "value"}
    print("  ✓ simple JSON object extracted")


def test_extract_json_embedded_in_prose():
    text = 'Here is my analysis:\n{"score": 85, "passed": true}\nThat is all.'
    result = _extract_json(text)
    assert result == {"score": 85, "passed": True}
    print("  ✓ JSON extracted from surrounding prose")


def test_extract_json_empty_object():
    result = _extract_json("{}")
    assert result == {}
    print("  ✓ empty {} returns empty dict")


def test_extract_json_no_json_returns_none():
    result = _extract_json("No JSON here at all.")
    assert result is None
    print("  ✓ no JSON → None")


def test_extract_json_malformed_json_returns_none():
    result = _extract_json('{"unclosed": "object"')
    assert result is None
    print("  ✓ malformed JSON → None")


def test_extract_json_array_not_object_returns_none():
    # The regex looks for {} not [], so arrays return None
    result = _extract_json('[1, 2, 3]')
    assert result is None
    print("  ✓ JSON array (not object) → None")


def test_extract_json_escaped_characters():
    result = _extract_json('{"text": "line1\\nline2", "quote": "say \\"hi\\""}')
    assert result == {"text": "line1\nline2", "quote": 'say "hi"'}
    print("  ✓ escaped characters parsed correctly")


def test_extract_json_nested_object():
    text = '{"hooks": [{"text": "hook1", "type": "mystery"}], "count": 1}'
    result = _extract_json(text)
    assert result["hooks"][0]["text"] == "hook1"
    assert result["count"] == 1
    print("  ✓ nested objects/arrays parsed correctly")


def test_extract_json_multiple_objects_greedy_behavior():
    """With greedy .*  the regex captures from first { to last }.
    Documents current behavior: two separate JSON objects in one response."""
    # Greedy match from first { to last } — may capture both and produce invalid JSON
    # or may successfully parse the combined span depending on structure
    text = '{"a": 1} and then {"b": 2}'
    result = _extract_json(text)
    # Current behavior: greedy capture includes everything up to last }
    # '{"a": 1} and then {"b": 2}' → '{"a": 1} and then {"b": 2}' → JSONDecodeError → None
    # OR the regex may match only the first {...}. Either way, document it.
    # The important assertion: it does NOT raise an exception.
    assert result is None or isinstance(result, dict)
    print(f"  ✓ multiple JSON objects: greedy behavior = {result!r} (no crash)")


# ── research_hooks — mocked ───────────────────────────────────────────────────

async def test_research_hooks_success():
    """Valid JSON response → dict with scored_by injected."""
    payload = {
        "reasoning": "step by step",
        "hooks": [{"text": "hook1", "type": "mystery", "why_it_works": "curiosity"}],
        "platform_insight": "reels users swipe fast",
        "recommended_hook_index": 0,
    }
    mock_resp = _make_response(json.dumps(payload))

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await research_hooks("horror", "instagram_reels")

    assert result["scored_by"] == "gemini"
    assert len(result["hooks"]) == 1
    assert result["hooks"][0]["text"] == "hook1"
    print("  ✓ valid JSON response → dict with scored_by=gemini")


async def test_research_hooks_no_client_returns_empty():
    """No API key (_get_client returns None) → {}."""
    with patch("services.gemini.reasoning._get_client", return_value=None):
        result = await research_hooks("horror", "instagram_reels")
    assert result == {}
    print("  ✓ no client → {}")


async def test_research_hooks_non_json_response_returns_fallback():
    """Non-JSON Gemini text → fallback dict with empty hooks."""
    mock_resp = _make_response("Sorry, I cannot analyze that topic.")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await research_hooks("finance", "tiktok")

    assert result["hooks"] == []
    assert result["scored_by"] == "gemini"
    assert "cannot analyze" in result["reasoning"]
    print("  ✓ non-JSON response → fallback {hooks: [], scored_by: gemini}")


async def test_research_hooks_api_error_returns_empty():
    """API error (e.g. quota exceeded) → {}."""
    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry",
               new=AsyncMock(side_effect=RuntimeError("503 Service Unavailable"))):
        result = await research_hooks("fitness", "youtube_shorts")

    assert result == {}
    print("  ✓ API error → {}")


async def test_research_hooks_style_param_included_in_prompt():
    """Custom style is included in the prompt sent to Gemini."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await research_hooks("horror", "tiktok", style="creepy_dark")

    assert "creepy_dark" in captured["contents"]
    print("  ✓ style param forwarded to Gemini prompt")


# ── score_script — mocked ────────────────────────────────────────────────────

async def test_score_script_success():
    """Valid JSON → dict with scored_by injected."""
    payload = {
        "score": 82,
        "hook_score": 25,
        "story_score": 35,
        "cta_score": 16,
        "pacing_score": 6,
        "passed": True,
        "reasoning": "Great hook, solid story arc",
        "top_strength": "hook",
        "top_weakness": "cta",
        "recommendation": "Call finalize_script",
    }
    mock_resp = _make_response(json.dumps(payload))

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await score_script(
            hook="Did you know giraffes sleep standing up?",
            scenes=[{"scene_id": 1, "duration_seconds": 5, "voiceover_text": "In the wild..."}],
            cta="Follow for more",
        )

    assert result["score"] == 82
    assert result["passed"] is True
    assert result["scored_by"] == "gemini"
    print("  ✓ valid JSON → dict with scored_by=gemini")


async def test_score_script_no_client_returns_empty():
    with patch("services.gemini.reasoning._get_client", return_value=None):
        result = await score_script(hook="h", scenes=[], cta="cta")
    assert result == {}
    print("  ✓ no client → {}")


async def test_score_script_non_json_returns_fallback():
    """Non-JSON response → fallback with score=70, passed=True."""
    mock_resp = _make_response("This script looks okay to me.")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await score_script(hook="h", scenes=[], cta="cta")

    assert result["score"] == 70
    assert result["passed"] is True
    assert result["scored_by"] == "gemini"
    print("  ✓ non-JSON → fallback {score: 70, passed: True}")


async def test_score_script_api_error_returns_empty():
    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry",
               new=AsyncMock(side_effect=RuntimeError("429 quota"))):
        result = await score_script(hook="h", scenes=[], cta="cta")
    assert result == {}
    print("  ✓ API error → {}")


async def test_score_script_scenes_formatted_in_prompt():
    """Each scene's voiceover_text and duration appear in the prompt."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    scenes = [
        {"scene_id": 1, "duration_seconds": 4, "voiceover_text": "The giraffe walked slowly"},
        {"scene_id": 2, "duration_seconds": 6, "voiceover_text": "And then it ran"},
    ]

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await score_script(hook="h", scenes=scenes, cta="cta", target_duration=30)

    prompt = captured["contents"]
    assert "The giraffe walked slowly" in prompt
    assert "And then it ran" in prompt
    assert "30" in prompt  # target_duration mentioned
    print("  ✓ scenes and target_duration included in prompt")


async def test_score_script_target_duration_affects_word_hint():
    """target_duration * 2.5 appears as expected word count in prompt."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await score_script(hook="h", scenes=[], cta="cta", target_duration=40)

    # 40 * 2.5 = 100 words expected in prompt
    assert "100" in captured["contents"]
    print("  ✓ target_duration=40 → word hint '100' in prompt")


# ── auto_configure_series — mocked ───────────────────────────────────────────

_FAKE_CONFIG = {
    "series_name": "Fear Factory",
    "niche": "horror",
    "art_style": "creepy_comic",
    "caption_style": "beast",
    "background_music": "quiet_before_storm",
    "music_volume": 0.15,
    "voice_id": "pNInz6obpgDQGcFmaJgB",
    "voice_name": "Adam",
    "video_duration": "30-40",
    "video_format": "storytelling",
    "target_platforms": ["instagram_reels", "tiktok"],
    "reasoning": "Horror niche benefits from dramatic art style...",
}


async def test_auto_configure_series_success():
    mock_resp = _make_response(json.dumps(_FAKE_CONFIG))

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await auto_configure_series("A horror story about haunted mirrors")

    assert result["configured_by"] == "gemini"
    assert result["series_name"] == "Fear Factory"
    assert result["art_style"] in _ART_STYLES
    print("  ✓ valid JSON → configured_by=gemini injected")


async def test_auto_configure_series_no_client_returns_empty():
    with patch("services.gemini.reasoning._get_client", return_value=None):
        result = await auto_configure_series("some transcript")
    assert result == {}
    print("  ✓ no client → {}")


async def test_auto_configure_series_reddit_context_injected():
    """reddit_context top_topics appear in the prompt."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    reddit_ctx = {
        "top_topics": ["haunted houses", "ghost sightings"],
        "subreddits_searched": ["horror", "paranormal"],
    }

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await auto_configure_series("transcript", reddit_context=reddit_ctx)

    assert "haunted houses" in captured["contents"]
    assert "ghost sightings" in captured["contents"]
    print("  ✓ reddit_context top_topics injected into prompt")


async def test_auto_configure_series_analytics_context_injected():
    """analytics_context art_style_performance appears in the prompt."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    analytics_ctx = {
        "art_style_performance": [
            {"art_style": "ghibli", "avg_quality": 91, "runs": 5},
            {"art_style": "comic", "avg_quality": 78, "runs": 3},
        ],
        "top_niches": [{"niche": "horror", "avg_quality": 88, "runs": 4}],
        "total_runs": 12,
    }

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await auto_configure_series("transcript", analytics_context=analytics_ctx)

    assert "ghibli" in captured["contents"]
    assert "91" in captured["contents"]
    print("  ✓ analytics_context injected into prompt")


async def test_auto_configure_series_no_contexts_clean_prompt():
    """No reddit/analytics context → neither section appears in prompt."""
    captured = {}

    async def fake_retry(fn, **kwargs):
        captured["contents"] = kwargs.get("contents", "")
        return _make_response("{}")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", side_effect=fake_retry):
        await auto_configure_series("plain transcript")

    assert "REDDIT" not in captured["contents"]
    assert "DATABRICKS" not in captured["contents"]
    print("  ✓ no contexts → prompt has no REDDIT/DATABRICKS sections")


async def test_auto_configure_series_non_json_returns_empty():
    mock_resp = _make_response("I cannot configure a series for that.")

    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await auto_configure_series("transcript")

    assert result == {}
    print("  ✓ non-JSON response → {}")


async def test_auto_configure_series_api_error_returns_empty():
    with patch("services.gemini.reasoning._get_client", return_value=MagicMock()), \
         patch("services.gemini.reasoning.call_with_retry",
               new=AsyncMock(side_effect=RuntimeError("503"))):
        result = await auto_configure_series("transcript")
    assert result == {}
    print("  ✓ API error → {}")


# ── auto_configure_series_adk — mocked ADK ───────────────────────────────────

async def test_auto_configure_series_adk_falls_back_on_runner_error():
    """If ADK Runner raises, fall back to auto_configure_series."""
    from unittest.mock import AsyncMock as AM

    mock_runner_instance = MagicMock()
    mock_runner_instance.run_async = MagicMock(side_effect=RuntimeError("ADK unavailable"))

    mock_runner_cls = MagicMock(return_value=mock_runner_instance)
    mock_agent_cls = MagicMock()
    mock_session_svc = MagicMock()
    mock_session_svc.create_session = AM(return_value=None)

    fake_adk_modules = {
        "google.adk": MagicMock(),
        "google.adk.agents": MagicMock(Agent=mock_agent_cls),
        "google.adk.runners": MagicMock(Runner=mock_runner_cls),
        "google.adk.sessions": MagicMock(InMemorySessionService=MagicMock(return_value=mock_session_svc)),
        "google.adk.tools": MagicMock(ToolContext=MagicMock()),
    }

    fallback_result = {"configured_by": "gemini", "series_name": "Fallback Series"}

    with patch.dict("sys.modules", fake_adk_modules), \
         patch("services.gemini.reasoning.auto_configure_series",
               new=AM(return_value=fallback_result)), \
         patch("config.get_settings", return_value=SimpleNamespace(
             use_vertex_ai=False, gemini_api_key="fake", vertex_ai_location="us-central1"
         )):
        from services.gemini.reasoning import auto_configure_series_adk
        result = await auto_configure_series_adk("A transcript about horror")

    assert result["configured_by"] == "gemini"
    assert result["series_name"] == "Fallback Series"
    print("  ✓ ADK Runner error → fallback to auto_configure_series()")


async def test_auto_configure_series_adk_missing_session_config_falls_back():
    """If _commit_series_config not called (session.state empty), fall back."""
    from unittest.mock import AsyncMock as AM

    async def empty_event_stream(*args, **kwargs):
        return
        yield  # make it an async generator

    mock_runner_instance = MagicMock()
    mock_runner_instance.run_async = empty_event_stream

    mock_session = MagicMock()
    mock_session.state = {}  # no series_config

    mock_session_svc = MagicMock()
    mock_session_svc.create_session = AM(return_value=None)
    mock_session_svc.get_session = AM(return_value=mock_session)

    fake_adk_modules = {
        "google.adk": MagicMock(),
        "google.adk.agents": MagicMock(Agent=MagicMock()),
        "google.adk.runners": MagicMock(Runner=MagicMock(return_value=mock_runner_instance)),
        "google.adk.sessions": MagicMock(InMemorySessionService=MagicMock(return_value=mock_session_svc)),
        "google.adk.tools": MagicMock(ToolContext=MagicMock()),
    }

    fallback_result = {"configured_by": "gemini", "series_name": "Fallback"}

    with patch.dict("sys.modules", fake_adk_modules), \
         patch("services.gemini.reasoning.auto_configure_series",
               new=AM(return_value=fallback_result)), \
         patch("config.get_settings", return_value=SimpleNamespace(
             use_vertex_ai=False, gemini_api_key="fake", vertex_ai_location="us-central1"
         )):
        from services.gemini.reasoning import auto_configure_series_adk
        result = await auto_configure_series_adk("transcript")

    assert result["configured_by"] == "gemini"
    print("  ✓ empty session state → fallback to auto_configure_series()")


# ── Sub-agent tool functions — pure ──────────────────────────────────────────

def test_analyze_content_returns_expected_keys():
    result = _analyze_content("Horror story about mirrors", "instagram_reels, tiktok")
    assert "transcript_length" in result
    assert "platforms" in result
    assert "instruction" in result
    assert result["transcript_length"] == len("Horror story about mirrors")
    print("  ✓ _analyze_content returns expected keys")


def test_profile_audience_platform_behaviors():
    for platform in ["instagram_reels", "tiktok", "youtube_shorts"]:
        result = _profile_audience("horror", platform)
        assert "platform_behavior" in result
        assert result["platform"] == platform
        assert result["platform_behavior"]  # non-empty
    print("  ✓ _profile_audience handles all 3 platforms")


def test_profile_audience_unknown_platform_defaults():
    result = _profile_audience("horror", "unknown_platform")
    # Should fall back to instagram_reels behavior (dict.get default)
    assert "platform_behavior" in result
    assert result["platform_behavior"]
    print("  ✓ _profile_audience unknown platform → fallback behavior")


def test_select_creative_style_returns_expected_structure():
    result = _select_creative_style("horror", "dramatic")
    assert result["niche"] == "horror"
    assert result["emotional_tone"] == "dramatic"
    assert "No historical data" in result["analytics_hint"]
    assert len(result["available_art_styles"]) > 0
    print("  ✓ _select_creative_style returns correct structure")


def test_select_creative_style_analytics_hint_forwarded():
    result = _select_creative_style("fitness", "exciting", analytics_hint="ghibli scores 91/100")
    assert "ghibli scores 91/100" in result["analytics_hint"]
    print("  ✓ analytics_hint forwarded to _select_creative_style")


def test_select_production_config_returns_expected_structure():
    result = _select_production_config("instagram_reels", "exciting")
    assert result["platform"] == "instagram_reels"
    assert "15-30" in result["duration_options"]
    assert "storytelling" in result["format_options"]
    assert len(result["available_voices"]) == 5
    print("  ✓ _select_production_config returns all options")


async def test_commit_series_config_builds_correct_dict():
    result = await _commit_series_config(
        series_name="Fear Factory",
        niche="horror",
        art_style="creepy_comic",
        caption_style="beast",
        background_music="quiet_before_storm",
        music_volume=0.15,
        voice_id="pNInz6obpgDQGcFmaJgB",
        voice_name="Adam",
        video_duration="30-40",
        video_format="storytelling",
        target_platforms_json='["instagram_reels", "tiktok"]',
        reasoning="Horror vibes require dark art",
    )
    assert result == {"status": "accepted", "message": "Series configuration committed."}
    print("  ✓ _commit_series_config returns accepted status")


async def test_commit_series_config_writes_to_tool_context_state():
    ctx = SimpleNamespace(state={})
    await _commit_series_config(
        series_name="Test",
        niche="horror",
        art_style="comic",
        caption_style="beast",
        background_music="none",
        music_volume=0.2,
        voice_id="TxGEqnHWrfWFTfGW9XjX",
        voice_name="Josh",
        video_duration="15-30",
        video_format="storytelling",
        target_platforms_json='["tiktok"]',
        reasoning="test",
        tool_context=ctx,
    )
    assert "series_config" in ctx.state
    cfg = ctx.state["series_config"]
    assert cfg["series_name"] == "Test"
    assert cfg["configured_by"] == "google-adk"
    assert cfg["target_platforms"] == ["tiktok"]
    print("  ✓ _commit_series_config writes config to tool_context.state")


async def test_commit_series_config_malformed_json_defaults_to_instagram():
    ctx = SimpleNamespace(state={})
    await _commit_series_config(
        series_name="X",
        niche="n",
        art_style="comic",
        caption_style="beast",
        background_music="none",
        music_volume=0.2,
        voice_id="id",
        voice_name="Josh",
        video_duration="15-30",
        video_format="storytelling",
        target_platforms_json="NOT_VALID_JSON",
        reasoning="r",
        tool_context=ctx,
    )
    assert ctx.state["series_config"]["target_platforms"] == ["instagram_reels"]
    print("  ✓ malformed target_platforms_json → defaults to [instagram_reels]")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_extract_json_simple_object,
        test_extract_json_embedded_in_prose,
        test_extract_json_empty_object,
        test_extract_json_no_json_returns_none,
        test_extract_json_malformed_json_returns_none,
        test_extract_json_array_not_object_returns_none,
        test_extract_json_escaped_characters,
        test_extract_json_nested_object,
        test_extract_json_multiple_objects_greedy_behavior,
        test_analyze_content_returns_expected_keys,
        test_profile_audience_platform_behaviors,
        test_profile_audience_unknown_platform_defaults,
        test_select_creative_style_returns_expected_structure,
        test_select_creative_style_analytics_hint_forwarded,
        test_select_production_config_returns_expected_structure,
    ]

    async_tests = [
        test_research_hooks_success,
        test_research_hooks_no_client_returns_empty,
        test_research_hooks_non_json_response_returns_fallback,
        test_research_hooks_api_error_returns_empty,
        test_research_hooks_style_param_included_in_prompt,
        test_score_script_success,
        test_score_script_no_client_returns_empty,
        test_score_script_non_json_returns_fallback,
        test_score_script_api_error_returns_empty,
        test_score_script_scenes_formatted_in_prompt,
        test_score_script_target_duration_affects_word_hint,
        test_auto_configure_series_success,
        test_auto_configure_series_no_client_returns_empty,
        test_auto_configure_series_reddit_context_injected,
        test_auto_configure_series_analytics_context_injected,
        test_auto_configure_series_no_contexts_clean_prompt,
        test_auto_configure_series_non_json_returns_empty,
        test_auto_configure_series_api_error_returns_empty,
        test_auto_configure_series_adk_falls_back_on_runner_error,
        test_auto_configure_series_adk_missing_session_config_falls_back,
        test_commit_series_config_builds_correct_dict,
        test_commit_series_config_writes_to_tool_context_state,
        test_commit_series_config_malformed_json_defaults_to_instagram,
    ]

    passed = failed = 0

    for fn in sync_tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    for fn in async_tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    total = passed + failed
    print(f"\n{'─'*44}")
    print(f"  {passed}/{total} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
