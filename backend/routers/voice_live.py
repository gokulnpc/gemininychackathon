"""Live voice transcription — WebSocket endpoint.

WebSocket: /api/v1/projects/{project_id}/live-voice

Browser streams raw PCM16 mic audio (16kHz mono) → server pipes to Gemini Live API
→ real-time transcript chunks streamed back → on complete, returns full transcript
+ detected_tone so the browser can call POST /generate-script with source=text.

The file-upload voice flow (source=voice with audio_base64) is unchanged.

Client protocol
---------------
  → binary frame        raw PCM16 audio chunk (16kHz mono, no container)
  → JSON {"type":"done"} recording stopped, no more audio coming

Server protocol
---------------
  ← {"type":"transcript_chunk","text":"..."}          incremental transcript
  ← {"type":"complete","transcript":"...","detected_tone":"...","language":"en-US"}
  ← {"type":"error","message":"..."}                   on failure
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["voice-live"])


@router.websocket("/projects/{project_id}/live-voice")
async def live_voice(websocket: WebSocket, project_id: UUID):
    """Stream mic audio and receive real-time transcript + tone."""
    await websocket.accept()
    logger.info("Live voice session started (project=%s)", project_id)

    # Queue bridges the WebSocket receive loop and the Gemini Live send loop.
    # None is used as a sentinel to signal end of stream.
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _audio_stream():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def _on_chunk(text: str) -> None:
        await websocket.send_text(
            json.dumps({"type": "transcript_chunk", "text": text})
        )

    async def _receive_loop() -> None:
        """Read WebSocket frames and push audio bytes to the queue."""
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    await audio_queue.put(message["bytes"])
                elif "text" in message and message["text"]:
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "done":
                        await audio_queue.put(None)  # sentinel → close stream
                        return
        except WebSocketDisconnect:
            await audio_queue.put(None)

    try:
        from services import gemini_live as gemini_live_svc

        receive_task = asyncio.create_task(_receive_loop())

        result = await gemini_live_svc.transcribe_live(
            audio_chunks=_audio_stream(),
            on_transcript_chunk=_on_chunk,
        )

        await receive_task  # ensure receive loop is fully done

        await websocket.send_text(json.dumps({"type": "complete", **result}))
        logger.info(
            "Live voice session complete (project=%s, chars=%d, tone=%s)",
            project_id, len(result.get("transcript", "")), result.get("detected_tone"),
        )

    except WebSocketDisconnect:
        logger.info("Live voice WebSocket disconnected (project=%s)", project_id)
    except Exception as exc:
        logger.exception("Live voice error (project=%s): %s", project_id, exc)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
