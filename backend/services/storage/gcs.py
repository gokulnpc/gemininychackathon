"""Google Cloud Storage — with local-filesystem fallback.

When google-cloud-storage is not installed or GCS_BUCKET is not configured,
files are copied to the local `outputs/` directory and served via
FastAPI's StaticFiles mount at /outputs.

Same public interface as before — all callers work without changes.
"""

import asyncio
import functools
import json
import logging
import os
import shutil
from datetime import timedelta

from config import get_settings

logger = logging.getLogger(__name__)

# Local outputs directory (relative to this file's parent = backend/)
_OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs")


@functools.lru_cache(maxsize=None)
def _gcs_available() -> bool:
    """Return True if google-cloud-storage is importable. Cached after first call."""
    try:
        from google.cloud import storage  # noqa: F401
        return True
    except ImportError:
        return False


def _get_client(settings):
    from google.cloud import storage
    return storage.Client(project=settings.google_cloud_project or None)


def _public_url(bucket_name: str, key: str) -> str:
    return f"https://storage.googleapis.com/{bucket_name}/{key}"


def _local_url(gcs_key: str, base_url: str = "http://localhost:8000") -> str:
    """Return a localhost URL for a file saved under outputs/."""
    return f"{base_url}/outputs/{gcs_key}"


def _local_path(gcs_key: str) -> str:
    dest = os.path.join(_OUTPUTS_DIR, gcs_key)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    return dest


async def upload_file(local_path: str, gcs_key: str, content_type: str = "video/mp4") -> str:
    """Upload a local file to GCS (or copy locally) and return a URL."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _upload():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            blob = bucket.blob(gcs_key)
            blob.upload_from_filename(local_path, content_type=content_type)
            return _public_url(settings.gcs_bucket, gcs_key)

        url = await asyncio.to_thread(_upload)
        logger.info("Uploaded %s → %s", local_path, url)
        return url

    # ── Local fallback ────────────────────────────────────────────────────────
    dest = _local_path(gcs_key)
    await asyncio.to_thread(shutil.copy2, local_path, dest)
    url = _local_url(gcs_key)
    logger.info("Local copy %s → %s  (GCS not configured)", local_path, url)
    return url


async def generate_presigned_url(gcs_key: str, expires_in: int = 3600) -> str:
    """Return a signed GCS URL, or the local URL if GCS is unavailable."""
    settings = get_settings()

    if not _gcs_available() or not settings.gcs_bucket:
        return _local_url(gcs_key)

    def _sign():
        client = _get_client(settings)
        bucket = client.bucket(settings.gcs_bucket)
        blob = bucket.blob(gcs_key)
        return blob.generate_signed_url(
            expiration=timedelta(seconds=expires_in),
            method="GET",
            version="v4",
        )

    try:
        return await asyncio.to_thread(_sign)
    except Exception as e:
        logger.warning("GCS signed URL unavailable (%s) — returning public URL", e)
        return _public_url(settings.gcs_bucket, gcs_key)


async def download_file(gcs_key: str, local_path: str) -> str:
    """Download a GCS object (or copy from local outputs/) to local_path."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _download():
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            bucket.blob(gcs_key).download_to_filename(local_path)

        await asyncio.to_thread(_download)
    else:
        src = _local_path(gcs_key)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        await asyncio.to_thread(shutil.copy2, src, local_path)

    logger.info("Downloaded %s → %s", gcs_key, local_path)
    return local_path


async def store_json(data: dict, gcs_key: str) -> str:
    """Upload a dict as JSON to GCS (or save locally) and return a URL."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _store():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            blob = bucket.blob(gcs_key)
            blob.upload_from_string(
                json.dumps(data, indent=2),
                content_type="application/json",
            )
            return _public_url(settings.gcs_bucket, gcs_key)

        url = await asyncio.to_thread(_store)
        logger.info("Stored JSON → %s", url)
        return url

    def _store_local() -> str:
        dest = _local_path(gcs_key)
        with open(dest, "w") as f:
            json.dump(data, f, indent=2)
        return _local_url(gcs_key)

    url = await asyncio.to_thread(_store_local)
    logger.info("Stored JSON locally → %s", url)
    return url


async def load_json(gcs_key: str) -> dict:
    """Download and parse a JSON file from GCS or local outputs/."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _load():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            return json.loads(bucket.blob(gcs_key).download_as_text())

        return await asyncio.to_thread(_load)

    def _load_local() -> dict:
        src = _local_path(gcs_key)
        with open(src) as f:
            return json.load(f)

    return await asyncio.to_thread(_load_local)


async def list_keys(prefix: str) -> list[str]:
    """List all object names under a given prefix (GCS or local outputs/)."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _list():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            return [blob.name for blob in bucket.list_blobs(prefix=prefix)]

        return await asyncio.to_thread(_list)

    base = os.path.join(_OUTPUTS_DIR, prefix)
    keys: list[str] = []
    if os.path.exists(base):
        for root, _, files in os.walk(base):
            for fn in files:
                abs_path = os.path.join(root, fn)
                keys.append(os.path.relpath(abs_path, _OUTPUTS_DIR))
    return keys


async def key_exists(gcs_key: str) -> bool:
    """Return True if the object exists in GCS or local outputs/."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _exists():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            return bucket.blob(gcs_key).exists()

        return await asyncio.to_thread(_exists)

    return os.path.exists(_local_path(gcs_key))


async def get_asset_url(uid: str, category: str, asset_id: str) -> str | None:
    """Resolve a user-owned asset ID to a presigned playback URL.

    Reads user_assets/{uid}/{category}/{asset_id}/meta.json, extracts the
    stored gcs_key, and returns a presigned (or public) URL.  Returns None
    when the asset doesn't exist or the meta.json has no gcs_key.
    """
    meta_key = f"user_assets/{uid}/{category}/{asset_id}/meta.json"
    try:
        meta = await load_json(meta_key)
    except Exception:
        return None
    gcs_key = meta.get("gcs_key")
    if not gcs_key:
        return None
    return await generate_presigned_url(gcs_key)


async def delete_object(gcs_key: str) -> None:
    """Delete an object from GCS or local outputs/."""
    settings = get_settings()

    if _gcs_available() and settings.gcs_bucket:
        def _delete():
            client = _get_client(settings)
            bucket = client.bucket(settings.gcs_bucket)
            bucket.blob(gcs_key).delete()

        await asyncio.to_thread(_delete)
        logger.info("Deleted gs://%s/%s", settings.gcs_bucket, gcs_key)
        return

    dest = _local_path(gcs_key)
    if os.path.exists(dest):
        os.remove(dest)
    logger.info("Deleted local %s", dest)
