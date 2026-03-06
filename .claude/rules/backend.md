---
globs: backend/**/*.py
---

# Backend Coding Rules

## Structure
- New services → `backend/services/<name>.py`
- New API endpoints → `backend/routers/<name>.py` with `prefix="/api/v1/..."`
- Register routers in `backend/main.py` via `app.include_router(...)`
- New Pydantic models → append to `backend/models/schemas.py`
- Config → `backend/config.py` (Settings class, pydantic-settings, `.env`)

## Async Pattern
- All functions calling external APIs must be `async def`
- Synchronous / blocking work: wrap with `asyncio.to_thread(sync_fn, *args)`
- Never call a blocking function directly inside an async context
- Service layer raises exceptions; router layer catches and raises `HTTPException`

## Gemini Client (google-genai ≥ 1.0)
**ALWAYS use the shared factory — never instantiate `genai.Client()` directly.**
```python
from services.gemini_client import get_client

# Stable models (gemini-2.5-pro): Vertex AI on GCP, API key locally
client = get_client()

# Preview models (image gen, TTS, interleaved, audio): always API key
client = get_client(force_api_key=True)
```
- `get_client()` reads `USE_VERTEX_AI` from config — set `true` on Cloud Run
- Sync calls always wrapped in `asyncio.to_thread()`
- Use `call_with_retry()` from `services/retry.py` for production resilience

## Project Metadata — Firestore
Project metadata goes to **Firestore**, not GCS JSON. GCS is for video/audio files only.
```python
from services import firestore_db

# Save / upsert
await firestore_db.save_project(str(project_id), metadata_dict)

# Load (returns dict | None)
data = await firestore_db.get_project(str(project_id))

# List (newest first)
items = await firestore_db.list_projects(limit=100)

# Delete
await firestore_db.delete_project(str(project_id))
```
`firestore_db` falls back to GCS JSON when `GOOGLE_CLOUD_PROJECT` is not set (local dev).

## Interleaved Output (Phase 3 Creative Director)
```python
config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
```
- Model: `gemini-2.0-flash-preview-image-generation`
- Iterate `response.candidates[0].content.parts`
- `part.text` → text block; `part.inline_data` → image block
- `inline_data.data` may be `bytes` or base64 `str` — handle both

## New Feature Checklist
1. Schema(s) in `models/schemas.py`
2. Service in `services/`
3. Router in `routers/`
4. Register router in `main.py`
5. Update `.claude/CLAUDE.md` Service Dependency Map section
6. Use `firestore_db` (not `gcs.store_json`) for project metadata
7. Use `get_client()` / `get_client(force_api_key=True)` — never raw `genai.Client()`

## Style
- `from __future__ import annotations` at top of every module
- Module-level `logger = logging.getLogger(__name__)`
- Constants in UPPER_SNAKE_CASE at module level
- No unused imports; no commented-out dead code
