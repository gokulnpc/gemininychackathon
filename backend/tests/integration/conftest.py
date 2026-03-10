from __future__ import annotations

import os

import pytest


def _live_enabled() -> bool:
    return os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() in {"1", "true", "yes"}


def pytest_collection_modifyitems(config, items):
    """Skip live integration tests unless explicitly enabled.

    Only affects tests collected from the tests/integration/ directory.
    Set RUN_LIVE_INTEGRATION_TESTS=1 to run them.
    """
    if _live_enabled():
        return

    skip_live = pytest.mark.skip(
        reason="Live integration tests disabled. Set RUN_LIVE_INTEGRATION_TESTS=1 to run."
    )
    for item in items:
        if "tests/integration" in str(item.fspath) or "tests\\integration" in str(item.fspath):
            item.add_marker(skip_live)
