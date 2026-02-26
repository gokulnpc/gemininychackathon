import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import auth, catalog, projects, publish, script, video

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


@app.get("/health")
async def health():
    return {"status": "ok"}
