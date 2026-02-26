from fastapi import APIRouter, HTTPException

from models.schemas import TranscribeRequest, TranscribeResponse

router = APIRouter(prefix="/api/v1", tags=["generation"])


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    raise HTTPException(status_code=501, detail="Transcription service not configured.")
