"""Integration tests for services/storage/firestore_db.py — real persistence calls.

Works in two modes:
  - With GOOGLE_CLOUD_PROJECT set: tests Firestore path
  - Without GOOGLE_CLOUD_PROJECT: tests GCS fallback path (always runnable locally)

Uses a unique test project ID with a timestamp suffix to avoid collisions.
Always cleans up even if assertions fail.

Usage:
    cd backend && .venv/bin/python tests/integration/test_firestore_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.storage.firestore_db import (
    delete_project,
    get_project,
    list_projects,
    save_project,
)

_TEST_PROJECT_ID = f"test-integration-{int(time.time())}"
_TEST_METADATA = {
    "project_id": _TEST_PROJECT_ID,
    "status": "done",
    "niche": "horror",
    "created_at": "2025-01-01T00:00:00Z",
    "video_url": "https://example.com/video.mp4",
}


def _backend():
    """Return which backend is active."""
    from config import get_settings
    from services.storage.firestore_db import _firestore_available
    s = get_settings()
    if _firestore_available() and s.google_cloud_project:
        return f"Firestore (project={s.google_cloud_project})"
    return "GCS fallback"


async def test_save_and_get_round_trip():
    """save_project → get_project returns the same metadata."""
    await save_project(_TEST_PROJECT_ID, _TEST_METADATA)
    result = await get_project(_TEST_PROJECT_ID)

    assert result is not None, f"Expected metadata, got None for project_id={_TEST_PROJECT_ID}"
    assert result.get("project_id") == _TEST_PROJECT_ID
    assert result.get("status") == "done"
    assert result.get("niche") == "horror"
    print(f"  ✓ save → get round-trip verified")


async def test_get_missing_project_returns_none():
    """get_project on a non-existent ID returns None."""
    result = await get_project("definitely-does-not-exist-xyzzy-9999")
    assert result is None, f"Expected None, got: {result}"
    print("  ✓ get on missing project → None")


async def test_list_projects_includes_saved():
    """list_projects includes the project saved in the round-trip test."""
    projects = await list_projects(limit=100)
    assert isinstance(projects, list), f"Expected list, got {type(projects)}"

    ids = [p.get("project_id") for p in projects]
    assert _TEST_PROJECT_ID in ids, (
        f"Expected {_TEST_PROJECT_ID!r} in project list. Found IDs: {ids[:5]}"
    )
    print(f"  ✓ list_projects returns {len(projects)} project(s), includes test project")


async def test_delete_project_removes_it():
    """delete_project → get_project returns None."""
    await delete_project(_TEST_PROJECT_ID)
    result = await get_project(_TEST_PROJECT_ID)
    assert result is None, f"Expected None after delete, got: {result}"
    print("  ✓ delete → get returns None")


async def test_list_projects_excludes_deleted():
    """After deletion, project no longer appears in list_projects."""
    projects = await list_projects(limit=100)
    ids = [p.get("project_id") for p in projects]
    assert _TEST_PROJECT_ID not in ids, (
        f"Expected {_TEST_PROJECT_ID!r} to be absent after delete, still found in: {ids[:5]}"
    )
    print(f"  ✓ deleted project absent from list_projects")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"  backend: {_backend()}")
    print(f"  test project_id: {_TEST_PROJECT_ID}\n")

    # Tests must run in order: save → get → list → delete → verify list
    tests = [
        test_save_and_get_round_trip,
        test_get_missing_project_returns_none,
        test_list_projects_includes_saved,
        test_delete_project_removes_it,
        test_list_projects_excludes_deleted,
    ]

    passed = failed = 0
    for fn in tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1
            # Try to clean up even on failure
            if fn in (test_save_and_get_round_trip, test_list_projects_includes_saved):
                try:
                    await delete_project(_TEST_PROJECT_ID)
                except Exception:
                    pass

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
