"""Integration tests for services/storage/gcs.py — real GCS or local fallback.

Works in two modes:
  - With GCS_BUCKET configured: tests real GCS operations
  - Without GCS_BUCKET: tests local-filesystem fallback (always runnable)

Uses unique keys with a timestamp suffix to avoid collisions.
Always cleans up with try/finally.

Usage:
    cd backend && .venv/bin/python tests/integration/test_gcs.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.storage.gcs import (
    delete_object,
    key_exists,
    list_keys,
    load_json,
    store_json,
    upload_file,
    generate_presigned_url,
)

_TS = int(time.time())
_JSON_KEY = f"test/integration/gcs_test_{_TS}.json"
_FILE_KEY = f"test/integration/gcs_upload_{_TS}.txt"
_TEST_DATA = {"test": True, "ts": _TS, "msg": "integration test"}


def _backend() -> str:
    from config import get_settings
    from services.storage.gcs import _gcs_available
    s = get_settings()
    if _gcs_available() and s.gcs_bucket:
        return f"GCS (bucket={s.gcs_bucket})"
    return "local-filesystem fallback"


# ── store_json + load_json ────────────────────────────────────────────────────

async def test_store_and_load_json_round_trip():
    """store_json → load_json: saved data matches loaded data."""
    try:
        url = await store_json(_TEST_DATA, _JSON_KEY)
        assert url, f"Expected non-empty URL, got: {repr(url)}"

        result = await load_json(_JSON_KEY)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result["test"] is True
        assert result["ts"] == _TS
        assert result["msg"] == "integration test"
        print(f"  ✓ store_json → load_json round-trip verified ({url})")
    finally:
        try:
            await delete_object(_JSON_KEY)
        except Exception:
            pass


# ── list_keys ─────────────────────────────────────────────────────────────────

async def test_list_keys_includes_stored_key():
    """list_keys returns the key we just stored."""
    try:
        await store_json(_TEST_DATA, _JSON_KEY)
        keys = await list_keys("test/integration/")

        assert isinstance(keys, list), f"Expected list, got {type(keys)}"
        assert _JSON_KEY in keys, (
            f"Expected {_JSON_KEY!r} in keys. Found: {keys[:5]}"
        )
        print(f"  ✓ list_keys: found {len(keys)} key(s), includes test key")
    finally:
        try:
            await delete_object(_JSON_KEY)
        except Exception:
            pass


# ── key_exists ────────────────────────────────────────────────────────────────

async def test_key_exists_true_for_stored_false_for_missing():
    """key_exists: True for stored key, False for a random missing key."""
    try:
        await store_json(_TEST_DATA, _JSON_KEY)

        exists = await key_exists(_JSON_KEY)
        assert exists is True, f"Expected True for stored key, got {exists}"

        missing = await key_exists(f"test/integration/does_not_exist_{_TS}.json")
        assert missing is False, f"Expected False for missing key, got {missing}"

        print("  ✓ key_exists: True for stored key, False for missing key")
    finally:
        try:
            await delete_object(_JSON_KEY)
        except Exception:
            pass


# ── delete_object ─────────────────────────────────────────────────────────────

async def test_delete_object_removes_key():
    """delete_object → key_exists returns False."""
    await store_json(_TEST_DATA, _JSON_KEY)
    assert await key_exists(_JSON_KEY) is True

    await delete_object(_JSON_KEY)
    exists = await key_exists(_JSON_KEY)
    assert exists is False, f"Expected False after delete, got {exists}"
    print("  ✓ delete_object: key no longer exists after deletion")


# ── upload_file + generate_presigned_url ──────────────────────────────────────

async def test_upload_file_and_presigned_url():
    """upload_file with a temp text file; generate_presigned_url returns a URL."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(f"integration test content ts={_TS}")
        tmp_path = tmp.name

    try:
        url = await upload_file(tmp_path, _FILE_KEY, content_type="text/plain")
        assert url, f"Expected non-empty URL, got: {repr(url)}"

        signed = await generate_presigned_url(_FILE_KEY, expires_in=300)
        assert signed, f"Expected non-empty signed URL, got: {repr(signed)}"
        assert "http" in signed, f"Expected HTTP URL, got: {signed}"

        print(f"  ✓ upload_file → {url[:60]}...")
        print(f"  ✓ generate_presigned_url → {signed[:60]}...")
    finally:
        os.unlink(tmp_path)
        try:
            await delete_object(_FILE_KEY)
        except Exception:
            pass


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"  backend: {_backend()}")
    print(f"  test key prefix: test/integration/gcs_test_{_TS}*\n")

    tests = [
        test_store_and_load_json_round_trip,
        test_list_keys_includes_stored_key,
        test_key_exists_true_for_stored_false_for_missing,
        test_delete_object_removes_key,
        test_upload_file_and_presigned_url,
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

    print(f"\n{'─'*44}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
