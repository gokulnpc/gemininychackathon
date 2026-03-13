"""Endpoint for audio transcription and tone detection."""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.gemini.live import transcribe_live
from services.gemini.audio import transcribe_with_tone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcribe"])


class TranscribeRequest(BaseModel):
    audio_base64: str
    audio_format: str = "webm"
    language: str = "en"


class TranscribeResponse(BaseModel):
    transcript: str
    detected_tone: str
    language: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """Transcribe audio and detect emotional tone using Gemini 2.5 Pro."""
    result = await transcribe_with_tone(
        audio_b64=request.audio_base64,
        audio_format=request.audio_format,
    )
    return TranscribeResponse(**result)


@router.websocket("/transcribe/ws")
async def transcribe_websocket(websocket: WebSocket):
    """Real-time streaming transcription endpoint (live-voice binary protocol).

    Expects:
      → binary frames   raw PCM16 audio (16kHz mono, no container)
      → JSON {"type":"done"}   recording stopped, no more audio

    Sends:
      ← {"type":"transcript_chunk","text":"..."}   incremental transcript
      ← {"type":"complete","transcript":"...","detected_tone":"..."}
      ← {"type":"error","message":"..."}
    """
    await websocket.accept()

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)

    async def _audio_stream():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def _receive_loop() -> None:
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    if audio_queue.full():
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    audio_queue.put_nowait(message["bytes"])
                elif "text" in message and message["text"]:
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "done":
                        await audio_queue.put(None)
                        return
        except WebSocketDisconnect:
            await audio_queue.put(None)

    async def on_transcript_chunk(text: str):
        if websocket.client_state.value != 1:  # 1 is CONNECTED
            return
        try:
            await websocket.send_json({"type": "transcript_chunk", "text": text})
        except Exception:
            pass

    try:
        receive_task = asyncio.create_task(_receive_loop())
        
        # We wrap the main logic to ensure cleanup even on failure
        final_result = await transcribe_live(
            audio_chunks=_audio_stream(),
            on_transcript_chunk=on_transcript_chunk,
        )
        
        # Stop receive loop if it's still waiting
        if not receive_task.done():
            receive_task.cancel()
        
        await websocket.send_json({"type": "complete", **final_result})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.exception("Transcription WebSocket failed")
        if websocket.client_state.value == 1:
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
