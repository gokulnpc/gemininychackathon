"""Scout Voice Agent WebSocket router.

WebSocket: /api/v1/voice-agent

Accepts binary PCM16 audio frames (16 kHz mono) from the browser,
streams Scout's PCM16 audio responses back as binary frames, and
sends JSON metadata events (transcripts, tool events, video_ready) as
text frames.

Protocol
--------
Browser → Server:
  binary frames   Raw PCM16 audio bytes (16 kHz mono, push-to-talk or VAD)
  {"type":"done"} User finished speaking — signals end of audio stream

Server → Browser:
  binary frames   Scout's PCM16 voice output (24 kHz mono)
  {"type":"agent_transcript","text":"..."}
  {"type":"tool_event","name":"start_video_generation","project_id":"..."}
  {"type":"video_ready","project_id":"...","video_url":"...","hook":"..."}
  {"type":"error","message":"..."}
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["voice-agent"])

_AUDIO_QUEUE_MAX = 100


@router.websocket("/voice-agent")
async def voice_agent_ws(websocket: WebSocket):
    """Bidirectional Scout voice agent session over WebSocket."""
    await websocket.accept()
    logger.info("Scout voice agent WebSocket connected")

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)

    async def _audio_stream():
        """Async generator that yields audio chunks from the queue."""
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def _on_event(event: dict) -> None:
        """Send a JSON metadata event to the browser."""
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            pass  # WebSocket may be closing

    async def _receive_loop() -> None:
        """Receive browser messages and route them to the audio queue."""
        try:
            while True:
                msg = await websocket.receive()
                if "bytes" in msg and msg["bytes"]:
                    # Drop oldest frame if queue is full (back-pressure relief)
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
                        # Signal end of audio stream
                        await audio_queue.put(None)
                        return
        except WebSocketDisconnect:
            await audio_queue.put(None)
        except Exception as exc:
            logger.warning("Scout receive loop error: %s", exc)
            await audio_queue.put(None)

    receive_task = asyncio.create_task(_receive_loop())

    try:
        from services import gemini_voice_agent as svc

        async for audio_chunk in svc.run_voice_agent(
            audio_chunks=_audio_stream(),
            on_event=_on_event,
        ):
            await websocket.send_bytes(audio_chunk)

        await receive_task

    except WebSocketDisconnect:
        logger.info("Scout voice agent WebSocket disconnected")
    except Exception as exc:
        logger.exception("Scout voice agent error: %s", exc)
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
        logger.info("Scout voice agent session closed")
