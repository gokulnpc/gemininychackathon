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
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from firebase_admin import auth as firebase_auth
from starlette.websockets import WebSocket, WebSocketDisconnect

from deps.auth import get_current_user
from models.schemas import EditAgentRequest
from services.storage import firestore_db

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

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
    decision_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=5)
    live_state: dict = {
        "project_json": project_data.get("project_json"),
        "editor_context": None,
    }

    async def _audio_stream():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def _on_event(event: dict) -> None:
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            pass

    async def _receive_loop() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if "bytes" in msg and msg["bytes"]:
                    if audio_queue.full():
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    audio_queue.put_nowait(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "done":
                        await audio_queue.put(None)
                        return
                    if data.get("type") == "editor_state":
                        live_state["project_json"] = data.get("project_json")
                        live_state["editor_context"] = data.get("editor_context")
                    elif data.get("type") == "agent_decision":
                        if not decision_queue.full():
                            decision_queue.put_nowait(data)
        except WebSocketDisconnect:
            await audio_queue.put(None)
        except Exception as exc:
            logger.warning("Edit voice receive loop error: %s", exc)
            await audio_queue.put(None)

    receive_task = asyncio.create_task(_receive_loop())

    try:
        from services.gemini import edit_voice as svc

        async for audio_chunk in svc.run_edit_voice_agent(
            project_id=project_id,
            project_data=project_data,
            audio_chunks=_audio_stream(),
            get_live_state=lambda: dict(live_state),
            on_event=_on_event,
            decision_queue=decision_queue,
        ):
            await websocket.send_bytes(audio_chunk)

        await receive_task

    except WebSocketDisconnect:
        logger.info("Edit voice WebSocket disconnected: project=%s", project_id)
    except Exception as exc:
        logger.exception("Edit voice agent error: project=%s error=%s", project_id, exc)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        receive_task.cancel()
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
