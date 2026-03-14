from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import sys

from fastapi.testclient import TestClient

sys.modules.setdefault(
    "firebase_admin",
    SimpleNamespace(
        _apps=[object()],
        initialize_app=lambda *args, **kwargs: None,
        auth=SimpleNamespace(verify_id_token=lambda token: {"uid": "test"}),
        credentials=SimpleNamespace(ApplicationDefault=lambda: None),
    ),
)

from deps.auth import get_current_user
from main import app


class DummyCredentials:
    def __init__(self, payload: str):
        self._payload = payload

    def to_json(self) -> str:
        return self._payload


class DummyFlow:
    def __init__(self, redirect_uri: str, state: str | None = None):
        self.redirect_uri = redirect_uri
        self.state = state
        self.credentials = DummyCredentials('{"token":"new-token"}')
        self.fetch_token_calls: list[str] = []

    def authorization_url(self, access_type: str, prompt: str):
        return "https://accounts.example/auth", "state-123"

    def fetch_token(self, code: str):
        self.fetch_token_calls.append(code)


def test_youtube_auth_init_persists_pending_state(monkeypatch):
    saved_pending: dict = {}
    fake_flow = DummyFlow("https://api.example.com/api/v1/auth/youtube/callback")

    async def fake_create_pending(uid: str, state: str, redirect_uri: str):
        saved_pending.update({"uid": uid, "state": state, "redirect_uri": redirect_uri})

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    monkeypatch.setattr("routers.auth.auth._build_youtube_flow", lambda redirect_uri, state=None: fake_flow)
    monkeypatch.setattr(
        "services.storage.youtube_auth_store.create_pending_youtube_oauth_state",
        fake_create_pending,
    )

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/auth/youtube",
            params={"redirect_uri": "https://api.example.com/api/v1/auth/youtube/callback"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "auth_url": "https://accounts.example/auth",
        "state": "state-123",
    }
    assert saved_pending == {
        "uid": "user-1",
        "state": "state-123",
        "redirect_uri": "https://api.example.com/api/v1/auth/youtube/callback",
    }


def test_youtube_auth_status_is_user_scoped(monkeypatch):
    async def fake_get_credentials(uid: str):
        assert uid == "user-1"
        return '{"refresh_token":"refresh-token"}'

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    monkeypatch.setattr(
        "services.storage.youtube_auth_store.get_youtube_credentials_json",
        fake_get_credentials,
    )
    monkeypatch.setattr("routers.auth.auth._youtube_credentials_valid", lambda credentials_json: True)

    try:
        client = TestClient(app)
        response = client.get("/api/v1/auth/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["youtube"] is True


def test_youtube_callback_saves_credentials_for_correct_user(monkeypatch):
    saved: dict = {}
    deleted_states: list[str] = []
    fake_flow = DummyFlow("https://api.example.com/api/v1/auth/youtube/callback", state="state-123")

    async def fake_get_pending(state: str):
        assert state == "state-123"
        return {
            "uid": "user-1",
            "state": state,
            "redirect_uri": "https://api.example.com/api/v1/auth/youtube/callback",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def fake_save(uid: str, credentials_json: str, channel_info: dict | None = None):
        saved.update({
            "uid": uid,
            "credentials_json": credentials_json,
            "channel_info": channel_info,
        })

    async def fake_delete(state: str):
        deleted_states.append(state)

    monkeypatch.setattr("services.storage.youtube_auth_store.get_pending_youtube_oauth_state", fake_get_pending)
    monkeypatch.setattr("services.storage.youtube_auth_store.save_youtube_credentials", fake_save)
    monkeypatch.setattr("services.storage.youtube_auth_store.delete_pending_youtube_oauth_state", fake_delete)
    monkeypatch.setattr("routers.auth.auth._build_youtube_flow", lambda redirect_uri, state=None: fake_flow)
    monkeypatch.setattr(
        "routers.auth.auth._fetch_youtube_channel_info",
        lambda credentials: {"channel_id": "channel-123", "channel_title": "My Channel"},
    )

    client = TestClient(app)
    response = client.get("/api/v1/auth/youtube/callback", params={"code": "abc123", "state": "state-123"})

    assert response.status_code == 200
    assert "YouTube Connected" in response.text
    assert fake_flow.fetch_token_calls == ["abc123"]
    assert saved == {
        "uid": "user-1",
        "credentials_json": '{"token":"new-token"}',
        "channel_info": {"channel_id": "channel-123", "channel_title": "My Channel"},
    }
    assert deleted_states == ["state-123"]
