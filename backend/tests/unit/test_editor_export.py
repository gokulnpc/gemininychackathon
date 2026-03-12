from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services.infra import editor_export


def test_normalize_render_media_src_rewrites_known_source_types(monkeypatch):
    monkeypatch.setattr(
        editor_export,
        "get_settings",
        lambda: SimpleNamespace(
            frontend_public_base_url="https://app.example",
            api_public_base_url="https://api.example",
        ),
    )

    assert editor_export.normalize_render_media_src("https://cdn.example/video.mp4") == "https://cdn.example/video.mp4"
    assert editor_export.normalize_render_media_src("gs://demo-bucket/scenes/scene-1.png") == (
        "https://storage.googleapis.com/demo-bucket/scenes/scene-1.png"
    )
    assert editor_export.normalize_render_media_src("/music/quiet_before_storm.mp3") == (
        "https://app.example/music/quiet_before_storm.mp3"
    )
    assert editor_export.normalize_render_media_src("/assets/image.png") == "https://api.example/assets/image.png"
    assert editor_export.normalize_render_media_src("/outputs/render/master.mp4") == (
        "https://api.example/outputs/render/master.mp4"
    )


def test_normalize_project_json_for_render_deep_copies_and_normalizes_media(monkeypatch):
    monkeypatch.setattr(
        editor_export,
        "get_settings",
        lambda: SimpleNamespace(
            frontend_public_base_url="https://frontend.local",
            api_public_base_url="https://api.local",
        ),
    )

    original = {
        "tracks": [
            {
                "id": "track-1",
                "elements": [
                    {"id": "image-1", "type": "image", "props": {"src": "/music/theme.mp3"}},
                    {"id": "image-2", "type": "image", "props": {"src": "gs://bucket/scene.png"}},
                    {"id": "effect-1", "type": "effect", "props": {"effectKey": "sepia"}},
                ],
            }
        ]
    }

    normalized = editor_export.normalize_project_json_for_render(original)

    assert normalized is not original
    assert normalized["tracks"][0]["elements"][0]["props"]["src"] == "https://frontend.local/music/theme.mp3"
    assert normalized["tracks"][0]["elements"][1]["props"]["src"] == "https://storage.googleapis.com/bucket/scene.png"
    assert normalized["tracks"][0]["elements"][2]["props"]["effectKey"] == "sepia"
    assert original["tracks"][0]["elements"][0]["props"]["src"] == "/music/theme.mp3"


def test_build_editor_export_state_merges_existing_values():
    merged = editor_export.build_editor_export_state(
        {"export_id": "old", "status": "queued", "queued_at": "2026-03-12T00:00:00Z"},
        status="completed",
        download_url="https://cdn.example/export.mp4",
    )

    assert merged["export_id"] == "old"
    assert merged["status"] == "completed"
    assert merged["queued_at"] == "2026-03-12T00:00:00Z"
    assert merged["download_url"] == "https://cdn.example/export.mp4"


def test_append_editor_export_history_adds_completed_export_and_sorts_latest_first():
    snapshot = {"tracks": [{"id": "track-1"}]}
    history = editor_export.append_editor_export_history(
        [
            {
                "export_id": "old-export",
                "completed_at": "2026-03-11T12:00:00Z",
                "download_url": "https://cdn.example/old.mp4",
                "project_json_snapshot": {"tracks": [{"id": "old"}]},
            }
        ],
        export_id="new-export",
        completed_at="2026-03-12T12:00:00Z",
        download_url="https://cdn.example/new.mp4",
        project_json_snapshot=snapshot,
    )

    assert [item["export_id"] for item in history] == ["new-export", "old-export"]
    assert history[0]["download_url"] == "https://cdn.example/new.mp4"
    assert history[0]["project_json_snapshot"] == snapshot
    assert history[0]["project_json_snapshot"] is not snapshot


def test_append_editor_export_history_deduplicates_existing_export_id():
    snapshot = {"tracks": [{"id": "new"}]}
    history = editor_export.append_editor_export_history(
        [
            {
                "export_id": "same-export",
                "completed_at": "2026-03-11T12:00:00Z",
                "download_url": "https://cdn.example/old.mp4",
                "project_json_snapshot": {"tracks": [{"id": "old"}]},
            }
        ],
        export_id="same-export",
        completed_at="2026-03-12T12:00:00Z",
        download_url="https://cdn.example/new.mp4",
        project_json_snapshot=snapshot,
    )

    assert history == [
        {
            "export_id": "same-export",
            "completed_at": "2026-03-12T12:00:00Z",
            "download_url": "https://cdn.example/new.mp4",
            "thumbnail_url": None,
            "project_json_snapshot": snapshot,
        }
    ]


def test_render_timeline_to_file_calls_remote_worker_with_oidc(monkeypatch, tmp_path):
    captured: dict = {}

    class DummyResponse:
        status_code = 200
        content = b"video-bytes"
        text = ""
        reason_phrase = "OK"

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    monkeypatch.setattr(
        editor_export,
        "get_settings",
        lambda: SimpleNamespace(
            timeline_render_worker_url="https://voicevid-render.example.run.app",
            frontend_public_base_url="https://frontend.example",
            api_public_base_url="https://api.example",
        ),
    )
    monkeypatch.setattr(editor_export, "_fetch_render_service_id_token", lambda audience: f"token-for:{audience}")
    monkeypatch.setattr(editor_export.httpx, "AsyncClient", lambda timeout=None: DummyClient())

    output_path = tmp_path / "render.mp4"
    project_json = {
        "tracks": [
            {"elements": [{"props": {"src": "/music/theme.mp3"}}]},
        ]
    }

    result = asyncio.run(
        editor_export.render_timeline_to_file(project_json=project_json, output_path=str(output_path))
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"video-bytes"
    assert captured["url"] == "https://voicevid-render.example.run.app/render"
    assert captured["headers"]["Authorization"] == "Bearer token-for:https://voicevid-render.example.run.app"
    assert captured["json"]["projectJson"]["tracks"][0]["elements"][0]["props"]["src"] == (
        "https://frontend.example/music/theme.mp3"
    )
