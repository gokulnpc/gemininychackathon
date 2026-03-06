"""Firestore project metadata service.

Collection: projects/{project_id}

Replaces GCS JSON blobs for project metadata (created_at, status, video_urls, etc.).
Video files (MP4s) remain in GCS — only the structured metadata moves to Firestore.

Falls back to GCS-based JSON if Firestore is unavailable (GOOGLE_CLOUD_PROJECT not set
or google-cloud-firestore not installed), so local development works without changes.

Public interface mirrors the GCS pattern used in video.py and projects.py:
  save_project(project_id, metadata)   → replaces gcs.store_json(metadata, "projects/.../metadata.json")
  get_project(project_id)              → replaces gcs.load_json("projects/.../metadata.json")
  list_projects(limit)                 → replaces gcs.list_keys + per-key load_json
  delete_project(project_id)           → replaces gcs.delete_object("projects/.../metadata.json")
"""

from __future__ import annotations

import asyncio
import logging

from config import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "projects"


def _firestore_available() -> bool:
    try:
        from google.cloud import firestore  # noqa: F401
        return True
    except ImportError:
        return False


def _get_db():
    from google.cloud import firestore
    settings = get_settings()
    return firestore.Client(project=settings.google_cloud_project or None)


# ── Public API ────────────────────────────────────────────────────────────────

async def save_project(project_id: str, metadata: dict) -> None:
    """Upsert project metadata to Firestore (or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _save():
            db = _get_db()
            db.collection(COLLECTION).document(project_id).set(metadata)

        await asyncio.to_thread(_save)
        logger.info("Firestore: saved project %s", project_id)
        return

    # GCS fallback
    from services import gcs
    await gcs.store_json(metadata, f"projects/{project_id}/metadata.json")


async def get_project(project_id: str) -> dict | None:
    """Load project metadata from Firestore (or GCS fallback). Returns None on miss."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _get():
            db = _get_db()
            doc = db.collection(COLLECTION).document(project_id).get()
            return doc.to_dict() if doc.exists else None

        result = await asyncio.to_thread(_get)
        logger.debug("Firestore: loaded project %s (found=%s)", project_id, result is not None)
        return result

    # GCS fallback
    from services import gcs
    try:
        return await gcs.load_json(f"projects/{project_id}/metadata.json")
    except Exception:
        return None


async def list_projects(limit: int = 50) -> list[dict]:
    """List projects ordered by created_at descending (Firestore or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _list():
            from google.cloud import firestore
            db = _get_db()
            return [
                doc.to_dict()
                for doc in db.collection(COLLECTION)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            ]

        results = await asyncio.to_thread(_list)
        logger.debug("Firestore: listed %d projects", len(results))
        return results

    # GCS fallback — list all metadata keys and load each
    from services import gcs
    all_keys = await gcs.list_keys("projects/")
    meta_keys = [
        k for k in all_keys
        if k.endswith("/metadata.json") and len(k.split("/")) == 3
    ]
    project_ids = [k.split("/")[1] for k in meta_keys]
    results: list[dict] = []
    for pid in project_ids:
        try:
            data = await gcs.load_json(f"projects/{pid}/metadata.json")
            results.append(data)
        except Exception:
            pass
    results.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return results[:limit]


async def delete_project(project_id: str) -> None:
    """Delete a project document from Firestore (or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _delete():
            _get_db().collection(COLLECTION).document(project_id).delete()

        await asyncio.to_thread(_delete)
        logger.info("Firestore: deleted project %s", project_id)
        return

    from services import gcs
    await gcs.delete_object(f"projects/{project_id}/metadata.json")
