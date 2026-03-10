import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from routers.auth.auth import router as auth_router
from routers.users.users import router as users_router
from routers.projects.projects import router as projects_router
from routers.projects.catalog import router as catalog_router
from routers.generation.script import router as script_router
from routers.generation.video import router as video_router
from routers.generation.recompose import router as recompose_router
from routers.generation.creative_director import router as creative_director_router
from routers.publishing.publish import router as publish_router
from routers.voice.transcribe import router as transcribe_router
from routers.voice.live import router as live_router
from routers.voice.agent import router as voice_agent_router
from routers.voice.edit import router as edit_voice_router
from routers.media.assets import router as assets_router
from routers.media.ocr import router as ocr_router
from routers.internal.worker import router as worker_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Content Factory — turn a voice memo into a marketing video",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(catalog_router)
app.include_router(script_router)
app.include_router(video_router)
app.include_router(publish_router)
app.include_router(creative_director_router)
app.include_router(recompose_router)
app.include_router(live_router)
app.include_router(voice_agent_router)
app.include_router(edit_voice_router)
app.include_router(transcribe_router)
app.include_router(ocr_router)
app.include_router(worker_router)   # internal Cloud Tasks callbacks (not in public docs)
app.include_router(assets_router)

# Serve locally generated videos when GCS is not configured
_outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(_outputs_dir, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=_outputs_dir), name="outputs")

# Serve art style reference images and other static assets
_assets_dir = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(_assets_dir, exist_ok=True)
app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/health")
async def health():
    return {"status": "ok"}
