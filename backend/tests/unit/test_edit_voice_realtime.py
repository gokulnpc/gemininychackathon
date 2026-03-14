from __future__ import annotations

import asyncio
import base64
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.gemini.editing.voice_runtime import (
    _build_voice_config,
    _resolve_live_transport,
    _send_realtime_event,
    run_edit_voice_agent,
)


class FakeRealtimeSession:
    def __init__(self):
        self.calls: list[dict] = []

    async def send_realtime_input(self, **kwargs):
        self.calls.append(kwargs)


def _audio_part(data: bytes):
    return SimpleNamespace(inline_data=SimpleNamespace(data=data), text=None, thought=False)


def _text_part(text: str):
    return SimpleNamespace(inline_data=None, text=text, thought=False)


class FakeLiveSession:
    def __init__(self, *, stall_on_turns: set[int] | None = None):
        self.realtime_calls: list[dict] = []
        self.tool_response_calls: list[dict] = []
        self._responses: asyncio.Queue = asyncio.Queue()
        self._turn_count = 0
        self._stall_on_turns = stall_on_turns or set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send_realtime_input(self, **kwargs):
        self.realtime_calls.append(kwargs)

        if kwargs.get("activity_start") is not None:
            self._turn_count += 1
            return

        if kwargs.get("activity_end") is not None:
            turn_index = self._turn_count
            if turn_index in self._stall_on_turns:
                return

            await self._responses.put(
                SimpleNamespace(
                    server_content=SimpleNamespace(
                        model_turn=None,
                        input_transcription=SimpleNamespace(text=f"user turn {turn_index}"),
                        output_transcription=None,
                        interrupted=False,
                        generation_complete=False,
                        turn_complete=False,
                    ),
                    tool_call=None,
                    text=None,
                    data=None,
                )
            )
            if turn_index == 1:
                await self._responses.put(
                    SimpleNamespace(
                        server_content=None,
                        tool_call=SimpleNamespace(
                            function_calls=[
                                SimpleNamespace(id="fc-1", name="get_project_info", args={})
                            ]
                        ),
                        text=None,
                        data=None,
                    )
                )
            await self._responses.put(
                SimpleNamespace(
                    server_content=SimpleNamespace(
                        model_turn=SimpleNamespace(
                            parts=[
                                _audio_part(b"\x00\x01"),
                                _text_part(f"agent turn {turn_index}"),
                            ]
                        ),
                        input_transcription=None,
                        output_transcription=None,
                        interrupted=False,
                        generation_complete=False,
                        turn_complete=False,
                    ),
                    tool_call=None,
                    text=None,
                    data=None,
                )
            )
            await self._responses.put(
                SimpleNamespace(
                    server_content=SimpleNamespace(
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=None,
                        interrupted=False,
                        generation_complete=True,
                        turn_complete=False,
                    ),
                    tool_call=None,
                    text=None,
                    data=None,
                )
            )
            await self._responses.put(
                SimpleNamespace(
                    server_content=SimpleNamespace(
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=None,
                        interrupted=False,
                        generation_complete=False,
                        turn_complete=True,
                    ),
                    tool_call=None,
                    text=None,
                    data=None,
                )
            )

    async def send_tool_response(self, **kwargs):
        self.tool_response_calls.append(kwargs)

    async def receive(self):
        while True:
            item = await self._responses.get()
            yield item


class FakeLiveConnector:
    def __init__(self, sessions: list[FakeLiveSession]):
        self._sessions = deque(sessions)

    def connect(self, **_kwargs):
        if not self._sessions:
            raise RuntimeError("No fake live session available")
        return self._sessions.popleft()


class FakeClient:
    def __init__(self, sessions: list[FakeLiveSession]):
        self.aio = SimpleNamespace(live=FakeLiveConnector(sessions))


@pytest.mark.asyncio
async def test_send_realtime_event_forwards_activity_and_audio_without_audio_stream_end():
    session = FakeRealtimeSession()
    audio_b64 = base64.b64encode(b"\x01\x02\x03\x04").decode()

    await _send_realtime_event(session, {"kind": "activity_start", "turn_id": "turn-1"}, allow_audio_stream_end=False)
    await _send_realtime_event(session, {"kind": "audio", "audio_b64": audio_b64, "turn_id": "turn-1"}, allow_audio_stream_end=False)
    await _send_realtime_event(session, {"kind": "activity_end", "turn_id": "turn-1"}, allow_audio_stream_end=False)
    await _send_realtime_event(session, {"kind": "done"}, allow_audio_stream_end=False)

    assert session.calls[0]["activity_start"] is not None
    assert session.calls[1]["audio"].data == b"\x01\x02\x03\x04"
    assert session.calls[2]["activity_end"] is not None
    assert len(session.calls) == 3
    assert all("audio_stream_end" not in call for call in session.calls)


def test_build_voice_config_enables_explicit_vad_signal_for_vertex():
    config = _build_voice_config(
        {"hook": "Test Hook", "caption_style": "beast", "background_music": "none"},
        "vertex",
    )
    dumped = config.model_dump(exclude_none=True)

    assert dumped["explicit_vad_signal"] is True
    assert dumped["realtime_input_config"]["automatic_activity_detection"]["disabled"] is True
    assert dumped["realtime_input_config"]["activity_handling"] == "START_OF_ACTIVITY_INTERRUPTS"
    assert dumped["realtime_input_config"]["turn_coverage"] == "TURN_INCLUDES_ONLY_ACTIVITY"


def test_build_voice_config_uses_minimal_manual_vad_for_gemini_api():
    config = _build_voice_config(
        {"hook": "Test Hook", "caption_style": "beast", "background_music": "none"},
        "gemini_api",
    )
    dumped = config.model_dump(exclude_none=True)
    realtime_config = dumped["realtime_input_config"]

    assert "explicit_vad_signal" not in dumped
    assert realtime_config["automatic_activity_detection"]["disabled"] is True
    assert "activity_handling" not in realtime_config
    assert "turn_coverage" not in realtime_config


def test_resolve_live_transport_prefers_vertex_when_enabled(patch_settings):
    patch_settings.use_vertex_ai = True
    patch_settings.google_cloud_project = "story-labs-factory"
    assert _resolve_live_transport() == "vertex"


def test_resolve_live_transport_falls_back_to_gemini_api(patch_settings):
    patch_settings.use_vertex_ai = False
    assert _resolve_live_transport() == "gemini_api"


@pytest.mark.asyncio
async def test_run_edit_voice_agent_handles_two_turns_with_model_turn_parts(monkeypatch, patch_settings):
    fake_session = FakeLiveSession()
    fake_client = FakeClient([fake_session])
    on_event = AsyncMock()
    on_audio = AsyncMock()
    on_ready = AsyncMock()
    dispatch_tool = AsyncMock(return_value={"hook": "demo", "background_music": "none"})

    patch_settings.use_vertex_ai = False
    monkeypatch.setattr("services.gemini.client.get_client", lambda force_api_key=False: fake_client)
    monkeypatch.setattr("services.gemini.editing.voice_runtime._dispatch_voice_tool", dispatch_tool)

    audio_queue: asyncio.Queue = asyncio.Queue()
    for event in (
        {"kind": "activity_start", "turn_id": "turn-1"},
        {"kind": "audio", "audio_b64": base64.b64encode(b"first-turn").decode(), "turn_id": "turn-1"},
        {"kind": "activity_end", "turn_id": "turn-1"},
        {"kind": "activity_start", "turn_id": "turn-2"},
        {"kind": "audio", "audio_b64": base64.b64encode(b"second-turn").decode(), "turn_id": "turn-2"},
        {"kind": "activity_end", "turn_id": "turn-2"},
        {"kind": "done"},
    ):
        await audio_queue.put(event)

    await run_edit_voice_agent(
        project_id="project-1",
        project_data={"hook": "demo"},
        audio_queue=audio_queue,
        get_live_state=lambda: {"project_json": {}, "editor_context": None},
        on_event=on_event,
        on_audio=on_audio,
        on_ready=on_ready,
        uid="user-1",
    )

    event_types = [call.args[0]["type"] for call in on_event.await_args_list]
    assert event_types.count("user_transcript") == 2
    assert event_types.count("agent_transcript") == 2
    assert event_types.count("generation_complete") == 2
    assert event_types.count("turn_complete") == 2
    assert any(call.args[0]["type"] == "turn_complete" and call.args[0]["turn_id"] == "turn-1" for call in on_event.await_args_list)
    assert any(call.args[0]["type"] == "turn_complete" and call.args[0]["turn_id"] == "turn-2" for call in on_event.await_args_list)

    assert dispatch_tool.await_count == 1
    assert len(fake_session.tool_response_calls) == 1
    assert on_audio.await_count == 2
    on_ready.assert_awaited_once_with("gemini_api")
    assert all("audio_stream_end" not in call for call in fake_session.realtime_calls)


@pytest.mark.asyncio
async def test_run_edit_voice_agent_recovers_after_stall(monkeypatch, patch_settings):
    first_session = FakeLiveSession(stall_on_turns={1})
    second_session = FakeLiveSession()
    fake_client = FakeClient([first_session, second_session])
    on_event = AsyncMock()
    on_audio = AsyncMock()
    on_ready = AsyncMock()

    patch_settings.use_vertex_ai = False
    monkeypatch.setattr("services.gemini.client.get_client", lambda force_api_key=False: fake_client)
    monkeypatch.setattr("services.gemini.editing.voice_runtime._dispatch_voice_tool", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr("services.gemini.editing.voice_runtime._STALL_TIMEOUT_SECONDS", 0.05)

    audio_queue: asyncio.Queue = asyncio.Queue()
    for event in (
        {"kind": "activity_start", "turn_id": "turn-1"},
        {"kind": "audio", "audio_b64": base64.b64encode(b"stalled-turn").decode(), "turn_id": "turn-1"},
        {"kind": "activity_end", "turn_id": "turn-1"},
    ):
        await audio_queue.put(event)

    async def _close_after_recovery():
        await asyncio.sleep(0.15)
        await audio_queue.put({"kind": "done"})

    producer = asyncio.create_task(_close_after_recovery())
    try:
        await run_edit_voice_agent(
            project_id="project-1",
            project_data={"hook": "demo"},
            audio_queue=audio_queue,
            get_live_state=lambda: {"project_json": {}, "editor_context": None},
            on_event=on_event,
            on_audio=on_audio,
            on_ready=on_ready,
            uid="user-1",
        )
    finally:
        await producer

    event_types = [call.args[0]["type"] for call in on_event.await_args_list]
    assert "session_recovering" in event_types
    assert "session_restarted" in event_types
    on_ready.assert_awaited_once_with("gemini_api")
    assert all("audio_stream_end" not in call for call in first_session.realtime_calls)
    assert all("audio_stream_end" not in call for call in second_session.realtime_calls)
