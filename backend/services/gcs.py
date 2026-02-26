"""Google Cloud Storage — drop-in replacement for the AWS S3 service.

Same public interface as the old s3.py so all callers work without changes.

Reuses Application Default Credentials (ADC) already configured for Veo 3 —
no extra auth needed beyond GOOGLE_CLOUD_PROJECT and GCS_BUCKET in .env.
"""

import asyncio
import json
import logging
import os
from datetime import timedelta

from config import get_settings

logger = logging.getLogger(__name__)


def _get_client():
    from google.cloud import storage
    return storage.Client()


def _public_url(bucket_name: str, key: str) -> str:
    return f"https://storage.googleapis.com/{bucket_name}/{key}"


async def upload_file(local_path: str, gcs_key: str, content_type: str = "video/mp4") -> str:
    """Upload a local file to GCS and return its public URL."""
    settings = get_settings()

    def _upload():
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        blob = bucket.blob(gcs_key)
        blob.upload_from_filename(local_path, content_type=content_type)
        return _public_url(settings.gcs_bucket, gcs_key)

    url = await asyncio.to_thread(_upload)
    logger.info("Uploaded %s → %s", local_path, url)
    return url


async def generate_presigned_url(gcs_key: str, expires_in: int = 3600) -> str:
    """Return a signed GCS URL valid for `expires_in` seconds.

    Requires the ADC credentials to be a service account (set
    GOOGLE_APPLICATION_CREDENTIALS to a service account JSON key for local dev;
    on GCP the default compute service account works automatically).
    Falls back to the public URL if signing is unavailable.
    """
    settings = get_settings()

    def _sign():
        client = _get_client()
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
    """Download a GCS object to a local path."""
    settings = get_settings()

    def _download():
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        bucket.blob(gcs_key).download_to_filename(local_path)

    await asyncio.to_thread(_download)
    logger.info("Downloaded gs://%s/%s → %s", settings.gcs_bucket, gcs_key, local_path)
    return local_path


async def store_json(data: dict, gcs_key: str) -> str:
    """Upload a dict as JSON to GCS and return its public URL."""
    settings = get_settings()

    def _store():
        client = _get_client()
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


async def load_json(gcs_key: str) -> dict:
    """Download and parse a JSON file from GCS."""
    settings = get_settings()

    def _load():
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        return json.loads(bucket.blob(gcs_key).download_as_text())

    return await asyncio.to_thread(_load)


async def list_keys(prefix: str) -> list[str]:
    """List all GCS object names under a given prefix."""
    settings = get_settings()

    def _list():
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        return [blob.name for blob in bucket.list_blobs(prefix=prefix)]

    return await asyncio.to_thread(_list)


async def key_exists(gcs_key: str) -> bool:
    """Return True if an object exists in GCS."""
    settings = get_settings()

    def _exists():
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        return bucket.blob(gcs_key).exists()

    return await asyncio.to_thread(_exists)


async def delete_object(gcs_key: str) -> None:
    """Delete an object from GCS."""
    settings = get_settings()

    def _delete():
        client = _get_client()
        bucket = client.bucket(settings.gcs_bucket)
        bucket.blob(gcs_key).delete()

    await asyncio.to_thread(_delete)
    logger.info("Deleted gs://%s/%s", settings.gcs_bucket, gcs_key)
