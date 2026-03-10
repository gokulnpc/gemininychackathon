"""Unit tests for services/integrations/reddit.py — mocked paths only.

No real API calls made. Safe to run without credentials or internet.

Usage:
    cd backend && .venv/bin/python tests/unit/test_reddit.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.integrations.reddit import (
    _NICHE_KEYWORDS,
    _NICHE_TO_SUBREDDITS,
    _fetch_posts,
    detect_niche,
    fetch_trending,
)

# ── Fake Reddit API response data ─────────────────────────────────────────────

def _fake_children(posts: list[dict]) -> dict:
    """Build a fake Reddit JSON listing response."""
    return {
        "data": {
            "children": [
                {"data": {**p, "stickied": p.get("stickied", False)}}
                for p in posts
            ]
        }
    }


_SAMPLE_POSTS = [
    {"title": "Post A", "score": 100, "upvote_ratio": 0.95, "num_comments": 42},
    {"title": "Post B", "score": 50,  "upvote_ratio": 0.88, "num_comments": 10},
]

_STICKIED_POSTS = [
    {"title": "Stickied Announcement", "score": 999, "upvote_ratio": 1.0, "num_comments": 0, "stickied": True},
    {"title": "Normal Post", "score": 30, "upvote_ratio": 0.80, "num_comments": 5},
]


# ── detect_niche (pure) ──────────────────────────────────────────────────────

def test_detect_horror_niche():
    result = detect_niche("I saw a scary ghost in the haunted house")
    assert result == "horror", f"Expected 'horror', got: {result}"
    print("  ✓ horror keywords → 'horror'")


def test_detect_finance_niche():
    result = detect_niche("invest in stock trading for profit income")
    assert result == "finance", f"Expected 'finance', got: {result}"
    print("  ✓ finance keywords → 'finance'")


def test_detect_general_when_no_keywords_match():
    result = detect_niche("the quick brown fox jumps over the lazy dog")
    assert result == "general", f"Expected 'general', got: {result}"
    print("  ✓ no keyword matches → 'general'")


def test_detect_niche_case_insensitive():
    result = detect_niche("HORROR GHOST SCARY NIGHTMARE")
    assert result == "horror", f"Expected 'horror', got: {result}"
    print("  ✓ uppercase text → still detects 'horror'")


def test_detect_niche_empty_transcript():
    result = detect_niche("")
    assert result == "general", f"Expected 'general', got: {result}"
    print("  ✓ empty transcript → 'general'")


def test_detect_niche_tiebreaker_highest_count():
    # 3 horror keywords vs 1 finance keyword → horror wins
    result = detect_niche("scary ghost haunted money")
    assert result == "horror", f"Expected 'horror' (3 hits vs 1), got: {result}"
    print("  ✓ highest keyword count wins tiebreaker")


def test_niche_keywords_are_valid_strings():
    for niche, keywords in _NICHE_KEYWORDS.items():
        assert isinstance(niche, str), f"key is not str: {niche}"
        for kw in keywords:
            assert isinstance(kw, str), f"keyword is not str: {kw}"
    print(f"  ✓ all {len(_NICHE_KEYWORDS)} niches have valid string keywords")


# ── _fetch_posts (mocked httpx) ──────────────────────────────────────────────

async def test_fetch_posts_returns_parsed_posts():
    """200 response with valid children → parsed post dicts."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _fake_children(_SAMPLE_POSTS)

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.integrations.reddit.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_posts("AskReddit", "hot", limit=5)

    assert len(result) == 2, f"Expected 2 posts, got {len(result)}"
    assert result[0]["title"] == "Post A"
    assert result[0]["score"] == 100
    assert "subreddit" in result[0]
    assert result[0]["sort"] == "hot"
    print("  ✓ 200 response → parsed post dicts with correct keys")


async def test_fetch_posts_filters_stickied():
    """Stickied posts are excluded from results."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _fake_children(_STICKIED_POSTS)

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.integrations.reddit.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_posts("AskReddit", "hot")

    assert len(result) == 1, f"Expected 1 (stickied filtered), got {len(result)}"
    assert result[0]["title"] == "Normal Post"
    print("  ✓ stickied posts filtered out")


async def test_fetch_posts_non_200_returns_empty():
    """Non-200 HTTP status → empty list."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.integrations.reddit.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_posts("nonexistent", "hot")

    assert result == [], f"Expected [], got: {result}"
    print("  ✓ HTTP 404 → []")


async def test_fetch_posts_network_error_returns_empty():
    """Network error → graceful fallback to empty list."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.integrations.reddit.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_posts("AskReddit", "hot")

    assert result == [], f"Expected [], got: {result}"
    print("  ✓ network error → [] (graceful fallback)")


async def test_fetch_posts_controversial_adds_time_param():
    """sort='controversial' adds t=week to request params."""
    captured_params = {}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _fake_children([])

    async def capture_get(url, params=None):
        captured_params.update(params or {})
        return mock_resp

    mock_client = AsyncMock()
    mock_client.get = capture_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.integrations.reddit.httpx.AsyncClient", return_value=mock_client):
        await _fetch_posts("AskReddit", "controversial", limit=5)

    assert captured_params.get("t") == "week", f"Expected t='week', got: {captured_params}"
    print("  ✓ controversial sort adds t=week param")


# ── fetch_trending (mocked orchestration) ─────────────────────────────────────

async def test_fetch_trending_explicit_niche():
    """Explicit niche='horror' uses horror subreddits."""
    with patch("services.integrations.reddit._fetch_posts", new=AsyncMock(return_value=_SAMPLE_POSTS)):
        result = await fetch_trending(niche="horror")

    assert result["niche"] == "horror"
    assert "nosleep" in result["subreddits_searched"]
    print("  ✓ explicit niche='horror' → horror subreddits")


async def test_fetch_trending_auto_detects_niche():
    """niche=None + transcript with horror keywords → auto-detects 'horror'."""
    with patch("services.integrations.reddit._fetch_posts", new=AsyncMock(return_value=_SAMPLE_POSTS)):
        result = await fetch_trending(niche=None, transcript="scary ghost haunted nightmare")

    assert result["niche"] == "horror", f"Expected 'horror', got: {result['niche']}"
    print("  ✓ auto-detected niche from transcript → 'horror'")


async def test_fetch_trending_defaults_to_general():
    """niche=None, transcript=None → defaults to 'general'."""
    with patch("services.integrations.reddit._fetch_posts", new=AsyncMock(return_value=_SAMPLE_POSTS)):
        result = await fetch_trending(niche=None, transcript=None)

    assert result["niche"] == "general", f"Expected 'general', got: {result['niche']}"
    print("  ✓ no niche, no transcript → 'general'")


async def test_fetch_trending_fallback_when_primary_sparse():
    """Primary returns < 3 posts → falls back to secondary subreddit."""
    call_count = 0

    async def sparse_then_extra(subreddit, sort, limit=5):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # First two calls (hot + controversial for primary) return very few
            return [_SAMPLE_POSTS[0]] if sort == "hot" else []
        # Fallback call returns one more post
        return [_SAMPLE_POSTS[1]]

    with patch("services.integrations.reddit._fetch_posts", side_effect=sparse_then_extra):
        result = await fetch_trending(niche="horror")

    assert call_count == 3, f"Expected 3 calls (primary hot + controversial + fallback), got {call_count}"
    # After extend, hot has 2 posts (1 primary + 1 fallback) — still < 3,
    # so subreddits_searched includes the fallback subreddit.
    assert len(result["subreddits_searched"]) > 1, "Expected fallback subreddit in searched list"
    assert len(result["hot_posts"]) == 2, f"Expected 2 hot posts (1+1), got {len(result['hot_posts'])}"
    print("  ✓ sparse primary → fetches from fallback subreddit")


async def test_fetch_trending_deduplicates_topics():
    """Duplicate titles across hot and controversial → deduplicated top_topics."""
    duplicate_posts = [
        {"title": "Same Title", "score": 10, "upvote_ratio": 0.9, "num_comments": 5, "subreddit": "test", "sort": "hot"},
        {"title": "Same Title", "score": 20, "upvote_ratio": 0.8, "num_comments": 3, "subreddit": "test", "sort": "hot"},
        {"title": "Unique Title", "score": 5, "upvote_ratio": 0.7, "num_comments": 1, "subreddit": "test", "sort": "hot"},
    ]

    with patch("services.integrations.reddit._fetch_posts", new=AsyncMock(return_value=duplicate_posts)):
        result = await fetch_trending(niche="general")

    titles = result["top_topics"]
    assert len(titles) == len(set(titles)), f"Duplicate titles found: {titles}"
    assert "Same Title" in titles
    assert "Unique Title" in titles
    print("  ✓ duplicate titles deduplicated in top_topics")


async def test_fetch_trending_result_shape():
    """Result dict has all expected keys."""
    with patch("services.integrations.reddit._fetch_posts", new=AsyncMock(return_value=_SAMPLE_POSTS)):
        result = await fetch_trending(niche="tech")

    expected_keys = {"niche", "subreddits_searched", "hot_posts", "controversial_posts", "top_topics"}
    assert expected_keys == set(result.keys()), f"Missing keys: {expected_keys - set(result.keys())}"
    assert isinstance(result["hot_posts"], list)
    assert isinstance(result["controversial_posts"], list)
    assert isinstance(result["top_topics"], list)
    assert isinstance(result["subreddits_searched"], list)
    print("  ✓ result has all expected keys with correct types")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_detect_horror_niche,
        test_detect_finance_niche,
        test_detect_general_when_no_keywords_match,
        test_detect_niche_case_insensitive,
        test_detect_niche_empty_transcript,
        test_detect_niche_tiebreaker_highest_count,
        test_niche_keywords_are_valid_strings,
    ]
    async_tests = [
        test_fetch_posts_returns_parsed_posts,
        test_fetch_posts_filters_stickied,
        test_fetch_posts_non_200_returns_empty,
        test_fetch_posts_network_error_returns_empty,
        test_fetch_posts_controversial_adds_time_param,
        test_fetch_trending_explicit_niche,
        test_fetch_trending_auto_detects_niche,
        test_fetch_trending_defaults_to_general,
        test_fetch_trending_fallback_when_primary_sparse,
        test_fetch_trending_deduplicates_topics,
        test_fetch_trending_result_shape,
    ]

    passed = failed = 0

    print("\n── detect_niche (pure) ──")
    for fn in sync_tests:
        print(f"[{fn.__name__}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── _fetch_posts (mocked httpx) ──")
    for fn in async_tests[:5]:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print("\n── fetch_trending (mocked orchestration) ──")
    for fn in async_tests[5:]:
        print(f"[{fn.__name__}]")
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
