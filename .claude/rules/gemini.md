---
globs: backend/services/gemini_*.py
---

# Gemini API Rules

## Model Registry

| Capability | Model ID | Auth path |
|-----------|----------|-----------|
| Script agent (ReAct) | `gemini-2.5-pro` | Vertex AI on GCP / API key locally |
| Hook research + scoring | `gemini-2.5-pro` | Vertex AI on GCP / API key locally |
| TTS voiceover | `gemini-2.5-flash-preview-tts` | API key (force_api_key=True) |
| Image generation | `gemini-3.1-flash-image-preview` | API key (force_api_key=True) |
| Interleaved text+image | `gemini-2.0-flash-preview-image-generation` | API key (force_api_key=True) |
| Audio transcription | Gemini multimodal (in gemini_audio.py) | API key (force_api_key=True) |

## Auth — Shared Client Factory
**Never create `genai.Client()` directly. Always use the shared factory.**
```python
from services.gemini_client import get_client

# Stable models (2.5 Pro) — Vertex AI on GCP, API key locally:
client = get_client()

# Preview models (image gen, TTS, interleaved, audio) — always API key:
client = get_client(force_api_key=True)
```
- `get_client()` checks `settings.use_vertex_ai` + `settings.google_cloud_project`
- On Cloud Run: `USE_VERTEX_AI=true` → `genai.Client(vertexai=True, project=..., location=...)`
- Locally / preview models: `genai.Client(api_key=settings.gemini_api_key or None)`
- Never hardcode or log API keys

## Interleaved Output — Critical Notes
- Only `gemini-2.0-flash-preview-image-generation` supports `response_modalities=["TEXT", "IMAGE"]`
- Do NOT use `gemini-2.5-flash-image` for interleaved — it's image-only (no text interleaving)
- Prompt must explicitly instruct the model to alternate text and images
- Check each part with `getattr(part, "text", None)` and `getattr(part, "inline_data", None)` — attributes may be absent

## Image Generation
- Use `gemini-3.1-flash-image-preview` for standalone image generation (scenes)
- Pass previous scene image as reference for character consistency
- Target size: 576×1024 (9:16 portrait)

## TTS
- `response_modalities=["AUDIO"]`
- Output: raw PCM16 → wrap in WAV (24kHz, 16-bit mono) via `_pcm_to_wav()`

## Retry Strategy
- Wrap all production Gemini calls with `call_with_retry()` from `services/retry.py`
- Retries on: HTTP 503, 429, 500, connection errors
- Backoff: 2s → 4s → 8s (3 attempts total)
