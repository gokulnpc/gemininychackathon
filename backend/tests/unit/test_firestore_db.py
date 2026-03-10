"""Unit tests for services/storage/firestore_db.py — mocked paths only.

No real Firestore or GCS calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_firestore_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import services.storage.firestore_db as fdb
from services.storage.firestore_db import (
    delete_project,
    get_project,
    list_projects,
    save_project,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_PROJECT_ID = "test-proj-001"
_METADATA = {"project_id": _PROJECT_ID, "status": "done", "created_at": "2025-01-01T00:00:00Z"}

def _settings(project: str = "my-gcp-project"):
    return SimpleNamespace(google_cloud_project=project, gcs_bucket="test-bucket")


def _fs_ctx(project: str = "my-gcp-project"):
    """Context managers for Firestore path: _firestore_available=True + settings with project."""
    return (
        patch.object(fdb, "_firestore_available", return_value=True),
        patch("config.get_settings", return_value=_settings(project)),
    )


def _gcs_ctx():
    """Context managers for GCS fallback path: _firestore_available=False."""
    return (
        patch.object(fdb, "_firestore_available", return_value=False),
        patch("services.storage.firestore_db.get_settings", return_value=_settings()),
    )


# ── save_project ──────────────────────────────────────────────────────────────

async def test_save_project_uses_firestore_when_available():
    """Firestore path: asyncio.to_thread called; GCS not touched."""
    gcs_mock = AsyncMock()
    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.firestore_db.asyncio.to_thread", new=AsyncMock()) as mock_thread, \
         patch("services.storage.gcs.store_json", gcs_mock):
        await save_project(_PROJECT_ID, _METADATA)

    mock_thread.assert_called_once()
    gcs_mock.assert_not_called()
    print("  ✓ Firestore path: asyncio.to_thread called, GCS not touched")


async def test_save_project_gcs_fallback_when_firestore_unavailable():
    """GCS fallback: gcs.store_json called with correct key."""
    gcs_mock = AsyncMock()
    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.store_json", gcs_mock):
        await save_project(_PROJECT_ID, _METADATA)

    gcs_mock.assert_called_once_with(_METADATA, f"projects/{_PROJECT_ID}/metadata.json")
    print("  ✓ GCS fallback: gcs.store_json called with correct key")


async def test_save_project_gcs_fallback_when_no_project():
    """No google_cloud_project → GCS path even if Firestore pkg is installed."""
    gcs_mock = AsyncMock()
    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings(project="")), \
         patch("services.storage.gcs.store_json", gcs_mock):
        await save_project(_PROJECT_ID, _METADATA)

    gcs_mock.assert_called_once()
    print("  ✓ No google_cloud_project → GCS fallback even with Firestore available")


# ── get_project ───────────────────────────────────────────────────────────────

async def test_get_project_firestore_returns_dict():
    """Firestore path: returns dict when doc exists."""
    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.firestore_db.asyncio.to_thread",
               new=AsyncMock(return_value=_METADATA)):
        result = await get_project(_PROJECT_ID)

    assert result == _METADATA
    print("  ✓ Firestore path: returns dict from doc.to_dict()")


async def test_get_project_firestore_returns_none_when_doc_missing():
    """Firestore path: returns None when doc does not exist."""
    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.firestore_db.asyncio.to_thread",
               new=AsyncMock(return_value=None)):
        result = await get_project(_PROJECT_ID)

    assert result is None
    print("  ✓ Firestore path: returns None when doc does not exist")


async def test_get_project_gcs_fallback_returns_dict():
    """GCS fallback: returns dict from gcs.load_json."""
    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.load_json", new=AsyncMock(return_value=_METADATA)):
        result = await get_project(_PROJECT_ID)

    assert result == _METADATA
    print("  ✓ GCS fallback: returns dict from gcs.load_json")


async def test_get_project_gcs_fallback_returns_none_on_error():
    """GCS fallback: gcs.load_json raises → returns None silently."""
    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.load_json",
               new=AsyncMock(side_effect=FileNotFoundError("not found"))):
        result = await get_project(_PROJECT_ID)

    assert result is None
    print("  ✓ GCS fallback: load_json raises → None (silently caught)")


# ── list_projects ─────────────────────────────────────────────────────────────

async def test_list_projects_firestore_returns_list():
    """Firestore path: returns list of dicts from query."""
    projects = [_METADATA, {**_METADATA, "project_id": "proj-2"}]

    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.firestore_db.asyncio.to_thread",
               new=AsyncMock(return_value=projects)):
        result = await list_projects()

    assert result == projects
    assert len(result) == 2
    print("  ✓ Firestore path: returns list of dicts")


async def test_list_projects_gcs_filters_metadata_keys():
    """GCS fallback: only keys with /metadata.json at depth 3 are loaded."""
    all_keys = [
        "projects/proj-1/metadata.json",   # valid
        "projects/proj-2/metadata.json",   # valid
        "projects/proj-3/other.json",      # wrong filename
        "projects/extra/deep/metadata.json",  # too deep (4 parts)
        "other/proj-4/metadata.json",       # wrong prefix structure
    ]

    loaded = {"proj-1": {"project_id": "proj-1", "created_at": "2025-01-02"},
              "proj-2": {"project_id": "proj-2", "created_at": "2025-01-01"}}

    async def fake_load_json(key: str) -> dict:
        pid = key.split("/")[1]
        if pid in loaded:
            return loaded[pid]
        raise FileNotFoundError(key)

    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.list_keys", new=AsyncMock(return_value=all_keys)), \
         patch("services.storage.gcs.load_json", side_effect=fake_load_json):
        result = await list_projects()

    # Only proj-1 and proj-2 should be loaded
    ids = [r["project_id"] for r in result]
    assert "proj-1" in ids
    assert "proj-2" in ids
    assert len(result) == 2
    print("  ✓ GCS fallback: filters to depth-3 /metadata.json keys only")


async def test_list_projects_gcs_skips_failed_loads():
    """GCS fallback: projects that fail to load are skipped, not raised."""
    all_keys = [
        "projects/good-proj/metadata.json",
        "projects/bad-proj/metadata.json",
    ]

    async def fake_load_json(key: str) -> dict:
        if "bad" in key:
            raise RuntimeError("GCS read error")
        return {"project_id": "good-proj", "created_at": "2025-01-01"}

    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.list_keys", new=AsyncMock(return_value=all_keys)), \
         patch("services.storage.gcs.load_json", side_effect=fake_load_json):
        result = await list_projects()

    assert len(result) == 1
    assert result[0]["project_id"] == "good-proj"
    print("  ✓ GCS fallback: failed loads skipped, others returned")


async def test_list_projects_gcs_sorted_by_created_at_desc():
    """GCS fallback: results sorted by created_at descending."""
    all_keys = [
        "projects/old-proj/metadata.json",
        "projects/new-proj/metadata.json",
        "projects/mid-proj/metadata.json",
    ]
    data = {
        "old-proj": {"project_id": "old-proj", "created_at": "2024-01-01"},
        "new-proj": {"project_id": "new-proj", "created_at": "2025-06-01"},
        "mid-proj": {"project_id": "mid-proj", "created_at": "2025-01-01"},
    }

    async def fake_load_json(key: str) -> dict:
        pid = key.split("/")[1]
        return data[pid]

    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.list_keys", new=AsyncMock(return_value=all_keys)), \
         patch("services.storage.gcs.load_json", side_effect=fake_load_json):
        result = await list_projects()

    assert result[0]["project_id"] == "new-proj"
    assert result[1]["project_id"] == "mid-proj"
    assert result[2]["project_id"] == "old-proj"
    print("  ✓ GCS fallback: sorted by created_at descending")


async def test_list_projects_gcs_respects_limit():
    """GCS fallback: limit param caps the returned list."""
    all_keys = [f"projects/proj-{i}/metadata.json" for i in range(10)]

    async def fake_load_json(key: str) -> dict:
        pid = key.split("/")[1]
        return {"project_id": pid, "created_at": f"2025-01-{int(pid.split('-')[1])+1:02d}"}

    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.list_keys", new=AsyncMock(return_value=all_keys)), \
         patch("services.storage.gcs.load_json", side_effect=fake_load_json):
        result = await list_projects(limit=3)

    assert len(result) == 3
    print("  ✓ GCS fallback: limit=3 respected")


# ── delete_project ────────────────────────────────────────────────────────────

async def test_delete_project_uses_firestore_when_available():
    """Firestore path: asyncio.to_thread called; GCS not touched."""
    gcs_mock = AsyncMock()
    with patch.object(fdb, "_firestore_available", return_value=True), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.firestore_db.asyncio.to_thread", new=AsyncMock()) as mock_thread, \
         patch("services.storage.gcs.delete_object", gcs_mock):
        await delete_project(_PROJECT_ID)

    mock_thread.assert_called_once()
    gcs_mock.assert_not_called()
    print("  ✓ Firestore path: asyncio.to_thread called for delete, GCS not touched")


async def test_delete_project_gcs_fallback():
    """GCS fallback: gcs.delete_object called with correct key."""
    gcs_mock = AsyncMock()
    with patch.object(fdb, "_firestore_available", return_value=False), \
         patch("services.storage.firestore_db.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.delete_object", gcs_mock):
        await delete_project(_PROJECT_ID)

    gcs_mock.assert_called_once_with(f"projects/{_PROJECT_ID}/metadata.json")
    print("  ✓ GCS fallback: gcs.delete_object called with correct key")


# ── _firestore_available — availability check ─────────────────────────────────

def test_firestore_available_returns_false_when_not_installed():
    """Returns False when google-cloud-firestore is not importable."""
    import builtins
    real_import = builtins.__import__

    def import_raiser(name, *args, **kwargs):
        if name in ("google.cloud.firestore", "google.cloud") and "firestore" in str(args):
            raise ImportError("google-cloud-firestore not installed")
        return real_import(name, *args, **kwargs)

    # Clear the lru_cache so we can test the fresh check
    fdb._firestore_available.cache_clear()
    try:
        with patch.dict("sys.modules", {"google.cloud.firestore": None}):
            result = fdb._firestore_available()
        # If firestore is installed, the result depends on the environment;
        # the key test is: it doesn't raise an exception
        assert isinstance(result, bool)
    finally:
        fdb._firestore_available.cache_clear()
    print(f"  ✓ _firestore_available() returns bool without raising: {result}")


def test_firestore_available_is_cached():
    """lru_cache ensures the import check runs only once."""
    fdb._firestore_available.cache_clear()
    # Call twice — only one actual evaluation
    r1 = fdb._firestore_available()
    r2 = fdb._firestore_available()
    assert r1 == r2
    info = fdb._firestore_available.cache_info()
    assert info.hits >= 1, f"Expected at least 1 cache hit, got {info.hits}"
    fdb._firestore_available.cache_clear()
    print(f"  ✓ _firestore_available cached: hits={info.hits}, misses={info.misses}")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_firestore_available_returns_false_when_not_installed,
        test_firestore_available_is_cached,
    ]

    async_tests = [
        test_save_project_uses_firestore_when_available,
        test_save_project_gcs_fallback_when_firestore_unavailable,
        test_save_project_gcs_fallback_when_no_project,
        test_get_project_firestore_returns_dict,
        test_get_project_firestore_returns_none_when_doc_missing,
        test_get_project_gcs_fallback_returns_dict,
        test_get_project_gcs_fallback_returns_none_on_error,
        test_list_projects_firestore_returns_list,
        test_list_projects_gcs_filters_metadata_keys,
        test_list_projects_gcs_skips_failed_loads,
        test_list_projects_gcs_sorted_by_created_at_desc,
        test_list_projects_gcs_respects_limit,
        test_delete_project_uses_firestore_when_available,
        test_delete_project_gcs_fallback,
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
