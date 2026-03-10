"""PDF text extraction service for Content Factory.

Two-tier strategy:
  1. Gemini multimodal (default, zero-config) — send PDF inline, ask for text extraction.
     Works with just GEMINI_API_KEY.
  2. Google Document AI (upgrade path) — set DOCUMENT_AI_PROCESSOR_ID in .env for
     more accurate OCR on complex layouts and scanned documents.
"""

from __future__ import annotations

import asyncio
import base64
import logging

logger = logging.getLogger(__name__)


async def extract_text_from_pdf(pdf_base64: str) -> str:
    """Extract all text from a base64-encoded PDF.

    Args:
        pdf_base64: Base64-encoded PDF bytes.

    Returns:
        Extracted text string.

    Raises:
        RuntimeError: if extraction fails.
    """
    from config import get_settings
    settings = get_settings()

    if settings.document_ai_processor_id and settings.google_cloud_project:
        logger.info("Using Google Document AI for PDF extraction")
        return await _extract_with_document_ai(pdf_base64, settings)

    logger.info("Using Gemini multimodal for PDF extraction")
    return await _extract_with_gemini(pdf_base64)


async def _extract_with_gemini(pdf_base64: str) -> str:
    """Extract text using Gemini's native PDF understanding."""
    from google.genai import types
    from services.gemini.client import get_client

    client = get_client(force_api_key=True)
    pdf_bytes = base64.b64decode(pdf_base64)

    def _run() -> str:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(
                        mime_type="application/pdf",
                        data=pdf_bytes,
                    )),
                    types.Part(text=(
                        "Extract all text from this PDF document. "
                        "Return only the extracted text, preserving paragraph structure. "
                        "Do not add any commentary or formatting markup."
                    )),
                ])
            ],
        )
        return response.text or ""

    text = await asyncio.to_thread(_run)
    logger.info("Gemini PDF extraction: %d chars extracted", len(text))
    return text


async def _extract_with_document_ai(pdf_base64: str, settings) -> str:
    """Extract text using Google Document AI."""
    try:
        from google.cloud import documentai_v1 as documentai
    except ImportError as exc:
        logger.warning(
            "google-cloud-documentai not installed — falling back to Gemini: %s", exc
        )
        return await _extract_with_gemini(pdf_base64)

    pdf_bytes = base64.b64decode(pdf_base64)

    def _run() -> str:
        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(
            settings.google_cloud_project,
            settings.document_ai_location,
            settings.document_ai_processor_id,
        )
        raw_doc = documentai.RawDocument(
            content=pdf_bytes,
            mime_type="application/pdf",
        )
        result = client.process_document(
            request=documentai.ProcessRequest(name=name, raw_document=raw_doc)
        )
        return result.document.text or ""

    text = await asyncio.to_thread(_run)
    logger.info("Document AI PDF extraction: %d chars extracted", len(text))
    return text
