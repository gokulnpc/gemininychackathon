"""Unit tests for describe_reference_subject — error/guard paths only.

No real API calls made. Safe to run without GCP credentials.

Usage:
    cd backend && .venv/bin/python tests/unit/test_describe_subject.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.gemini.image import describe_reference_subject


async def test_missing_file():
    result = await describe_reference_subject("/tmp/no_such_file_xyzzy.jpg")
    assert result == "", f"Expected '' for missing file, got: {repr(result)}"
    print("  ✓ missing file → ''")


async def test_empty_path():
    result = await describe_reference_subject("")
    assert result == "", f"Expected '' for empty path, got: {repr(result)}"
    print("  ✓ empty path → ''")


async def main() -> None:
    tests = [test_missing_file, test_empty_path]
    passed = failed = 0

    for fn in tests:
        print(f"[{fn.__name__}]")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'─'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
