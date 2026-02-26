import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import auth, generation, pipeline, preset_process, projects, publish, series, smart_process

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Voice-to-Video pipeline — turn a voice memo into a marketing video",
    version="0.1.0",
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
app.include_router(generation.router)
app.include_router(pipeline.router)
app.include_router(publish.router)
app.include_router(series.router)
app.include_router(smart_process.router)
app.include_router(preset_process.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
