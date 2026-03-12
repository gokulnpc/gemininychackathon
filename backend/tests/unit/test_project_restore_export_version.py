from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from deps.auth import get_current_user
from main import app

PROJECT_ID = "2d319253-81b0-4f18-8070-bad4573c8473"


def test_restore_export_version_replaces_project_json(monkeypatch):
    saved_payload: dict = {}
    original_project_json = {"tracks": [{"id": "current-track"}]}
    restored_project_json = {"tracks": [{"id": "restored-track"}]}
    project_doc = {
        "uid": "user-1",
        "project_id": PROJECT_ID,
        "status": "completed",
        "video_urls": {"instagram_reels": "https://cdn.example/original.mp4"},
        "project_json": deepcopy(original_project_json),
        "editor_export_history": [
            {
                "export_id": "export-1",
                "completed_at": "2026-03-12T12:00:00Z",
                "download_url": "https://cdn.example/export-1.mp4",
                "project_json_snapshot": deepcopy(restored_project_json),
            }
        ],
    }

    async def fake_get_project_for_user(project_id: str, uid: str) -> dict:
        assert project_id == PROJECT_ID
        assert uid == "user-1"
        return deepcopy(project_doc)

    async def fake_save_project(project_id: str, payload: dict) -> None:
        saved_payload["project_id"] = project_id
        saved_payload["payload"] = deepcopy(payload)

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    monkeypatch.setattr("services.storage.firestore_db.get_project_for_user", fake_get_project_for_user)
    monkeypatch.setattr("services.storage.firestore_db.save_project", fake_save_project)

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/restore-export-version",
            json={"export_id": "export-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert saved_payload["project_id"] == PROJECT_ID
    assert saved_payload["payload"]["project_json"] == restored_project_json
    assert saved_payload["payload"]["video_urls"] == {"instagram_reels": "https://cdn.example/original.mp4"}
    assert saved_payload["payload"]["editor_export_history"][0]["export_id"] == "export-1"


def test_restore_export_version_rejects_unknown_or_non_restorable_export(monkeypatch):
    project_doc = {
        "uid": "user-1",
        "project_id": PROJECT_ID,
        "status": "completed",
        "project_json": {"tracks": [{"id": "current-track"}]},
        "editor_export_history": [
            {
                "export_id": "export-without-snapshot",
                "completed_at": "2026-03-12T12:00:00Z",
                "download_url": "https://cdn.example/export.mp4",
                "project_json_snapshot": None,
            }
        ],
    }

    async def fake_get_project_for_user(project_id: str, uid: str) -> dict:
        return deepcopy(project_doc)

    async def fake_save_project(project_id: str, payload: dict) -> None:
        raise AssertionError("save_project should not be called for unknown restore target")

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    monkeypatch.setattr("services.storage.firestore_db.get_project_for_user", fake_get_project_for_user)
    monkeypatch.setattr("services.storage.firestore_db.save_project", fake_save_project)

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/restore-export-version",
            json={"export_id": "missing-export"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Restorable export version not found"
