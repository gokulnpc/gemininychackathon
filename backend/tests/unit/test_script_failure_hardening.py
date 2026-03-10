from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import config
from routers.internal.worker import _run_script_generation
from routers.projects.projects import retry_script
from services.gemini import agent as agent_mod
from services.infra import task_queue


def _tool_event(name: str):
    return SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(function_call=SimpleNamespace(name=name))]
        )
    )


@pytest.fixture()
def patch_agent_settings(monkeypatch, test_settings):
    config.get_settings.cache_clear()

    def _get_settings():
        return test_settings

    _get_settings.cache_clear = lambda: None
    monkeypatch.setattr(config, "get_settings", _get_settings)
    return test_settings


@pytest.mark.unit
def test_classify_script_agent_failure_agent_no_finalize():
    failure = agent_mod._classify_script_agent_failure("finalize_script was not called")
    assert failure.error_code == "agent_no_finalize"
    assert failure.retryable is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_script_agent_retries_once_then_completes(patch_agent_settings, monkeypatch):
    finalized_script = {
        "hook": {"text": "Hook", "duration": 3},
        "scenes": [{"scene_id": 1, "duration_seconds": 5, "voiceover_text": "Scene", "visual_prompt": "Prompt", "emotion": "calm"}],
        "cta": {"text": "CTA", "type": "verbal_and_visual"},
        "social_copy": {},
        "quality_score": 88,
        "agent_reasoning": "reasoning",
        "character_description": "character",
    }

    class FakeSessionService:
        def __init__(self):
            self.sessions: dict[str, dict] = {}

        async def create_session(self, app_name: str, user_id: str, session_id: str):
            self.sessions[session_id] = {}

        async def get_session(self, app_name: str, user_id: str, session_id: str):
            return SimpleNamespace(state=self.sessions[session_id])

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

    class FakeRunner:
        def __init__(self, agent, app_name, session_service):
            self.session_service = session_service

        async def run_async(self, user_id: str, session_id: str, new_message):
            if len(self.session_service.sessions) == 1:
                yield _tool_event("search_trending_hooks")
            else:
                self.session_service.sessions[session_id]["finalized_script"] = finalized_script
                yield _tool_event("finalize_script")

    monkeypatch.setattr(agent_mod, "InMemorySessionService", FakeSessionService)
    monkeypatch.setattr(agent_mod, "Agent", FakeAgent)
    monkeypatch.setattr(agent_mod, "Runner", FakeRunner)

    events = []
    async for event in agent_mod.stream_script_agent(
        transcript="money tips",
        target_platforms=["instagram_reels"],
        video_duration=20,
    ):
        events.append(event)

    assert [event["type"] for event in events] == ["agent_step", "retry", "agent_step", "complete"]
    assert events[1]["attempt"] == 2
    assert events[-1]["script"]["hook"]["text"] == "Hook"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_script_agent_emits_structured_error_after_retry(patch_agent_settings, monkeypatch):
    class FakeSessionService:
        def __init__(self):
            self.sessions: dict[str, dict] = {}

        async def create_session(self, app_name: str, user_id: str, session_id: str):
            self.sessions[session_id] = {}

        async def get_session(self, app_name: str, user_id: str, session_id: str):
            return SimpleNamespace(state=self.sessions[session_id])

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

    class FakeRunner:
        def __init__(self, agent, app_name, session_service):
            self.session_service = session_service

        async def run_async(self, user_id: str, session_id: str, new_message):
            yield _tool_event("search_trending_hooks")

    monkeypatch.setattr(agent_mod, "InMemorySessionService", FakeSessionService)
    monkeypatch.setattr(agent_mod, "Agent", FakeAgent)
    monkeypatch.setattr(agent_mod, "Runner", FakeRunner)

    events = []
    async for event in agent_mod.stream_script_agent(
        transcript="history fact",
        target_platforms=["instagram_reels"],
        video_duration=20,
    ):
        events.append(event)

    assert events[-1]["type"] == "error"
    assert events[-1]["error_code"] == "agent_no_finalize"
    assert events[-1]["retryable"] is True
    assert "finalize" in events[-1]["debug_hint"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_script_generation_persists_failure_metadata(monkeypatch):
    saved_docs: list[dict] = []
    doc = {
        "project_id": "proj-1",
        "uid": "user-1",
        "status": "queued",
        "pipeline_config": {
            "source": "text",
            "transcript": "test transcript",
            "target_platforms": ["instagram_reels"],
            "video_duration": 20,
        },
    }

    async def _get_project(project_id: str):
        return doc

    async def _save_project(project_id: str, payload: dict):
        saved_docs.append(payload.copy())

    async def _fake_stream_script_agent(**kwargs):
        yield {
            "type": "retry",
            "attempt": 2,
            "message": "Retrying script generation with a fresh Scout session…",
            "error_code": "agent_no_finalize",
            "retryable": True,
            "progress_pct": 18,
        }
        yield {
            "type": "error",
            "message": "Scout did not finalize a script on this run.",
            "error_code": "agent_no_finalize",
            "retryable": True,
            "debug_hint": "The ADK session ended without finalize_script being called.",
        }

    monkeypatch.setattr("services.storage.firestore_db.get_project", _get_project)
    monkeypatch.setattr("services.storage.firestore_db.save_project", _save_project)
    monkeypatch.setattr("services.gemini.agent.stream_script_agent", _fake_stream_script_agent)

    with pytest.raises(agent_mod.ScriptAgentFailure):
        await _run_script_generation("proj-1")

    final_doc = saved_docs[-1]
    assert final_doc["status"] == "failed"
    assert final_doc["error_code"] == "agent_no_finalize"
    assert final_doc["retryable"] is True
    assert final_doc["failure_stage"] == "script_generation"
    assert final_doc["script_attempt_count"] == 2
    assert final_doc["last_error_code"] == "agent_no_finalize"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_script_requeues_failed_project(monkeypatch):
    project_id = uuid4()
    saved_payloads: list[dict] = []

    async def _get_project_for_user(project_id_str: str, uid: str):
        return {
            "project_id": project_id_str,
            "uid": uid,
            "status": "failed",
            "pipeline_config": {"source": "text", "transcript": "hello"},
            "error": "Scout did not finalize a script on this run.",
            "error_code": "agent_no_finalize",
            "retryable": True,
        }

    async def _save_project(project_id_str: str, payload: dict):
        saved_payloads.append(payload.copy())

    async def _enqueue_script_generation(project_id_str: str):
        return "local-inprocess"

    monkeypatch.setattr("services.storage.firestore_db.get_project_for_user", _get_project_for_user)
    monkeypatch.setattr("services.storage.firestore_db.save_project", _save_project)
    monkeypatch.setattr("services.infra.task_queue.enqueue_script_generation", _enqueue_script_generation)

    response = await retry_script(project_id=project_id, current_user={"uid": "user-1"})

    assert response.status_code == 202
    assert saved_payloads[-1]["status"] == "queued"
    assert saved_payloads[-1]["error"] is None
    assert saved_payloads[-1]["error_code"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_spawn_local_task_retrieves_exception(caplog):
    caplog.set_level("ERROR")

    async def _boom():
        raise RuntimeError("boom")

    task_queue._spawn_local_task(_boom(), description="script generation for project test")
    await pytest.importorskip("asyncio").sleep(0)
    await pytest.importorskip("asyncio").sleep(0)

    assert "Local background task failed" in caplog.text
