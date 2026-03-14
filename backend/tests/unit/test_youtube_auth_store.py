from __future__ import annotations

import json

import pytest

from services.storage import youtube_auth_store


@pytest.mark.asyncio
async def test_youtube_auth_store_local_roundtrip(monkeypatch, patch_settings, tmp_path):
    patch_settings.google_cloud_project = ""
    monkeypatch.setattr(youtube_auth_store, "_LOCAL_STATE_ROOT", tmp_path)

    await youtube_auth_store.save_youtube_credentials(
        uid="user-1",
        credentials_json='{"refresh_token":"refresh-token"}',
        channel_info={"channel_id": "channel-123", "channel_title": "My Channel"},
    )

    record = await youtube_auth_store.get_youtube_auth("user-1")

    assert record is not None
    assert record["uid"] == "user-1"
    assert record["credentials_json"] == '{"refresh_token":"refresh-token"}'
    assert record["channel_id"] == "channel-123"
    assert record["channel_title"] == "My Channel"


@pytest.mark.asyncio
async def test_pending_youtube_oauth_state_local_roundtrip(monkeypatch, patch_settings, tmp_path):
    patch_settings.google_cloud_project = ""
    monkeypatch.setattr(youtube_auth_store, "_LOCAL_STATE_ROOT", tmp_path)

    await youtube_auth_store.create_pending_youtube_oauth_state(
        uid="user-1",
        state="state-123",
        redirect_uri="https://api.example.com/api/v1/auth/youtube/callback",
    )

    pending = await youtube_auth_store.get_pending_youtube_oauth_state("state-123")
    assert pending is not None
    assert pending["uid"] == "user-1"
    assert pending["redirect_uri"] == "https://api.example.com/api/v1/auth/youtube/callback"

    await youtube_auth_store.delete_pending_youtube_oauth_state("state-123")
    assert await youtube_auth_store.get_pending_youtube_oauth_state("state-123") is None
