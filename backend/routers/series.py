"""Series & wizard configuration endpoints.

Provides:
  POST /api/v1/series          — create a series with all wizard settings (stored in S3)
  GET  /api/v1/series          — list all series (for Create Video dropdown)
  GET  /api/v1/voices          — list available ElevenLabs voices
  GET  /api/v1/voices/{id}/preview — return base64 sample audio for a voice
"""
import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from models.schemas import (
    SeriesConfig,
    SeriesCreateResponse,
    SeriesListItem,
    SeriesListResponse,
    VoiceOption,
)
from services import s3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["series"])

# ── Voice catalogue ───────────────────────────────────────────────────────────

VOICE_CATALOGUE: list[VoiceOption] = [
    VoiceOption(id="21m00Tcm4TlvDq8ikWAM", name="Rachel", gender="Female", description="Calm, young American voice — great for lifestyle and wellness."),
    VoiceOption(id="pNInz6obpgDQGcFmaJgB", name="Adam", gender="Male", description="Deep, middle-aged American voice — ideal for authoritative content."),
    VoiceOption(id="TxGEqnHWrfWFTfGW9XjX", name="Josh", gender="Male", description="Young, conversational voice — perfect for casual storytelling."),
    VoiceOption(id="EXAVITQu4vr4xnSDxMaL", name="Bella", gender="Female", description="Soft, gentle voice — suited for calm and mindful content."),
    VoiceOption(id="VR6AewLTigWG4xSOukaG", name="Arnold", gender="Male", description="Crisp, clear voice — great for informative and educational content."),
]

_VOICE_IDS = {v.id for v in VOICE_CATALOGUE}

# Duration range → integer mapping
DURATION_MAP = {
    "15-30": 25,
    "30-40": 35,
    "60+": 60,
}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/series", response_model=SeriesCreateResponse)
async def create_series(config: SeriesConfig):
    """Create a new series with all wizard configuration settings.

    Stores the config as JSON in S3 under series/{series_id}/config.json.
    Returns the series_id to use in subsequent pipeline runs.
    """
    series_id = str(uuid4())
    s3_key = f"series/{series_id}/config.json"

    try:
        config_url = await s3.store_json(config.model_dump(), s3_key)
    except Exception as e:
        logger.exception("Failed to store series config for %s", series_id)
        raise HTTPException(status_code=500, detail=f"Failed to save series config: {e}")

    logger.info("Created series %s (%s)", series_id, config.series_name)
    return SeriesCreateResponse(
        series_id=series_id,
        config=config,
        config_url=config_url,
    )


@router.get("/series", response_model=SeriesListResponse)
async def list_series():
    """List all series configs for the Create Video dropdown.

    Scans S3 for series/{id}/config.json files created by POST /series.
    """
    try:
        all_keys = await s3.list_keys("series/")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list series: {e}")

    series_ids = {
        key.split("/")[1]
        for key in all_keys
        if key.endswith("/config.json") and len(key.split("/")) == 3
    }

    if not series_ids:
        return SeriesListResponse(series=[], total=0)

    async def _load(sid: str) -> SeriesListItem | None:
        try:
            data = await s3.load_json(f"series/{sid}/config.json")
            return SeriesListItem(
                series_id=sid,
                series_name=data.get("series_name", sid),
                video_format=data.get("video_format", "storytelling"),
                niche=data.get("niche"),
                art_style=data.get("art_style", "realism"),
                caption_style=data.get("caption_style", "bold_stroke"),
                background_music=data.get("background_music", "none"),
                voice_id=data.get("voice_id", ""),
                video_duration=data.get("video_duration", "30-40"),
            )
        except Exception:
            return None

    results = await asyncio.gather(*[_load(sid) for sid in series_ids])
    items = [r for r in results if r is not None]
    items.sort(key=lambda x: x.series_name)

    return SeriesListResponse(series=items, total=len(items))


@router.get("/voices", response_model=list[VoiceOption])
async def list_voices():
    """Return all available ElevenLabs voice options with metadata.

    Each voice can be previewed via GET /api/v1/voices/{voice_id}/preview.
    """
    return VOICE_CATALOGUE


