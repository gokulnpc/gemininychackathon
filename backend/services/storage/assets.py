"""User Asset Storage Helper.

Provides a unified way to resolve asset metadata and URLs, 
decoupling the Gemini agent and Routers from the underlying gcs bucket schema.
"""

from __future__ import annotations
import logging

from services.storage import gcs

logger = logging.getLogger(__name__)

async def resolve_asset_metadata(uid: str, category: str, asset_id: str) -> dict | None:
    """Load asset metadata, verifying ownership."""
    meta_key = f"user_assets/{uid}/{category}/{asset_id}/meta.json"
    try:
        meta = await gcs.load_json(meta_key)
    except Exception as e:
        logger.warning(f"Could not load asset metadata for {asset_id}: {e}")
        return None

    if meta.get("uid") and meta["uid"] != uid:
        logger.warning(f"Unauthorized asset access attempt for {asset_id} by {uid}")
        return None

    return meta

async def resolve_asset_url(uid: str, category: str, asset_id: str) -> str | None:
    """Resolve a user-owned asset ID to a presigned playback URL.

    Reads user_assets/{uid}/{category}/{asset_id}/meta.json, extracts the
    stored gcs_key, and returns a presigned (or public) URL.
    """
    meta = await resolve_asset_metadata(uid, category, asset_id)
    if not meta:
        return None
        
    gcs_key = meta.get("gcs_key")
    if not gcs_key:
        return None
        
    try:
        url = await gcs.generate_presigned_url(gcs_key)
        return url
    except Exception as e:
        logger.warning(f"Could not generate presigned URL for {asset_id}: {e}")
        return None

async def list_user_assets(uid: str, category: str, limit: int = 20) -> list[dict]:
    """List the user's uploaded assets for a given category.
    Returns a list of {id, filename, uploaded_at} records.
    """
    import asyncio
    prefix = f"user_assets/{uid}/{category}/"
    try:
        keys = await gcs.list_keys(prefix)
        meta_keys = [k for k in keys if k.endswith("/meta.json")]
        metas = await asyncio.gather(
            *[gcs.load_json(mk) for mk in meta_keys],
            return_exceptions=True,
        )
        assets = [
            {
                "id": str(m.get("id", "")),
                "filename": str(m.get("filename", "")),
                "uploaded_at": str(m.get("uploaded_at", ""))
            }
            for m in metas
            if isinstance(m, dict) and m.get("id")
        ]
        # Sort by uploaded_at newest first
        assets.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        return assets[:limit]
    except Exception as e:
        logger.warning(f"Could not list user assets for {uid}/{category}: {e}")
        return []
