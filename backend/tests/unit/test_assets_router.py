from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from routers.media import assets as assets_router


@pytest.mark.asyncio
async def test_list_assets_returns_empty_when_storage_listing_fails(monkeypatch):
    async def _boom(prefix: str):
        raise RuntimeError(f"boom: {prefix}")

    monkeypatch.setattr(assets_router.gcs, "list_keys", _boom)

    response = await assets_router.list_assets(category="images", current_user={"uid": "user-123"})

    assert response == {"assets": []}


@pytest.mark.asyncio
async def test_list_assets_skips_non_dict_metadata(monkeypatch):
    async def _keys(prefix: str):
        return [f"{prefix}a/meta.json", f"{prefix}b/meta.json"]

    async def _load_json(key: str):
        if key.endswith("a/meta.json"):
            return {"id": "a", "uploaded_at": "2026-03-11T00:00:00Z"}
        return ["unexpected"]

    monkeypatch.setattr(assets_router.gcs, "list_keys", _keys)
    monkeypatch.setattr(assets_router.gcs, "load_json", _load_json)

    response = await assets_router.list_assets(category="images", current_user={"uid": "user-123"})

    assert response == {"assets": [{"id": "a", "uploaded_at": "2026-03-11T00:00:00Z"}]}
