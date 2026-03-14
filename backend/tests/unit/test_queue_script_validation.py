from __future__ import annotations

from types import SimpleNamespace
import sys
from uuid import uuid4

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


def test_queue_script_rejects_missing_preset():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/projects/{uuid4()}/queue-script",
            json={
                "source": "preset",
                "target_platforms": ["instagram_reels"],
                "video_duration": 20,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "preset is required when source=preset"


def test_queue_script_rejects_empty_transcript():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/projects/{uuid4()}/queue-script",
            json={
                "source": "text",
                "transcript": "   ",
                "target_platforms": ["instagram_reels"],
                "video_duration": 20,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "transcript is required when source=text"


def test_queue_script_accepts_valid_preset(monkeypatch):
    saved: dict = {}

    async def fake_save_project(project_id: str, payload: dict):
        saved["project_id"] = project_id
        saved["payload"] = payload

    async def fake_enqueue_script_generation(project_id: str):
        saved["enqueued_project_id"] = project_id
        return "task-123"

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    monkeypatch.setattr("services.storage.firestore_db.save_project", fake_save_project)
    monkeypatch.setattr("services.infra.task_queue.enqueue_script_generation", fake_enqueue_script_generation)

    project_id = str(uuid4())

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/projects/{project_id}/queue-script",
            json={
                "source": "preset",
                "preset": "marketing_business",
                "target_platforms": ["instagram_reels"],
                "video_duration": 20,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["project_id"] == project_id
    assert saved["project_id"] == project_id
    assert saved["enqueued_project_id"] == project_id
    assert saved["payload"]["pipeline_config"]["preset"] == "marketing_business"
