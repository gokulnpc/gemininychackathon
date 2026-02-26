"""Reddit trending topic research for VoiceVid smart-process pipeline.

Fetches hot and controversial posts from niche-relevant subreddits using
Reddit's public JSON API (no authentication required — read-only public data).

Used in Stage 1 of the smart-process flow to give Nemotron real-world
trending context before it configures the video series.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

# ── Niche keyword scoring ──────────────────────────────────────────────────────
# Used to auto-detect niche from transcript when the caller doesn't specify one.

_NICHE_KEYWORDS: dict[str, list[str]] = {
    "horror":        ["horror", "scary", "creepy", "ghost", "paranormal", "supernatural",
                      "haunted", "demon", "monster", "nightmare"],
    "finance":       ["money", "invest", "stock", "crypto", "finance", "wealth", "budget",
                      "debt", "saving", "trading", "income", "profit"],
    "fitness":       ["workout", "gym", "fitness", "exercise", "muscle", "diet", "weight",
                      "lifting", "training", "run", "cardio", "protein"],
    "food":          ["recipe", "cooking", "food", "restaurant", "eat", "chef", "meal",
                      "baking", "kitchen", "dish", "ingredient", "cuisine"],
    "tech":          ["tech", "software", "app", "ai", "code", "startup", "programming",
                      "computer", "digital", "algorithm", "robot", "automation"],
    "gaming":        ["game", "gaming", "play", "player", "console", "minecraft", "steam",
                      "esports", "fps", "rpg", "twitch", "controller"],
    "travel":        ["travel", "trip", "adventure", "explore", "destination", "vacation",
                      "backpack", "abroad", "abroad", "wanderlust", "tourist"],
    "nature":        ["nature", "wildlife", "animal", "forest", "ocean", "hiking",
                      "environment", "mountain", "planet", "ecosystem", "bird"],
    "science":       ["science", "research", "study", "discovery", "biology", "physics",
                      "space", "chemistry", "experiment", "nasa", "universe"],
    "history":       ["history", "historical", "ancient", "war", "civilization", "empire",
                      "century", "past", "medieval", "revolution", "dynasty"],
    "mystery":       ["mystery", "unsolved", "conspiracy", "secret", "hidden", "weird",
                      "strange", "unexplained", "disappear", "cover-up"],
    "motivation":    ["motivation", "success", "mindset", "productivity", "goals", "hustle",
                      "inspire", "achieve", "growth", "discipline", "habit"],
    "relationships": ["relationship", "love", "dating", "marriage", "family", "breakup",
                      "toxic", "partner", "jealous", "heartbreak"],
    "mental_health": ["anxiety", "depression", "mental", "stress", "therapy", "wellbeing",
                      "heal", "trauma", "self-care", "mindfulness"],
}

# ── Niche → subreddits ─────────────────────────────────────────────────────────

_NICHE_TO_SUBREDDITS: dict[str, list[str]] = {
    "horror":        ["nosleep", "creepy", "horror", "paranormal"],
    "finance":       ["personalfinance", "investing", "wallstreetbets", "financialindependence"],
    "fitness":       ["fitness", "bodybuilding", "loseit", "running"],
    "food":          ["food", "Cooking", "recipes", "MealPrepSunday"],
    "tech":          ["technology", "programming", "MachineLearning", "startups"],
    "gaming":        ["gaming", "pcgaming", "Games", "patientgamers"],
    "travel":        ["travel", "solotravel", "backpacking", "digitalnomad"],
    "nature":        ["nature", "EarthPorn", "wildlife", "hiking"],
    "science":       ["science", "askscience", "todayilearned", "space"],
    "history":       ["history", "AskHistorians", "todayilearned", "HistoryMemes"],
    "mystery":       ["UnsolvedMysteries", "mystery", "conspiracy", "AskReddit"],
    "motivation":    ["GetMotivated", "productivity", "selfimprovement", "entrepreneur"],
    "relationships": ["relationship_advice", "dating_advice", "AITA", "relationship"],
    "mental_health": ["mentalhealth", "anxiety", "depression", "meditation"],
    "general":       ["AskReddit", "todayilearned", "mildlyinteresting", "interestingasfuck"],
}

_HEADERS = {"User-Agent": "VoiceVidBot/1.0 (educational content research)"}
_TIMEOUT = 8.0


# ── Helpers ────────────────────────────────────────────────────────────────────

def detect_niche(transcript: str) -> str:
    """Detect content niche from transcript text using keyword frequency scoring.

    Scores each niche by counting how many of its keywords appear in the text.
    Returns the highest-scoring niche, or 'general' if no keywords match.
    """
    text = transcript.lower()
    scores: dict[str, int] = {
        niche: sum(text.count(kw) for kw in keywords)
        for niche, keywords in _NICHE_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "general"


async def _fetch_posts(subreddit: str, sort: str, limit: int = 5) -> list[dict]:
    """Fetch posts from a subreddit (sort = 'hot' or 'controversial')."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params: dict = {"limit": limit}
    if sort == "controversial":
        params["t"] = "week"

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.debug("Reddit r/%s/%s → HTTP %s", subreddit, sort, resp.status_code)
            return []

        children = resp.json().get("data", {}).get("children", [])
        return [
            {
                "title":        c["data"].get("title", ""),
                "score":        c["data"].get("score", 0),
                "upvote_ratio": round(c["data"].get("upvote_ratio", 0), 2),
                "num_comments": c["data"].get("num_comments", 0),
                "subreddit":    subreddit,
                "sort":         sort,
            }
            for c in children
            if not c["data"].get("stickied")
        ]
    except Exception as exc:
        logger.debug("Reddit fetch failed r/%s/%s: %s", subreddit, sort, exc)
        return []


# ── Public API ─────────────────────────────────────────────────────────────────

async def fetch_trending(
    niche: str | None = None,
    transcript: str | None = None,
) -> dict:
    """Fetch hot and controversial Reddit posts for a given content niche.

    Args:
        niche:      Content niche label (horror, finance, fitness, etc.).
                    If None, auto-detected from transcript.
        transcript: Raw idea text — used for niche detection when niche is None.

    Returns:
        {
            "niche":               str,
            "subreddits_searched": [str, ...],
            "hot_posts":           [{title, score, num_comments, subreddit}, ...],
            "controversial_posts": [{title, score, num_comments, subreddit}, ...],
            "top_topics":          [str, ...],   # deduped titles — fed straight to Nemotron
        }
    Falls back to an empty result dict on any network failure.
    """
    resolved_niche = niche or (detect_niche(transcript) if transcript else "general")
    subreddits = _NICHE_TO_SUBREDDITS.get(resolved_niche, _NICHE_TO_SUBREDDITS["general"])
    primary, *fallbacks = subreddits

    logger.info("Reddit research: niche=%s subreddit=r/%s", resolved_niche, primary)

    hot, controversial = await asyncio.gather(
        _fetch_posts(primary, "hot", limit=6),
        _fetch_posts(primary, "controversial", limit=4),
        return_exceptions=False,
    )

    # Pull from secondary subreddit if primary returned very little
    if len(hot) < 3 and fallbacks:
        extra = await _fetch_posts(fallbacks[0], "hot", limit=4)
        hot.extend(extra)

    # Deduplicated topic titles (what Nemotron actually reads)
    seen: set[str] = set()
    top_topics: list[str] = []
    for post in [*hot[:5], *controversial[:3]]:
        title = post["title"]
        if title not in seen:
            seen.add(title)
            top_topics.append(title)

    result = {
        "niche":               resolved_niche,
        "subreddits_searched": [primary] + (fallbacks[:1] if len(hot) < 3 else []),
        "hot_posts":           hot,
        "controversial_posts": controversial,
        "top_topics":          top_topics[:8],
    }
    logger.info(
        "Reddit: niche=%s hot=%d controversial=%d topics=%d",
        resolved_niche, len(hot), len(controversial), len(top_topics),
    )
    return result
