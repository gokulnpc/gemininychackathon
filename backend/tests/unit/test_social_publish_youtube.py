from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.integrations import social_publish


@pytest.mark.asyncio
async def test_publish_youtube_requires_connected_account(monkeypatch):
    async def fake_download_file(gcs_key: str, local_path: str):
        Path(local_path).write_bytes(b"fake-video")
        return local_path

    async def fake_get_credentials(uid: str):
        assert uid == "user-1"
        return None

    monkeypatch.setattr(social_publish.gcs_service, "download_file", fake_download_file)
    monkeypatch.setattr("services.storage.youtube_auth_store.get_youtube_credentials_json", fake_get_credentials)

    result = await social_publish._publish_youtube(
        project_id="project-1",
        uid="user-1",
        title="My title",
        description="My description",
        tags=[],
    )

    assert result["platform"] == "youtube"
    assert result["status"] == "failed"
    assert "not connected" in result["error"].lower()


@pytest.mark.asyncio
async def test_publish_youtube_persists_refreshed_token(monkeypatch):
    saved_credentials: list[dict] = []

    async def fake_download_file(gcs_key: str, local_path: str):
        Path(local_path).write_bytes(b"fake-video")
        return local_path

    async def fake_get_credentials(uid: str):
        assert uid == "user-1"
        return '{"refresh_token":"refresh-token","token":"old-token"}'

    async def fake_save_credentials(uid: str, credentials_json: str, channel_info: dict | None = None):
        saved_credentials.append({
            "uid": uid,
            "credentials_json": credentials_json,
            "channel_info": channel_info,
        })

    class DummyCreds:
        expired = True
        refresh_token = "refresh-token"

        def refresh(self, request):
            self.expired = False

        def to_json(self):
            return '{"refresh_token":"refresh-token","token":"new-token"}'

    class DummyMediaUpload:
        def __init__(self, filename: str, mimetype: str, resumable: bool):
            self.filename = filename

    class DummyRequest:
        def __init__(self):
            self._done = False

        def next_chunk(self):
            if self._done:
                return None, {"id": "video-123"}
            self._done = True
            return None, None

    class DummyVideos:
        def insert(self, part: str, body: dict, media_body):
            return DummyRequest()

    class DummyYouTube:
        def videos(self):
            return DummyVideos()

    monkeypatch.setattr(social_publish.gcs_service, "download_file", fake_download_file)
    monkeypatch.setattr("services.storage.youtube_auth_store.get_youtube_credentials_json", fake_get_credentials)
    monkeypatch.setattr("services.storage.youtube_auth_store.save_youtube_credentials", fake_save_credentials)
    monkeypatch.setitem(
        sys.modules,
        "google.auth.transport.requests",
        SimpleNamespace(Request=lambda: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "google.oauth2.credentials",
        SimpleNamespace(Credentials=SimpleNamespace(from_authorized_user_info=lambda info, scopes: DummyCreds())),
    )
    monkeypatch.setitem(
        sys.modules,
        "googleapiclient.discovery",
        SimpleNamespace(build=lambda service, version, credentials=None: DummyYouTube()),
    )
    monkeypatch.setitem(
        sys.modules,
        "googleapiclient.http",
        SimpleNamespace(MediaFileUpload=DummyMediaUpload),
    )

    result = await social_publish._publish_youtube(
        project_id="project-1",
        uid="user-1",
        title="My title",
        description="My description",
        tags=[],
    )

    assert result == {
        "platform": "youtube",
        "status": "published",
        "post_url": "https://www.youtube.com/watch?v=video-123",
    }
    assert saved_credentials == [
        {
            "uid": "user-1",
            "credentials_json": '{"refresh_token":"refresh-token","token":"new-token"}',
            "channel_info": None,
        }
    ]
