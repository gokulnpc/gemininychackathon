from __future__ import annotations

import asyncio
import functools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)

YOUTUBE_AUTH_COLLECTION = "user_social_auth"
YOUTUBE_PENDING_COLLECTION = "user_social_oauth_states"
_LOCAL_STATE_ROOT = Path(__file__).resolve().parents[2] / ".local_state" / "youtube_auth"


@functools.lru_cache(maxsize=None)
def _firestore_available() -> bool:
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_user_path(uid: str) -> Path:
    return _LOCAL_STATE_ROOT / "users" / f"{uid}.json"


def _local_pending_path(state: str) -> Path:
    return _LOCAL_STATE_ROOT / "pending" / f"{state}.json"


async def get_youtube_auth(uid: str) -> dict | None:
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _get():
            doc = _get_db(settings).collection(YOUTUBE_AUTH_COLLECTION).document(uid).get()
            return doc.to_dict() if doc.exists else None

        return await asyncio.to_thread(_get)

    def _load_local() -> dict | None:
        path = _local_user_path(uid)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    return await asyncio.to_thread(_load_local)


async def get_youtube_credentials_json(uid: str) -> str | None:
    record = await get_youtube_auth(uid)
    if not record:
        return None
    return record.get("credentials_json")


async def save_youtube_credentials(
    uid: str,
    credentials_json: str,
    channel_info: dict | None = None,
) -> dict:
    settings = get_settings()
    now = _now_iso()

    if _firestore_available() and settings.google_cloud_project:
        def _save() -> dict:
            db = _get_db(settings)
            ref = db.collection(YOUTUBE_AUTH_COLLECTION).document(uid)
            existing_doc = ref.get()
            existing = existing_doc.to_dict() if existing_doc.exists else {}
            payload = {
                "uid": uid,
                "provider": "youtube",
                "credentials_json": credentials_json,
                "updated_at": now,
            }
            if not existing:
                payload["connected_at"] = now
            else:
                payload["connected_at"] = existing.get("connected_at", now)
            if channel_info:
                payload.update({
                    "channel_id": channel_info.get("channel_id"),
                    "channel_title": channel_info.get("channel_title"),
                })
            ref.set(payload, merge=True)
            return {**existing, **payload}

        return await asyncio.to_thread(_save)

    def _save_local() -> dict:
        path = _local_user_path(uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            existing = json.loads(path.read_text())
        payload = {
            "uid": uid,
            "provider": "youtube",
            "credentials_json": credentials_json,
            "updated_at": now,
            "connected_at": existing.get("connected_at", now),
        }
        if channel_info:
            payload.update({
                "channel_id": channel_info.get("channel_id"),
                "channel_title": channel_info.get("channel_title"),
            })
        record = {**existing, **payload}
        path.write_text(json.dumps(record, indent=2))
        return record

    return await asyncio.to_thread(_save_local)


async def delete_youtube_credentials(uid: str) -> None:
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _delete() -> None:
            _get_db(settings).collection(YOUTUBE_AUTH_COLLECTION).document(uid).delete()

        await asyncio.to_thread(_delete)
        return

    def _delete_local() -> None:
        path = _local_user_path(uid)
        path.unlink(missing_ok=True)

    await asyncio.to_thread(_delete_local)


async def create_pending_youtube_oauth_state(
    uid: str,
    state: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict:
    settings = get_settings()
    payload = {
        "uid": uid,
        "provider": "youtube",
        "state": state,
        "redirect_uri": redirect_uri,
        "created_at": _now_iso(),
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier

    if _firestore_available() and settings.google_cloud_project:
        def _save() -> dict:
            _get_db(settings).collection(YOUTUBE_PENDING_COLLECTION).document(state).set(payload)
            return payload

        return await asyncio.to_thread(_save)

    def _save_local() -> dict:
        path = _local_pending_path(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return payload

    return await asyncio.to_thread(_save_local)


async def get_pending_youtube_oauth_state(state: str) -> dict | None:
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _get() -> dict | None:
            doc = _get_db(settings).collection(YOUTUBE_PENDING_COLLECTION).document(state).get()
            return doc.to_dict() if doc.exists else None

        return await asyncio.to_thread(_get)

    def _load_local() -> dict | None:
        path = _local_pending_path(state)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    return await asyncio.to_thread(_load_local)


async def delete_pending_youtube_oauth_state(state: str) -> None:
    settings = get_settings()

    if _firestore_available() and settings.google_cloud_project:
        def _delete() -> None:
            _get_db(settings).collection(YOUTUBE_PENDING_COLLECTION).document(state).delete()

        await asyncio.to_thread(_delete)
        return

    def _delete_local() -> None:
        _local_pending_path(state).unlink(missing_ok=True)

    await asyncio.to_thread(_delete_local)
