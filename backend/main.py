import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from routers import auth, catalog, creative_director, projects, publish, recompose, script, video, worker

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

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(catalog.router)
app.include_router(script.router)
app.include_router(video.router)
app.include_router(publish.router)
app.include_router(creative_director.router)
app.include_router(recompose.router)
app.include_router(worker.router)   # internal Cloud Tasks callbacks (not in public docs)

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
