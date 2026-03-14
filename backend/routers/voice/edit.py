"""Edit Voice router — AI-powered video editing via voice or text.

WebSocket: /api/v1/projects/{project_id}/edit-voice
  Scout (Live API voice agent) edits an existing completed project through
  natural-language voice conversation. Streams Scout's voice audio back as binary
  frames and sends JSON events (transcripts, creative blocks, edit_complete) as
  text frames.

SSE: POST /api/v1/projects/{project_id}/edit-agent
  Text-based quick-action endpoint. Accepts a natural-language instruction,
  streams ADK agent tool-call progress as SSE, returns new video URL on completion.
  Used by quick action buttons (Change Captions, Change Music).

Guard conditions (both endpoints):
  404 — project not found
  409 — project status != "completed"
  422 — voiceover_full_script missing (pre-dates recompose support)
"""

from __future__ import annotations

import asyncio
import base64
from collections import deque
import contextlib
import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from firebase_admin import auth as firebase_auth
from starlette.websockets import WebSocket, WebSocketDisconnect

from deps.auth import get_current_user
from models.schemas import EditAgentRequest
from services.storage import firestore_db

if TYPE_CHECKING:
    from services.gemini.editing.voice_runtime import VoiceRealtimeEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["edit-voice"])

_AUDIO_QUEUE_MAX = 100


# ── Shared project loader ───────────────────────────────────────────────────────

async def _load_project(project_id: str) -> dict:
    """Load and validate a completed project from Firestore."""
    data = await firestore_db.get_project(project_id)
    if not data:
        raise HTTPException(status_code=404, detail="Project not found")
    if data.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Project must be completed before editing (current status: {data.get('status')})",
        )
    if not data.get("voiceover_full_script"):
        raise HTTPException(
            status_code=422,
            detail="voiceover_full_script is missing — re-run generate-video for this project",
        )
    return data


# ── WebSocket — Voice Edit ──────────────────────────────────────────────────────

@router.websocket("/projects/{project_id}/edit-voice")
async def edit_voice_ws(project_id: str, websocket: WebSocket, token: str | None = Query(default=None)):
    """Scout voice edit session for a completed project."""
    await websocket.accept()

    # ── Auth ──────────────────────────────────────────────────────────────────
    if not token:
        await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized: token required"}))
        await websocket.close(code=4001)
        return
    try:
        claims = firebase_auth.verify_id_token(token)
        uid = claims["uid"]
    except Exception:
        await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized: invalid token"}))
        await websocket.close(code=4001)
        return

    # ── Ownership + project validation ────────────────────────────────────────
    try:
        project_data = await firestore_db.get_project_for_user(project_id, uid)
        if project_data.get("status") != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Project must be completed before editing (current status: {project_data.get('status')})",
            )
        if not project_data.get("voiceover_full_script"):
            raise HTTPException(
                status_code=422,
                detail="voiceover_full_script is missing — re-run generate-video for this project",
            )
    except HTTPException as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": exc.detail}))
        await websocket.close()
        return

    logger.info("Scout edit voice WebSocket connected: project=%s", project_id)

    audio_queue: asyncio.Queue["VoiceRealtimeEvent"] = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
    decision_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=5)
    frame_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=10)
    screen_share_state: dict[str, bool] = {"active": False}
    live_state: dict = {
        "project_json": project_data.get("project_json"),
        "editor_context": None,
    }
    event_counts: dict[str, int] = {}
    session_failed = False

    def _record_event(kind: str) -> None:
        event_counts[kind] = event_counts.get(kind, 0) + 1

    def _drop_oldest_audio_event() -> bool:
        queue_storage = getattr(audio_queue, "_queue", None)
        if not isinstance(queue_storage, deque):
            return False

        for index, queued_event in enumerate(queue_storage):
            if queued_event["kind"] != "audio":
                continue
            queue_storage.rotate(-index)
            dropped = queue_storage.popleft()
            queue_storage.rotate(index)
            logger.warning(
                "Scout edit voice queue full: dropped queued kind=%s project=%s depth=%d",
                dropped["kind"],
                project_id,
                audio_queue.qsize(),
            )
            return True

        return False

    async def _enqueue_realtime_event(event: "VoiceRealtimeEvent") -> None:
        nonlocal session_failed
        kind = event["kind"]
        if session_failed and kind != "done":
            logger.debug(
                "Scout edit voice ignoring event after failure: kind=%s turn=%s project=%s",
                kind,
                event.get("turn_id"),
                project_id,
            )
            return

        _record_event(kind)
        if audio_queue.full():
            if kind == "audio":
                logger.warning(
                    "Scout edit voice queue full: dropped incoming audio project=%s depth=%d",
                    project_id,
                    audio_queue.qsize(),
                )
                return
            if not _drop_oldest_audio_event():
                await audio_queue.put(event)
                logger.debug(
                    "Scout edit voice queued control kind=%s turn=%s count=%d depth=%d project=%s",
                    kind,
                    event.get("turn_id"),
                    event_counts[kind],
                    audio_queue.qsize(),
                    project_id,
                )
                return

        audio_queue.put_nowait(event)
        logger.debug(
            "Scout edit voice queued kind=%s turn=%s count=%d depth=%d project=%s",
            kind,
            event.get("turn_id"),
            event_counts[kind],
            audio_queue.qsize(),
            project_id,
        )

    async def _on_event(event: dict) -> None:
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            pass

    async def _on_ready(transport: str) -> None:
        await _on_event({"type": "ready", "transport": transport})

    async def _on_audio(chunk: bytes) -> None:
        """Forward Gemini audio to client as base64 JSON text frame (Livewire protocol)."""
        b64 = base64.b64encode(chunk).decode()
        try:
            await websocket.send_text(json.dumps({"type": "audio", "data": b64}))
        except Exception:
            pass

    async def _receive_loop() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if "bytes" in msg and msg["bytes"]:
                    # Legacy binary audio frames — still supported
                    logger.debug("Scout edit voice legacy audio frame project=%s bytes=%d", project_id, len(msg["bytes"]))
                    await _enqueue_realtime_event({
                        "kind": "audio",
                        "audio_b64": base64.b64encode(msg["bytes"]).decode(),
                    })
                elif "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "done":
                        logger.info("Scout edit voice client done project=%s", project_id)
                        await _enqueue_realtime_event({"kind": "done"})
                        return
                    elif data.get("type") == "audio":
                        turn_id = str(data.get("turn_id")) if data.get("turn_id") else None
                        b64_str = data.get("data")
                        if b64_str and isinstance(b64_str, str):
                            await _enqueue_realtime_event({
                                "kind": "audio",
                                "audio_b64": b64_str,
                                **({"turn_id": turn_id} if turn_id else {}),
                            })
                    elif data.get("type") == "activity_start":
                        turn_id = str(data.get("turn_id")) if data.get("turn_id") else None
                        logger.info("Scout edit voice client activity_start project=%s turn=%s", project_id, turn_id)
                        await _enqueue_realtime_event({
                            "kind": "activity_start",
                            **({"turn_id": turn_id} if turn_id else {}),
                        })
                    elif data.get("type") == "activity_end":
                        turn_id = str(data.get("turn_id")) if data.get("turn_id") else None
                        logger.info("Scout edit voice client activity_end project=%s turn=%s", project_id, turn_id)
                        await _enqueue_realtime_event({
                            "kind": "activity_end",
                            **({"turn_id": turn_id} if turn_id else {}),
                        })
                    elif data.get("type") == "screen_share_start":
                        screen_share_state["active"] = True
                        logger.info("Scout edit voice screen share started: project=%s", project_id)
                        await _enqueue_realtime_event({"kind": "screen_share_started"})
                    elif data.get("type") == "screen_share_end":
                        screen_share_state["active"] = False
                        logger.info("Scout edit voice screen share ended: project=%s", project_id)
                        # Drain any buffered frames
                        while not frame_queue.empty():
                            with contextlib.suppress(asyncio.QueueEmpty):
                                frame_queue.get_nowait()
                    elif data.get("type") == "inspect_screen":
                        if screen_share_state["active"]:
                            await _enqueue_realtime_event({
                                "kind": "send_text",
                                "text": (
                                    "Please analyze my screen carefully. "
                                    "What do you see? Note any visual improvements I could make to the video — "
                                    "things like text positioning, caption style, music fit, contrast, pacing, "
                                    "or anything that looks off. Be specific. Maximum 3 sentences."
                                ),
                            })
                    elif data.get("type") == "screen_frame" and screen_share_state["active"]:
                        b64 = data.get("data")
                        if b64 and isinstance(b64, str):
                            try:
                                raw = base64.b64decode(b64)
                                if frame_queue.full():
                                    with contextlib.suppress(asyncio.QueueEmpty):
                                        frame_queue.get_nowait()
                                frame_queue.put_nowait(raw)
                            except Exception:
                                pass
                    elif data.get("type") == "editor_state":
                        live_state["project_json"] = data.get("project_json")
                        live_state["editor_context"] = data.get("editor_context")
                    elif data.get("type") == "agent_decision":
                        if not decision_queue.full():
                            decision_queue.put_nowait(data)
        except WebSocketDisconnect:
            await _enqueue_realtime_event({"kind": "done"})
        except Exception as exc:
            logger.warning("Edit voice receive loop error: %s", exc)
            await _enqueue_realtime_event({"kind": "done"})
        finally:
            # Unblock frame_queue consumer
            with contextlib.suppress(Exception):
                frame_queue.put_nowait(None)

    try:
        from services.gemini import edit_voice as svc

        agent_task = asyncio.create_task(
            svc.run_edit_voice_agent(
                project_id=project_id,
                project_data=project_data,
                audio_queue=audio_queue,
                get_live_state=lambda: dict(live_state),
                on_event=_on_event,
                on_audio=_on_audio,
                on_ready=_on_ready,
                decision_queue=decision_queue,
                uid=uid,
                frame_queue=frame_queue,
            )
        )
        receive_task = asyncio.create_task(_receive_loop())

        done, pending = await asyncio.wait(
            {agent_task, receive_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if agent_task in done:
            exc = agent_task.exception()
            if exc is not None:
                session_failed = True
                receive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await receive_task
                raise exc

            receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await receive_task

        if receive_task in done:
            await agent_task

    except WebSocketDisconnect:
        logger.info("Edit voice WebSocket disconnected: project=%s", project_id)
    except Exception as exc:
        session_failed = True
        logger.exception("Edit voice agent error: project=%s error=%s", project_id, exc)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
        with contextlib.suppress(Exception):
            await websocket.close()
    finally:
        session_failed = True
        # Unblock the receive loop if agent exited first
        with contextlib.suppress(Exception):
            await _enqueue_realtime_event({"kind": "done"})
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Edit voice session closed: project=%s", project_id)


# ── SSE — Text Edit (Quick Actions) ────────────────────────────────────────────

@router.post("/projects/{project_id}/edit-agent")
async def edit_agent_sse(project_id: str, req: EditAgentRequest, current_user: dict = Depends(get_current_user)):
    """Stream AI video edit agent progress as SSE.

    Send a natural-language instruction; Scout interprets it, queues the
    appropriate recompose parameters, applies them, and returns the new video URL.

    Quick action button examples:
      {"instruction": "make the captions more aggressive"}
      {"instruction": "change the music to something dark and atmospheric"}
      {"instruction": "switch to karaoke captions and quiet_before_storm music"}
    """
    project_data = await firestore_db.get_project_for_user(project_id, current_user["uid"])
    if project_data.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Project must be completed to edit")
    if not project_data.get("voiceover_full_script"):
        raise HTTPException(status_code=422, detail="voiceover_full_script missing — re-run generate-video first")

    async def event_gen():
        try:
            from services.gemini import edit_voice as svc
            async for event in svc.run_edit_text_agent(
                project_id=project_id,
                project_data=project_data,
                instruction=req.instruction,
                current_project_json=req.current_project_json,
                editor_context=req.editor_context.model_dump(exclude_none=True) if req.editor_context else None,
                mode=req.mode,
                commands=[c.model_dump() for c in req.commands] if req.commands else None,
                uid=current_user["uid"],
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("SSE edit agent failed: project=%s", project_id)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
