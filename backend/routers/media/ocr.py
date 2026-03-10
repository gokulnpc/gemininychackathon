"""OCR endpoints — PDF text extraction.

POST /api/v1/ocr-pdf
  Accepts a base64-encoded PDF, returns the extracted text.
  Used by the frontend "Upload Message" button in the Text to Video flow.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ocr"])


class OcrPdfRequest(BaseModel):
    pdf_base64: str


class OcrPdfResponse(BaseModel):
    text: str


@router.post("/ocr-pdf", response_model=OcrPdfResponse)
async def ocr_pdf(request: OcrPdfRequest) -> OcrPdfResponse:
    """Extract text from a PDF using Gemini multimodal (or Document AI if configured)."""
    if not request.pdf_base64:
        raise HTTPException(status_code=400, detail="pdf_base64 is required")

    try:
        from services.content.document_ai import extract_text_from_pdf
        text = await extract_text_from_pdf(request.pdf_base64)
    except Exception as exc:
        logger.exception("PDF text extraction failed")
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {exc}") from exc

    return OcrPdfResponse(text=text)
