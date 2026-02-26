"""Content catalog — configuration presets, tone options, and saved series.

Provides:
  GET  /api/v1/presets         — list available content presets (for preset flow)
  GET  /api/v1/tones           — list selectable tone/style options
  POST /api/v1/series          — save a series config to S3
  GET  /api/v1/series          — list saved series configs
"""
import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from models.schemas import (
    PresetKey,
    SeriesConfig,
    SeriesCreateResponse,
    SeriesListItem,
    SeriesListResponse,
    ToneOption,
)
from services import gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["catalog"])

# ── Duration range → integer seconds ──────────────────────────────────────────
# Imported by routers/script.py and routers/video.py

DURATION_MAP = {
    "15-30": 25,
    "30-40": 35,
    "60+":   60,
}

# ── Tone catalogue ─────────────────────────────────────────────────────────────
# IDs match the detected_tone values returned by gemini_audio.transcribe_with_tone().
# Flow 1 (voice): Gemini auto-detects tone from audio.
# Flow 2 (text) and Flow 3 (preset): user picks from this list.

TONE_CATALOGUE: list[ToneOption] = [
    ToneOption(
        id="excited",
        name="Excited",
        description="High energy, enthusiastic delivery — great for product reveals and exciting news.",
    ),
    ToneOption(
        id="conversational",
        name="Conversational",
        description="Friendly, casual tone — ideal for storytelling, vlogs, and personal content.",
    ),
    ToneOption(
        id="storytelling",
        name="Storytelling",
        description="Narrative, immersive pacing — perfect for true crime, history, and dramatic stories.",
    ),
    ToneOption(
        id="authoritative",
        name="Authoritative",
        description="Confident, expert delivery — best for business, finance, and how-to content.",
    ),
    ToneOption(
        id="dramatic",
        name="Dramatic",
        description="Intense, cinematic tone — great for horror, suspense, and emotional moments.",
    ),
    ToneOption(
        id="calm",
        name="Calm",
        description="Measured, soothing tone — perfect for wellness, meditation, and educational content.",
    ),
    ToneOption(
        id="urgent",
        name="Urgent",
        description="Fast-paced, high-stakes delivery — effective for warnings, deadlines, and calls to action.",
    ),
]

# ── Preset catalogue ──────────────────────────────────────────────────────────

_PRESET_CATALOGUE: list[dict] = [
    {"key": PresetKey.scary_stories.value,      "name": "Scary Stories",        "niche": "horror",      "description": "Chilling psychological horror with atmospheric dread and suspense."},
    {"key": PresetKey.history.value,             "name": "History",              "niche": "history",     "description": "Fascinating lesser-known historical events that changed the world."},
    {"key": PresetKey.true_crime.value,          "name": "True Crime",           "niche": "true_crime",  "description": "Gripping real crime stories — mysteries, disappearances, notorious cases."},
    {"key": PresetKey.stoic_motivation.value,    "name": "Stoic Motivation",     "niche": "motivation",  "description": "Stoic philosophy wisdom to overcome adversity and live with purpose."},
    {"key": PresetKey.marketing_business.value,  "name": "Marketing & Business", "niche": "business",    "description": "Actionable marketing insights and entrepreneurship lessons."},
    {"key": PresetKey.tech_innovation.value,     "name": "Tech & Innovation",    "niche": "technology",  "description": "Cutting-edge AI and tech breakthroughs changing the world right now."},
]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/presets")
async def list_presets():
    """List available content presets for the preset flow.

    Each preset defines a niche + base topic that the Gemini script agent
    expands into a full video script using live Reddit trending context.
    """
    return {"presets": _PRESET_CATALOGUE}


@router.get("/tones", response_model=list[ToneOption])
async def list_tones():
    """List selectable tone/style options for text and preset flows.

    In the voice flow, tone is auto-detected from the creator's audio by
    Gemini multimodal. In text/preset flows, the user picks from this list —
    the selected tone drives the Gemini script agent's writing style.
    """
    return TONE_CATALOGUE


@router.post("/series", response_model=SeriesCreateResponse)
async def create_series(config: SeriesConfig):
    """Save a series configuration to S3.

    A series bundles all video settings (art style, music, caption style, tone,
    video format) into a reusable profile. Pass the returned series_id in
    /generate-script and /generate-video to load these settings automatically.
    """
    series_id = str(uuid4())
    s3_key = f"series/{series_id}/config.json"

    try:
        config_url = await gcs.store_json(config.model_dump(), s3_key)
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
    """List all saved series configs.

    Scans S3 for series/{id}/config.json files created by POST /series.
    """
    try:
        all_keys = await gcs.list_keys("series/")
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
            data = await gcs.load_json(f"series/{sid}/config.json")
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
