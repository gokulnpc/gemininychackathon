"""User Assets router — upload, list, retrieve URL, delete user files.

Supports three categories: images, music, voice_memos.

GCS layout:
  user_assets/{category}/{asset_id}/{original_filename}   ← the file
  user_assets/{category}/{asset_id}/meta.json             ← metadata
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile

from deps.auth import get_current_user
from services.storage import gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assets"])

VALID_CATEGORIES = {"images", "music", "voice_memos"}


def _validate_category(category: str) -> None:
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}")


# ── List ───────────────────────────────────────────────────────────────────────


@router.get("/assets")
async def list_assets(category: str = Query(..., description="images | music | voice_memos"), current_user: dict = Depends(get_current_user)):
    """Return all assets in the given category, newest first."""
    _validate_category(category)

    prefix = f"user_assets/{category}/"
    try:
        keys = await gcs.list_keys(prefix)
    except Exception as e:
        logger.exception("Failed to list asset keys for category=%s", category)
        raise HTTPException(status_code=500, detail=f"Failed to list assets: {e}")

    meta_keys = [k for k in keys if k.endswith("/meta.json")]

    assets = []
    for mk in meta_keys:
        try:
            assets.append(await gcs.load_json(mk))
        except Exception:
            logger.warning("Could not load asset metadata at %s — skipping", mk)

    assets.sort(key=lambda a: a.get("uploaded_at", ""), reverse=True)
    return {"assets": assets}


# ── Upload ─────────────────────────────────────────────────────────────────────


@router.post("/assets/upload")
async def upload_asset(
    file: UploadFile,
    category: str = Form(..., description="images | music | voice_memos"),
    current_user: dict = Depends(get_current_user),
):
    """Upload a file and return its asset metadata."""
    _validate_category(category)

    asset_id = str(uuid4())
    content = await file.read()
    filename = file.filename or f"asset_{asset_id}"
    content_type = file.content_type or "application/octet-stream"

    gcs_key = f"user_assets/{category}/{asset_id}/{filename}"
    meta_key = f"user_assets/{category}/{asset_id}/meta.json"

    # Write to temp file then upload (gcs.upload_file expects a local path)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        await gcs.upload_file(tmp_path, gcs_key, content_type)
    except Exception as e:
        logger.exception("Failed to upload asset for category=%s", category)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    meta = {
        "id": asset_id,
        "filename": filename,
        "content_type": content_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "gcs_key": gcs_key,
        "size_bytes": len(content),
    }

    try:
        await gcs.store_json(meta, meta_key)
    except Exception as e:
        logger.exception("Failed to store asset metadata for asset_id=%s", asset_id)
        raise HTTPException(status_code=500, detail=f"Metadata save failed: {e}")

    return meta


# ── Get presigned URL ──────────────────────────────────────────────────────────


@router.get("/assets/{asset_id}/url")
async def get_asset_url(
    asset_id: str,
    category: str = Query(..., description="images | music | voice_memos"),
    current_user: dict = Depends(get_current_user),
):
    """Return a presigned (or public) URL for the asset file."""
    _validate_category(category)

    meta_key = f"user_assets/{category}/{asset_id}/meta.json"
    try:
        meta = await gcs.load_json(meta_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        url = await gcs.generate_presigned_url(meta["gcs_key"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate URL: {e}")

    return {"url": url}


# ── Delete ─────────────────────────────────────────────────────────────────────


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: str,
    category: str = Query(..., description="images | music | voice_memos"),
    current_user: dict = Depends(get_current_user),
):
    """Delete an asset and its metadata."""
    _validate_category(category)

    meta_key = f"user_assets/{category}/{asset_id}/meta.json"
    try:
        meta = await gcs.load_json(meta_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        await gcs.delete_object(meta["gcs_key"])
    except Exception as e:
        logger.warning("Failed to delete asset file %s: %s", meta["gcs_key"], e)

    try:
        await gcs.delete_object(meta_key)
    except Exception as e:
        logger.warning("Failed to delete asset metadata %s: %s", meta_key, e)

    return {"deleted": asset_id}
