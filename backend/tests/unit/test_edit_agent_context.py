from __future__ import annotations

import asyncio
import importlib
import sys
import types

from models.schemas import EditAgentRequest, EditorContextRequest, EditorScreenshotContext
from services.gemini.edit_voice import _summarize_editor_context


def test_summarize_editor_context_returns_safe_compact_shape():
    summary = _summarize_editor_context(
        {
            "mode": "text",
            "active_panel": "agent",
            "playhead_seconds": 3.25,
            "viewport_scale": 1.5,
            "selected_element_ids": ["el-1"],
            "selected_track_ids": ["tr-1"],
            "selected_element_types": ["text"],
            "screenshot": {"width": 1080, "height": 1920, "mime_type": "image/png"},
        }
    )

    assert summary["mode"] == "text"
    assert summary["active_panel"] == "agent"
    assert summary["playhead_seconds"] == 3.25
    assert summary["selected_element_ids"] == ["el-1"]
    assert summary["selected_track_ids"] == ["tr-1"]
    assert summary["selected_element_types"] == ["text"]
    assert summary["has_screenshot"] is True
    assert summary["screenshot_dimensions"] == {"width": 1080, "height": 1920}


def test_edit_agent_router_passes_editor_context(monkeypatch):
    captured: dict = {}

    async def fake_get_project_for_user(project_id: str, uid: str) -> dict:
        return {
            "project_id": project_id,
            "status": "completed",
            "voiceover_full_script": "hello world",
        }

    async def fake_run_edit_text_agent(**kwargs):
        captured.update(kwargs)
        yield {"type": "complete", "message": "ok"}

    monkeypatch.setattr(
        "services.storage.firestore_db.get_project_for_user",
        fake_get_project_for_user,
    )
    monkeypatch.setattr(
        "services.gemini.edit_voice.run_edit_text_agent",
        fake_run_edit_text_agent,
    )

    firebase_admin_stub = types.ModuleType("firebase_admin")
    firebase_admin_stub.auth = types.SimpleNamespace(verify_id_token=lambda token: {"uid": "user-1"})
    firebase_admin_stub.credentials = types.SimpleNamespace(Certificate=lambda value: value)
    monkeypatch.setitem(sys.modules, "firebase_admin", firebase_admin_stub)
    deps_auth_stub = types.ModuleType("deps.auth")
    deps_auth_stub.get_current_user = lambda: {"uid": "user-1"}
    monkeypatch.setitem(sys.modules, "deps.auth", deps_auth_stub)

    router_mod = importlib.import_module("routers.voice.edit")

    req = EditAgentRequest(
        instruction="make the intro stronger",
        current_project_json={"tracks": []},
        editor_context=EditorContextRequest(
            mode="select",
            active_panel="agent",
            playhead_seconds=1.25,
            selected_element_ids=["e-1"],
            selected_track_ids=["t-1"],
            selected_element_types=["text"],
            screenshot=EditorScreenshotContext(
                mime_type="image/png",
                image_b64="abc123",
                width=1080,
                height=1920,
            ),
        ),
    )

    async def _run() -> tuple[object, list[object]]:
        response = await router_mod.edit_agent_sse("project-1", req, {"uid": "user-1"})
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return response, chunks

    _, chunks = asyncio.run(_run())

    payload = b"".join(
        chunk if isinstance(chunk, bytes) else chunk.encode()
        for chunk in chunks
    ).decode()

    assert 'data: {"type": "complete", "message": "ok"}' in payload
    assert captured["project_id"] == "project-1"
    assert captured["instruction"] == "make the intro stronger"
    assert captured["current_project_json"] == {"tracks": []}
    assert captured["editor_context"]["mode"] == "select"
    assert captured["editor_context"]["playhead_seconds"] == 1.25
    assert captured["editor_context"]["selected_element_ids"] == ["e-1"]
    assert captured["editor_context"]["screenshot"]["image_b64"] == "abc123"


def test_edit_agent_request_mode_defaults_to_plan():
    req = EditAgentRequest(instruction="make it pop")
    assert req.mode == "plan"
    assert req.commands is None


def test_edit_agent_request_accepts_apply_mode_with_commands():
    from models.schemas import EditCommand, EditCommandKind
    cmd = EditCommand(kind=EditCommandKind.set_caption_style, args={"style": "sleek"})
    req = EditAgentRequest(instruction="apply this", mode="apply", commands=[cmd])
    assert req.mode == "apply"
    assert len(req.commands) == 1
    assert req.commands[0].kind == EditCommandKind.set_caption_style


def test_editor_context_request_accepts_focused_asset_id():
    req = EditorContextRequest(focused_asset_id="asset-abc-123")
    assert req.focused_asset_id == "asset-abc-123"


def test_editor_context_request_focused_asset_id_defaults_to_none():
    req = EditorContextRequest()
    assert req.focused_asset_id is None


def test_edit_agent_sse_plan_mode_passes_through_to_service(monkeypatch):
    """Router must pass mode='plan' and commands=None when not provided."""
    captured: dict = {}

    async def fake_get_project_for_user(project_id: str, uid: str) -> dict:
        return {"project_id": project_id, "status": "completed", "voiceover_full_script": "hello"}

    async def fake_run_edit_text_agent(**kwargs):
        captured.update(kwargs)
        yield {"type": "proposal", "proposal": {"proposal_id": "abc", "summary": "Caption → sleek", "commands": [], "confirmation_required": True}}

    monkeypatch.setattr("services.storage.firestore_db.get_project_for_user", fake_get_project_for_user)
    monkeypatch.setattr("services.gemini.edit_voice.run_edit_text_agent", fake_run_edit_text_agent)

    router_mod = importlib.import_module("routers.voice.edit")

    req = EditAgentRequest(instruction="sleek captions", mode="plan")

    async def _run():
        response = await router_mod.edit_agent_sse("project-1", req, {"uid": "user-1"})
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_run())
    payload = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode()

    assert '"type": "proposal"' in payload
    assert captured.get("mode") == "plan"


def test_edit_agent_sse_apply_mode_passes_commands_to_service(monkeypatch):
    """Router must pass mode='apply' and serialised commands to service."""
    from models.schemas import EditCommand, EditCommandKind
    captured: dict = {}

    async def fake_get_project_for_user(project_id: str, uid: str) -> dict:
        return {"project_id": project_id, "status": "completed", "voiceover_full_script": "hello"}

    async def fake_run_edit_text_agent(**kwargs):
        captured.update(kwargs)
        yield {"type": "applied", "message": "done", "project_json": None, "changes": {}}
        yield {"type": "complete", "message": "done", "project_json": None, "changes": {}}

    monkeypatch.setattr("services.storage.firestore_db.get_project_for_user", fake_get_project_for_user)
    monkeypatch.setattr("services.gemini.edit_voice.run_edit_text_agent", fake_run_edit_text_agent)

    router_mod = importlib.import_module("routers.voice.edit")

    cmd = EditCommand(kind=EditCommandKind.set_caption_style, args={"style": "beast"})
    req = EditAgentRequest(instruction="apply", mode="apply", commands=[cmd])

    async def _run():
        response = await router_mod.edit_agent_sse("project-1", req, {"uid": "user-1"})
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    asyncio.run(_run())

    assert captured.get("mode") == "apply"
    assert isinstance(captured.get("commands"), list)
    assert len(captured["commands"]) == 1
    assert captured["commands"][0]["kind"] == "set_caption_style"
