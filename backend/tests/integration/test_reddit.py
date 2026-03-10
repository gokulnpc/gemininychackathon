"""Integration test for services/integrations/reddit.py — real Reddit API call.

Fetches real hot/controversial posts from Reddit's public JSON API.
No API key or authentication required — uses read-only public endpoints.

Requires: internet access.

Usage:
    cd backend && .venv/bin/python tests/integration/test_reddit.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.integrations.reddit import fetch_trending


async def test_real_reddit_fetch():
    """Real Reddit API call — fetches trending posts for 'general' niche."""
    print("  Fetching trending posts from Reddit (niche=general) ...")

    result = await fetch_trending(niche="general")

    # Validate top-level keys
    expected_keys = {"niche", "subreddits_searched", "hot_posts", "controversial_posts", "top_topics"}
    assert expected_keys == set(result.keys()), f"Missing keys: {expected_keys - set(result.keys())}"

    assert result["niche"] == "general", f"Expected niche='general', got: {result['niche']}"
    assert isinstance(result["subreddits_searched"], list)
    assert len(result["subreddits_searched"]) >= 1

    # Validate hot_posts structure
    assert isinstance(result["hot_posts"], list), f"hot_posts is not a list: {type(result['hot_posts'])}"

    if len(result["hot_posts"]) > 0:
        post = result["hot_posts"][0]
        for key in ("title", "score", "subreddit", "sort", "num_comments", "upvote_ratio"):
            assert key in post, f"Post missing key '{key}': {post}"
        assert isinstance(post["title"], str)
        assert isinstance(post["score"], int)

    print(f"  ✓ niche={result['niche']}")
    print(f"  ✓ subreddits searched: {result['subreddits_searched']}")
    print(f"  ✓ {len(result['hot_posts'])} hot posts, {len(result['controversial_posts'])} controversial")
    print(f"  ✓ {len(result['top_topics'])} top topics")

    if result["top_topics"]:
        print(f"\n  {'─'*40}")
        print(f"  Top topics:")
        for i, topic in enumerate(result["top_topics"][:5], 1):
            print(f"    {i}. {topic[:80]}")


async def main() -> None:
    passed = failed = 0
    print(f"[{test_real_reddit_fetch.__name__}]")
    try:
        await test_real_reddit_fetch()
        passed += 1
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
