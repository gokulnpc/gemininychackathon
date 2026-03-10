"""Unit tests for services/storage/gcs.py — mocked paths only.

No real GCS calls made. Safe to run without credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_gcs.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import services.storage.gcs as gcs_mod
from services.storage.gcs import (
    _local_url,
    _public_url,
    delete_object,
    download_file,
    generate_presigned_url,
    key_exists,
    list_keys,
    load_json,
    store_json,
    upload_file,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_BUCKET = "test-bucket"
_PROJECT = "test-project"
_GCS_KEY = "projects/proj-1/metadata.json"
_FAKE_DATA = {"project_id": "proj-1", "status": "done"}
_FAKE_URL = f"https://storage.googleapis.com/{_BUCKET}/{_GCS_KEY}"
_FAKE_LOCAL_URL = f"http://localhost:8000/outputs/{_GCS_KEY}"


def _settings(bucket: str = _BUCKET, project: str = _PROJECT) -> SimpleNamespace:
    return SimpleNamespace(gcs_bucket=bucket, google_cloud_project=project)


def _gcs_patch(available: bool = True, bucket: str = _BUCKET):
    """Return context managers for the GCS path."""
    return (
        patch.object(gcs_mod, "_gcs_available", return_value=available),
        patch("services.storage.gcs.get_settings", return_value=_settings(bucket=bucket)),
    )


# ── Pure helpers — no mocks ───────────────────────────────────────────────────

def test_public_url_format():
    url = _public_url("my-bucket", "path/to/file.mp4")
    assert url == "https://storage.googleapis.com/my-bucket/path/to/file.mp4"
    print("  ✓ _public_url: correct GCS URL format")


def test_local_url_default_base():
    url = _local_url("path/to/file.mp4")
    assert url == "http://localhost:8000/outputs/path/to/file.mp4"
    print("  ✓ _local_url: correct localhost URL with default base")


def test_local_url_custom_base():
    url = _local_url("path/to/file.mp4", base_url="https://myapp.com")
    assert url == "https://myapp.com/outputs/path/to/file.mp4"
    print("  ✓ _local_url: custom base_url respected")


# ── _gcs_available — caching ──────────────────────────────────────────────────

def test_gcs_available_returns_bool():
    """Returns a bool without raising, regardless of whether GCS is installed."""
    gcs_mod._gcs_available.cache_clear()
    try:
        result = gcs_mod._gcs_available()
        assert isinstance(result, bool)
    finally:
        gcs_mod._gcs_available.cache_clear()
    print(f"  ✓ _gcs_available() returns bool: {result}")


def test_gcs_available_is_cached():
    """lru_cache: second call is a cache hit."""
    gcs_mod._gcs_available.cache_clear()
    try:
        gcs_mod._gcs_available()
        gcs_mod._gcs_available()
        info = gcs_mod._gcs_available.cache_info()
        assert info.hits >= 1, f"Expected ≥1 cache hit, got {info.hits}"
    finally:
        gcs_mod._gcs_available.cache_clear()
    print(f"  ✓ _gcs_available cached: hits={info.hits}, misses={info.misses}")


# ── upload_file ───────────────────────────────────────────────────────────────

async def test_upload_file_gcs_path_returns_public_url():
    """GCS path: asyncio.to_thread called, returns GCS public URL."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_FAKE_URL)) as mock_thread:
        result = await upload_file("/tmp/video.mp4", _GCS_KEY)

    mock_thread.assert_called_once()
    assert result == _FAKE_URL
    print("  ✓ upload_file GCS: asyncio.to_thread called, returns public URL")


async def test_upload_file_local_fallback_uses_shutil_copy():
    """Local fallback: asyncio.to_thread(shutil.copy2, ...) called, returns local URL."""
    captured = {}

    async def fake_to_thread(fn, *args, **kwargs):
        captured["fn"] = fn
        captured["args"] = args
        return None  # shutil.copy2 returns None

    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", side_effect=fake_to_thread):
        result = await upload_file("/tmp/video.mp4", _GCS_KEY)

    import shutil
    assert captured["fn"] is shutil.copy2, f"Expected shutil.copy2, got {captured['fn']}"
    assert "/tmp/video.mp4" in captured["args"]
    assert result == _FAKE_LOCAL_URL
    print("  ✓ upload_file local: shutil.copy2 called via asyncio.to_thread")


async def test_upload_file_local_fallback_when_no_bucket():
    """Empty gcs_bucket → local fallback even if GCS is installed."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings(bucket="")), \
         patch("services.storage.gcs.asyncio.to_thread", new=AsyncMock(return_value=None)):
        result = await upload_file("/tmp/video.mp4", _GCS_KEY)

    assert result == _FAKE_LOCAL_URL
    print("  ✓ upload_file: empty gcs_bucket → local fallback")


# ── generate_presigned_url ────────────────────────────────────────────────────

async def test_generate_presigned_url_local_when_gcs_unavailable():
    """GCS unavailable → returns local URL without calling to_thread."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        result = await generate_presigned_url(_GCS_KEY)

    mock_thread.assert_not_called()
    assert result == _FAKE_LOCAL_URL
    print("  ✓ generate_presigned_url: GCS unavailable → local URL, no thread")


async def test_generate_presigned_url_gcs_calls_to_thread():
    """GCS available → asyncio.to_thread called for signing."""
    _SIGNED_URL = "https://storage.googleapis.com/signed-url-here"

    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_SIGNED_URL)):
        result = await generate_presigned_url(_GCS_KEY)

    assert result == _SIGNED_URL
    print("  ✓ generate_presigned_url GCS: asyncio.to_thread called, returns signed URL")


async def test_generate_presigned_url_falls_back_to_public_on_error():
    """Signing raises → falls back to public GCS URL."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(side_effect=Exception("credentials error"))):
        result = await generate_presigned_url(_GCS_KEY)

    assert result == _FAKE_URL
    print("  ✓ generate_presigned_url: signing error → falls back to public URL")


# ── download_file ─────────────────────────────────────────────────────────────

async def test_download_file_gcs_path():
    """GCS path: asyncio.to_thread called, returns local_path."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", new=AsyncMock(return_value=None)):
        result = await download_file(_GCS_KEY, "/tmp/output.mp4")

    assert result == "/tmp/output.mp4"
    print("  ✓ download_file GCS: returns local_path")


async def test_download_file_local_fallback_uses_shutil_copy():
    """Local fallback: asyncio.to_thread(shutil.copy2, ...) called."""
    captured = {}

    async def fake_to_thread(fn, *args, **kwargs):
        captured["fn"] = fn
        return None

    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", side_effect=fake_to_thread):
        result = await download_file(_GCS_KEY, "/tmp/output.mp4")

    import shutil
    assert captured["fn"] is shutil.copy2
    assert result == "/tmp/output.mp4"
    print("  ✓ download_file local: shutil.copy2 called via asyncio.to_thread")


# ── store_json ────────────────────────────────────────────────────────────────

async def test_store_json_gcs_path_returns_public_url():
    """GCS path: asyncio.to_thread called, returns GCS public URL."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_FAKE_URL)) as mock_thread:
        result = await store_json(_FAKE_DATA, _GCS_KEY)

    mock_thread.assert_called_once()
    assert result == _FAKE_URL
    print("  ✓ store_json GCS: asyncio.to_thread called, returns public URL")


async def test_store_json_local_fallback_uses_to_thread():
    """Local fallback: asyncio.to_thread called (fix for blocking I/O), returns local URL."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_FAKE_LOCAL_URL)) as mock_thread:
        result = await store_json(_FAKE_DATA, _GCS_KEY)

    mock_thread.assert_called_once()
    assert result == _FAKE_LOCAL_URL
    print("  ✓ store_json local: asyncio.to_thread called (non-blocking I/O)")


async def test_store_json_local_actually_writes_file():
    """Local fallback end-to-end: JSON file is written and readable."""
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch _OUTPUTS_DIR to use our temp dir
        with patch.object(gcs_mod, "_gcs_available", return_value=False), \
             patch("services.storage.gcs.get_settings", return_value=_settings()), \
             patch("services.storage.gcs._OUTPUTS_DIR", tmpdir):
            result = await store_json(_FAKE_DATA, "test/data.json")

        written_path = os.path.join(tmpdir, "test", "data.json")
        assert os.path.exists(written_path), f"File not written: {written_path}"
        with open(written_path) as f:
            loaded = json.load(f)
        assert loaded == _FAKE_DATA

    assert "localhost" in result
    print("  ✓ store_json local: file written correctly and parseable")


# ── load_json ─────────────────────────────────────────────────────────────────

async def test_load_json_gcs_path_returns_dict():
    """GCS path: asyncio.to_thread called, returns dict."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_FAKE_DATA)) as mock_thread:
        result = await load_json(_GCS_KEY)

    mock_thread.assert_called_once()
    assert result == _FAKE_DATA
    print("  ✓ load_json GCS: asyncio.to_thread called, returns dict")


async def test_load_json_local_fallback_uses_to_thread():
    """Local fallback: asyncio.to_thread called (fix for blocking I/O), returns dict."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=_FAKE_DATA)) as mock_thread:
        result = await load_json(_GCS_KEY)

    mock_thread.assert_called_once()
    assert result == _FAKE_DATA
    print("  ✓ load_json local: asyncio.to_thread called (non-blocking I/O)")


async def test_load_json_local_reads_written_file():
    """Local fallback end-to-end: reads a file that was previously stored."""
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write the file manually
        key = "test/data.json"
        dest = os.path.join(tmpdir, "test", "data.json")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            json.dump(_FAKE_DATA, f)

        with patch.object(gcs_mod, "_gcs_available", return_value=False), \
             patch("services.storage.gcs.get_settings", return_value=_settings()), \
             patch("services.storage.gcs._OUTPUTS_DIR", tmpdir):
            result = await load_json(key)

    assert result == _FAKE_DATA
    print("  ✓ load_json local: reads and parses JSON correctly")


# ── list_keys ─────────────────────────────────────────────────────────────────

async def test_list_keys_gcs_path():
    """GCS path: asyncio.to_thread called, returns list of strings."""
    fake_keys = ["projects/p1/metadata.json", "projects/p2/metadata.json"]

    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread",
               new=AsyncMock(return_value=fake_keys)):
        result = await list_keys("projects/")

    assert result == fake_keys
    print("  ✓ list_keys GCS: returns list of strings from to_thread")


async def test_list_keys_local_fallback_with_temp_dir():
    """Local fallback: walks the outputs dir, returns relative paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        for sub in ["p1", "p2"]:
            path = os.path.join(tmpdir, "projects", sub, "metadata.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("{}")

        with patch.object(gcs_mod, "_gcs_available", return_value=False), \
             patch("services.storage.gcs.get_settings", return_value=_settings()), \
             patch("services.storage.gcs._OUTPUTS_DIR", tmpdir):
            result = await list_keys("projects/")

    assert len(result) == 2
    assert all(k.startswith("projects") for k in result)
    assert all(k.endswith("metadata.json") for k in result)
    print(f"  ✓ list_keys local: found {len(result)} keys in temp dir")


async def test_list_keys_local_empty_prefix():
    """Local fallback: prefix dir does not exist → empty list."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs._OUTPUTS_DIR", "/nonexistent/path/xyz"):
        result = await list_keys("projects/")

    assert result == []
    print("  ✓ list_keys local: non-existent prefix → []")


# ── key_exists ────────────────────────────────────────────────────────────────

async def test_key_exists_gcs_path():
    """GCS path: asyncio.to_thread called, returns True."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", new=AsyncMock(return_value=True)):
        result = await key_exists(_GCS_KEY)

    assert result is True
    print("  ✓ key_exists GCS: asyncio.to_thread called, returns True")


async def test_key_exists_local_true_when_file_present():
    """Local fallback: returns True when file exists on disk."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        key = os.path.relpath(tmp_path, "/")
        with patch.object(gcs_mod, "_gcs_available", return_value=False), \
             patch("services.storage.gcs.get_settings", return_value=_settings()), \
             patch("services.storage.gcs._local_path", return_value=tmp_path):
            result = await key_exists(key)

        assert result is True
    finally:
        os.unlink(tmp_path)
    print("  ✓ key_exists local: returns True when file exists")


async def test_key_exists_local_false_when_file_missing():
    """Local fallback: returns False when file does not exist."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs._local_path", return_value="/tmp/does_not_exist_xyzzy.json"):
        result = await key_exists("missing/key.json")

    assert result is False
    print("  ✓ key_exists local: returns False when file missing")


# ── delete_object ─────────────────────────────────────────────────────────────

async def test_delete_object_gcs_path():
    """GCS path: asyncio.to_thread called."""
    with patch.object(gcs_mod, "_gcs_available", return_value=True), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        await delete_object(_GCS_KEY)

    mock_thread.assert_called_once()
    print("  ✓ delete_object GCS: asyncio.to_thread called")


async def test_delete_object_local_removes_file():
    """Local fallback: existing file is removed."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    assert os.path.exists(tmp_path)

    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs._local_path", return_value=tmp_path):
        await delete_object("some/key.json")

    assert not os.path.exists(tmp_path), "File should have been deleted"
    print("  ✓ delete_object local: file removed from disk")


async def test_delete_object_local_no_error_when_file_missing():
    """Local fallback: file does not exist → no exception raised."""
    with patch.object(gcs_mod, "_gcs_available", return_value=False), \
         patch("services.storage.gcs.get_settings", return_value=_settings()), \
         patch("services.storage.gcs._local_path",
               return_value="/tmp/does_not_exist_xyzzy_9999.json"):
        await delete_object("missing/key.json")  # Should not raise

    print("  ✓ delete_object local: missing file → no error")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    sync_tests = [
        test_public_url_format,
        test_local_url_default_base,
        test_local_url_custom_base,
        test_gcs_available_returns_bool,
        test_gcs_available_is_cached,
    ]

    async_tests = [
        test_upload_file_gcs_path_returns_public_url,
        test_upload_file_local_fallback_uses_shutil_copy,
        test_upload_file_local_fallback_when_no_bucket,
        test_generate_presigned_url_local_when_gcs_unavailable,
        test_generate_presigned_url_gcs_calls_to_thread,
        test_generate_presigned_url_falls_back_to_public_on_error,
        test_download_file_gcs_path,
        test_download_file_local_fallback_uses_shutil_copy,
        test_store_json_gcs_path_returns_public_url,
        test_store_json_local_fallback_uses_to_thread,
        test_store_json_local_actually_writes_file,
        test_load_json_gcs_path_returns_dict,
        test_load_json_local_fallback_uses_to_thread,
        test_load_json_local_reads_written_file,
        test_list_keys_gcs_path,
        test_list_keys_local_fallback_with_temp_dir,
        test_list_keys_local_empty_prefix,
        test_key_exists_gcs_path,
        test_key_exists_local_true_when_file_present,
        test_key_exists_local_false_when_file_missing,
        test_delete_object_gcs_path,
        test_delete_object_local_removes_file,
        test_delete_object_local_no_error_when_file_missing,
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
