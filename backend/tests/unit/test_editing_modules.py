from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock

import pytest

from services.gemini.editing import preview as preview_mod
from services.gemini.editing.text_runtime import run_edit_text_agent
from services.gemini.editing.voice_runtime import _dispatch_voice_tool


@pytest.mark.asyncio
async def test_generate_quick_preview_streams_first_block(monkeypatch):
    events: list[dict] = []

    def fake_invoke(prompt: str) -> list[dict]:
        assert "creepy comic" in prompt.lower()
        return [
            {"type": "image", "content": "abc", "mime_type": "image/png"},
            {"type": "image", "content": "def", "mime_type": "image/png"},
        ]

    async def on_event(event: dict) -> None:
        events.append(event)

    monkeypatch.setattr(preview_mod, "_invoke_quick_preview", fake_invoke)

    result = await preview_mod._generate_quick_preview(
        brief="A creepy comic alleyway",
        art_style="creepy comic",
        on_event=on_event,
    )

    assert result == {"status": "completed", "total_images": 2}
    assert events == [{
        "type": "creative_block",
        "block": {"type": "image", "content": "abc", "mime_type": "image/png"},
        "block_index": 0,
        "total_blocks": 1,
    }]


@pytest.mark.asyncio
async def test_generate_quick_preview_returns_error_on_failure(monkeypatch):
    def fake_invoke(prompt: str) -> list[dict]:
        raise RuntimeError("preview failed")

    monkeypatch.setattr(preview_mod, "_invoke_quick_preview", fake_invoke)

    result = await preview_mod._generate_quick_preview("broken preview")

    assert result == {"error": "preview failed"}


@pytest.mark.asyncio
async def test_dispatch_voice_tool_drafts_command():
    draft_commands: list[dict] = []
    on_event = AsyncMock()

    result = await _dispatch_voice_tool(
        name="draft_edit_command",
        args={"kind": "set_caption_style", "args": {"style": "karaoke"}},
        project_id="proj-1",
        project_data={},
        draft_commands=draft_commands,
        current_project_json={},
        editor_context=None,
        on_event=on_event,
    )

    assert result == {
        "drafted": {
            "kind": "set_caption_style",
            "args": {"style": "karaoke"},
        }
    }
    assert draft_commands == [{
        "kind": "set_caption_style",
        "args": {"style": "karaoke"},
    }]


@pytest.mark.asyncio
async def test_run_edit_text_agent_apply_mode_uses_projector(monkeypatch):
    patched_json = {"tracks": [{"id": "track-1"}]}
    project_commands = AsyncMock(return_value=(patched_json, {"caption_style": "sleek"}, []))
    apply_live_edits = AsyncMock(return_value={
        "message": "Done",
        "changes": {"caption_style": "sleek"},
        "project_json": patched_json,
        "editor_context": {"mode": "text"},
        "requires_export": True,
    })

    monkeypatch.setattr("services.gemini.editing.text_runtime._project_commands", project_commands)
    monkeypatch.setattr("services.gemini.editing.text_runtime._apply_live_edits", apply_live_edits)

    events = [
        event
        async for event in run_edit_text_agent(
            project_id="proj-1",
            project_data={"hook": "hello"},
            instruction="apply",
            current_project_json={"tracks": []},
            editor_context={"mode": "text"},
            mode="apply",
            commands=[{"kind": "set_caption_style", "args": {"style": "sleek"}}],
            uid="user-1",
        )
    ]

    assert [event["type"] for event in events] == ["agent_step", "applied", "complete"]
    project_commands.assert_awaited_once()
    apply_live_edits.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_edit_text_agent_plan_mode_emits_proposal(monkeypatch):
    class FakeSessionService:
        def __init__(self):
            self.state: dict = {}

        async def create_session(self, *, state: dict, **_: object) -> None:
            self.state = state

        async def get_session(self, **_: object):
            return types.SimpleNamespace(state=self.state)

    class FakeAgent:
        def __init__(self, **_: object):
            pass

    class FakeRunner:
        def __init__(self, *, session_service: FakeSessionService, **_: object):
            self.session_service = session_service

        async def run_async(self, **_: object):
            self.session_service.state["draft_commands"] = [
                {"kind": "set_caption_style", "args": {"style": "beast"}},
            ]
            event = types.SimpleNamespace(
                content=types.SimpleNamespace(
                    parts=[
                        types.SimpleNamespace(
                            function_call=types.SimpleNamespace(name="draft_edit_command")
                        )
                    ]
                )
            )
            yield event

    class FakeContent:
        def __init__(self, role: str, parts: list[object]):
            self.role = role
            self.parts = parts

    class FakePart:
        def __init__(self, text: str):
            self.text = text

    monkeypatch.setattr("services.gemini.editing.text_runtime.settings_env", lambda: None)

    agents_mod = types.ModuleType("google.adk.agents")
    agents_mod.Agent = FakeAgent
    runners_mod = types.ModuleType("google.adk.runners")
    runners_mod.Runner = FakeRunner
    sessions_mod = types.ModuleType("google.adk.sessions")
    sessions_mod.InMemorySessionService = FakeSessionService
    genai_mod = types.ModuleType("google.genai")
    genai_mod.types = types.SimpleNamespace(Content=FakeContent, Part=FakePart)

    monkeypatch.setitem(sys.modules, "google.adk.agents", agents_mod)
    monkeypatch.setitem(sys.modules, "google.adk.runners", runners_mod)
    monkeypatch.setitem(sys.modules, "google.adk.sessions", sessions_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)

    events = [
        event
        async for event in run_edit_text_agent(
            project_id="proj-1",
            project_data={"hook": "hello", "caption_style": "beast"},
            instruction="make captions beast",
            current_project_json={"tracks": []},
            editor_context={"mode": "text"},
            mode="plan",
            uid="",
        )
    ]

    assert events[0] == {
        "type": "agent_step",
        "tool": "draft_edit_command",
        "message": "Drafting edit command...",
    }
    assert events[1]["type"] == "proposal"
    assert events[1]["proposal"]["commands"] == [
        {"kind": "set_caption_style", "args": {"style": "beast"}},
    ]
    assert events[2]["type"] == "complete"
