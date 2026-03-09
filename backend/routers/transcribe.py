"""Endpoint for audio transcription and tone detection."""

from fastapi import APIRouter
from pydantic import BaseModel

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
