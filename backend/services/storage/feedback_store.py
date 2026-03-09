"""Firestore-backed feedback loop for the Script Director agent.

Stores per-project outcome signals after video generation completes.
The script agent reads top-performing hooks from this collection to improve
its future output — making the system progressively better over time.

Schema (Firestore collection: "feedback"):
  project_id:      str
  created_at:      ISO-8601 timestamp
  hook_text:       str
  niche:           str
  art_style:       str
  quality_score:   float   (agent_quality_score from script metadata, 0-100)
  platforms:       list[str]
  scenes_count:    int

Top hooks (quality_score >= HIGH_QUALITY_THRESHOLD) are returned as additional
examples to the search_trending_hooks tool, augmenting the curated hook library.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HIGH_QUALITY_THRESHOLD = 85   # hooks at this score or above are shared as examples
MAX_FEEDBACK_HOOKS = 5        # cap on how many feedback hooks to inject per call
_FEEDBACK_COLLECTION = "feedback"


# ── Write ──────────────────────────────────────────────────────────────────────

def _firestore_available() -> bool:
    try:
        from google.cloud import firestore  # noqa: F401
        return True
    except ImportError:
        return False


def _get_db():
    from google.cloud import firestore
    from config import get_settings
    settings = get_settings()
    return firestore.Client(project=settings.google_cloud_project or None)


async def record_project_outcome(
    project_id: str,
    hook_text: str,
    niche: str,
    art_style: str,
    quality_score: float,
    platforms: list[str],
    scenes_count: int,
) -> None:
    """Persist project outcome signals to Firestore (fire-and-forget).

    Failures are logged as warnings — never raises.
    """
    try:
        from config import get_settings
        settings = get_settings()
        if not _firestore_available() or not settings.google_cloud_project:
            return

        doc = {
            "project_id":    project_id,
            "created_at":    datetime.now(timezone.utc).isoformat(),
            "hook_text":     hook_text,
            "niche":         niche,
            "art_style":     art_style,
            "quality_score": quality_score,
            "platforms":     platforms,
            "scenes_count":  scenes_count,
        }

        def _write():
            _get_db().collection(_FEEDBACK_COLLECTION).document(project_id).set(doc)

        await asyncio.to_thread(_write)
        logger.debug("Feedback recorded for project %s (score=%.1f)", project_id, quality_score)
    except Exception as exc:
        logger.warning("Failed to record feedback for project %s: %s", project_id, exc)


# ── Read ───────────────────────────────────────────────────────────────────────

async def get_top_hooks(niche: str, limit: int = MAX_FEEDBACK_HOOKS) -> list[dict]:
    """Return the top-performing hook examples for a given niche.

    Used by search_trending_hooks tool to augment the curated hook library with
    real-world high-scoring examples from previous generations.

    Returns [] on any error (never raises).
    """
    try:
        from config import get_settings
        settings = get_settings()
        if not _firestore_available() or not settings.google_cloud_project:
            return []

        def _query() -> list[dict]:
            docs = (
                _get_db().collection(_FEEDBACK_COLLECTION)
                .where("niche", "==", niche)
                .where("quality_score", ">=", HIGH_QUALITY_THRESHOLD)
                .order_by("quality_score", direction="DESCENDING")
                .limit(limit)
                .stream()
            )
            return [d.to_dict() for d in docs]

        return await asyncio.to_thread(_query)
    except Exception as exc:
        logger.warning("Failed to fetch feedback hooks for niche=%s: %s", niche, exc)
        return []
