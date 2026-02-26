import io
import json
import logging
import os

import boto3

from config import get_settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


async def upload_file(
    local_path: str,
    s3_key: str,
    content_type: str = "video/mp4",
) -> str:
    """Upload a file to S3 and return the public URL.

    Args:
        local_path: Path to the local file.
        s3_key: The S3 object key (e.g., "projects/abc/final.mp4").
        content_type: MIME type for the upload.

    Returns:
        The S3 URL of the uploaded file.
    """
    settings = get_settings()
    client = _get_s3_client()

    client.upload_file(
        local_path,
        settings.s3_bucket,
        s3_key,
        ExtraArgs={"ContentType": content_type},
    )

    url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    logger.info("Uploaded %s → %s", local_path, url)
    return url


async def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for an S3 object."""
    settings = get_settings()
    client = _get_s3_client()

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )
    return url


async def download_file(s3_key: str, local_path: str) -> str:
    """Download a file from S3 to a local path."""
    settings = get_settings()
    client = _get_s3_client()

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    client.download_file(settings.s3_bucket, s3_key, local_path)
    logger.info("Downloaded s3://%s/%s → %s", settings.s3_bucket, s3_key, local_path)
    return local_path


async def store_json(data: dict, s3_key: str) -> str:
    """Upload a dict as JSON to S3 and return the public URL."""
    settings = get_settings()
    client = _get_s3_client()

    body = json.dumps(data, indent=2).encode("utf-8")
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=body,
        ContentType="application/json",
    )

    url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    logger.info("Stored JSON → %s", url)
    return url


async def list_keys(prefix: str) -> list[str]:
    """List all S3 object keys under a given prefix."""
    settings = get_settings()
    client = _get_s3_client()

    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


async def load_json(s3_key: str) -> dict:
    """Download and parse a JSON file from S3."""
    settings = get_settings()
    client = _get_s3_client()

    response = client.get_object(Bucket=settings.s3_bucket, Key=s3_key)
    body = response["Body"].read().decode("utf-8")
    return json.loads(body)
