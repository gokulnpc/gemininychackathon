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
import functools
import logging

from config import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "projects"
USERS_COLLECTION = "users"
DEFAULT_CREDITS = 300
CREDIT_CHARGE = 100


@functools.lru_cache(maxsize=None)
def _firestore_available() -> bool:
    """Return True if google-cloud-firestore is installed. Cached after first call."""
    try:
        from google.cloud import firestore  # noqa: F401
        return True
    except ImportError:
        return False


def _get_db(settings=None):
    from google.cloud import firestore
    if settings is None:
        settings = get_settings()
    return firestore.Client(project=settings.google_cloud_project or None)


# ── Public API ────────────────────────────────────────────────────────────────

async def save_project(project_id: str, metadata: dict) -> None:
    """Upsert project metadata to Firestore (or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _save():
            db = _get_db(settings)
            db.collection(COLLECTION).document(project_id).set(metadata)

        await asyncio.to_thread(_save)
        logger.info("Firestore: saved project %s", project_id)
        return

    # GCS fallback
    from services.storage import gcs
    await gcs.store_json(metadata, f"projects/{project_id}/metadata.json")


async def get_project(project_id: str) -> dict | None:
    """Load project metadata from Firestore (or GCS fallback). Returns None on miss."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _get():
            db = _get_db(settings)
            doc = db.collection(COLLECTION).document(project_id).get()
            return doc.to_dict() if doc.exists else None

        result = await asyncio.to_thread(_get)
        logger.debug("Firestore: loaded project %s (found=%s)", project_id, result is not None)
        return result

    # GCS fallback
    from services.storage import gcs
    try:
        return await gcs.load_json(f"projects/{project_id}/metadata.json")
    except Exception as exc:
        logger.debug("GCS get_project %s miss or error: %s", project_id, exc)
        return None


async def list_projects(limit: int = 50) -> list[dict]:
    """List projects ordered by created_at descending (Firestore or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _list():
            from google.cloud import firestore
            db = _get_db(settings)
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
    from services.storage import gcs
    all_keys = await gcs.list_keys("projects/")
    meta_keys = [
        k for k in all_keys
        if k.endswith("/metadata.json") and len(k.split("/")) == 3
    ]
    project_ids = [k.split("/")[1] for k in meta_keys]

    async def _safe_load_json(pid: str) -> dict | None:
        try:
            return await gcs.load_json(f"projects/{pid}/metadata.json")
        except Exception:
            return None

    tasks = [_safe_load_json(pid) for pid in project_ids]
    loaded_data = await asyncio.gather(*tasks)

    results = [data for data in loaded_data if data is not None]
    results.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return results[:limit]


async def delete_project(project_id: str) -> None:
    """Delete a project document from Firestore (or GCS fallback)."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _delete():
            _get_db(settings).collection(COLLECTION).document(project_id).delete()

        await asyncio.to_thread(_delete)
        logger.info("Firestore: deleted project %s", project_id)
        return

    from services.storage import gcs
    await gcs.delete_object(f"projects/{project_id}/metadata.json")


# ── User profile ───────────────────────────────────────────────────────────────


async def get_or_create_user(
    uid: str,
    email: str | None = None,
    display_name: str | None = None,
    photo_url: str | None = None,
) -> dict:
    """Upsert a user profile in users/{uid}. Creates with default credits on first call."""
    settings = get_settings()
    if not (_firestore_available() and settings.google_cloud_project):
        # No Firestore — return a minimal in-memory profile
        return {"uid": uid, "email": email, "display_name": display_name, "photo_url": photo_url, "credits": DEFAULT_CREDITS}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    def _upsert():
        db = _get_db(settings)
        ref = db.collection(USERS_COLLECTION).document(uid)
        doc = ref.get()
        if doc.exists:
            # Update mutable fields; never overwrite credits
            updates: dict = {"last_seen_at": now}
            if email:
                updates["email"] = email
            if display_name:
                updates["display_name"] = display_name
            if photo_url:
                updates["photo_url"] = photo_url
            ref.update(updates)
            return {**doc.to_dict(), **updates}
        else:
            profile = {
                "uid": uid,
                "email": email or "",
                "display_name": display_name or "",
                "photo_url": photo_url or "",
                "credits": DEFAULT_CREDITS,
                "created_at": now,
                "last_seen_at": now,
            }
            ref.set(profile)
            logger.info("Firestore: created new user profile %s", uid)
            return profile

    return await asyncio.to_thread(_upsert)


async def get_user(uid: str) -> dict | None:
    """Load user profile from users/{uid}. Returns None if not found."""
    settings = get_settings()
    if not (_firestore_available() and settings.google_cloud_project):
        return None

    def _get():
        db = _get_db(settings)
        doc = db.collection(USERS_COLLECTION).document(uid).get()
        return doc.to_dict() if doc.exists else None

    return await asyncio.to_thread(_get)


async def update_user(uid: str, fields: dict) -> dict:
    """Update allowed user profile fields. Returns updated profile."""
    settings = get_settings()
    if not (_firestore_available() and settings.google_cloud_project):
        return {**fields, "uid": uid}

    # Only allow safe fields to be updated via this function
    allowed = {k: v for k, v in fields.items() if k in ("display_name", "photo_url")}

    def _update():
        db = _get_db(settings)
        ref = db.collection(USERS_COLLECTION).document(uid)
        ref.update(allowed)
        return ref.get().to_dict()

    return await asyncio.to_thread(_update)


# ── User-scoped project queries ────────────────────────────────────────────────


async def list_projects_for_user(uid: str, limit: int = 100) -> list[dict]:
    """List projects belonging to uid, newest first."""
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _list():
            from google.cloud import firestore
            db = _get_db(settings)
            docs = [
                doc.to_dict()
                for doc in db.collection(COLLECTION)
                .where(filter=firestore.FieldFilter("uid", "==", uid))
                .stream()
            ]
            docs.sort(key=lambda d: d.get("created_at", "") or "", reverse=True)
            return docs[:limit]

        results = await asyncio.to_thread(_list)
        logger.debug("Firestore: listed %d projects for uid=%s", len(results), uid)
        return results

    # GCS fallback — filter by uid field in metadata
    all_projects = await list_projects(limit=limit * 5)
    return [p for p in all_projects if p.get("uid") == uid][:limit]


async def get_project_for_user(project_id: str, uid: str) -> dict:
    """Load a project and verify ownership. Raises 404/403 via HTTPException."""
    from fastapi import HTTPException
    data = await get_project(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if data.get("uid") != uid:
        raise HTTPException(status_code=403, detail="Access denied. This project is unassigned or belongs to another user.")
    return data


# ── Credits (transactional) ────────────────────────────────────────────────────


async def deduct_credits(uid: str, project_id: str, amount: int = CREDIT_CHARGE) -> int:
    """Deduct credits for a project. Idempotent — won't charge twice for same project.

    Returns remaining credits after deduction.
    Raises HTTPException 402 if credits are insufficient.
    Raises HTTPException 409 if project was already charged.
    """
    from fastapi import HTTPException

    settings = get_settings()
    if not (_firestore_available() and settings.google_cloud_project):
        logger.warning("Firestore unavailable — skipping credit deduction for project %s", project_id)
        return DEFAULT_CREDITS

    def _transact():
        from google.cloud import firestore
        db = _get_db(settings)
        user_ref = db.collection(USERS_COLLECTION).document(uid)
        project_ref = db.collection(COLLECTION).document(project_id)

        @firestore.transactional
        def _run(transaction):
            user_snap = user_ref.get(transaction=transaction)
            project_snap = project_ref.get(transaction=transaction)

            if not user_snap.exists:
                raise ValueError("User not found")

            user_data = user_snap.to_dict()
            project_data = project_snap.to_dict() if project_snap.exists else {}

            if project_data.get("charged"):
                return user_data.get("credits", 0)  # already charged — idempotent

            current_credits = user_data.get("credits", 0)
            if current_credits < amount:
                raise PermissionError(f"Insufficient credits: {current_credits} < {amount}")

            new_credits = current_credits - amount
            transaction.update(user_ref, {"credits": new_credits})
            transaction.update(project_ref, {"charged": True})
            return new_credits

        txn = db.transaction()
        return _run(txn)

    try:
        remaining = await asyncio.to_thread(_transact)
        logger.info("Credits deducted: uid=%s project=%s amount=%d remaining=%d", uid, project_id, amount, remaining)
        return remaining
    except PermissionError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=402, detail=str(e))
    except Exception as e:
        logger.exception("Credit deduction failed for uid=%s project=%s", uid, project_id)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Credit deduction failed: {e}")
