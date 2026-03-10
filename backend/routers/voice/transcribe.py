"""Endpoint for audio transcription and tone detection."""

import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.gemini.live import transcribe_base64_audio_live, transcribe_live
from services.gemini.audio import transcribe_with_tone

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
    """Real-time streaming transcription endpoint.
    
    Expects JSON messages:
      { "type": "audio", "data": "<base64_pcm16_16kHz_mono>" }
      { "type": "stop" }
      
    Sends JSON messages:
      { "type": "transcript_chunk", "text": "partial text" }
      { "type": "final_result", "transcript": "...", "detected_tone": "..." }
      { "type": "error", "message": "..." }
    """
    await websocket.accept()

    async def audio_generator():
        try:
            while True:
                msg = await websocket.receive_json()
                if msg.get("type") == "stop":
                    break
                elif msg.get("type") == "audio" and "data" in msg:
                    yield base64.b64decode(msg["data"])
        except WebSocketDisconnect:
            pass

    async def on_transcript_chunk(text: str):
        try:
            await websocket.send_json({"type": "transcript_chunk", "text": text})
        except WebSocketDisconnect:
            pass

    try:
        final_result = await transcribe_live(
            audio_chunks=audio_generator(),
            on_transcript_chunk=on_transcript_chunk,
        )
        await websocket.send_json({
            "type": "final_result",
            "transcript": final_result["transcript"],
            "detected_tone": final_result["detected_tone"]
        })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except WebSocketDisconnect:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
