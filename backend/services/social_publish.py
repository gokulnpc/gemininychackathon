"""Social media publishing via official platform APIs.

Platforms:
  YouTube   — YouTube Data API v3  (OAuth2, google-api-python-client)
  Instagram — Meta Graph API v22   (long-lived access token + presigned S3 URL)
  TikTok    — Content Posting API v2 (Direct Post, access token)

Setup:
  YouTube:   python3 setup_social_auth.py youtube  (runs OAuth2 flow once)
  Instagram: set INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_USER_ID in .env
  TikTok:    set TIKTOK_ACCESS_TOKEN in .env
"""

import asyncio
import logging
from pathlib import Path

import httpx

from config import get_settings
from services import gcs as gcs_service

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v22.0"
TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"

# PublishPlatform values → Pipeline platform values (S3 key prefix)
PLATFORM_TO_S3_PREFIX: dict[str, str] = {
    "instagram": "instagram_reels",
    "youtube": "youtube_shorts",
    "tiktok": "tiktok",
}


# ── YouTube ───────────────────────────────────────────────────────────────────


async def _publish_youtube(
    project_id: str,
    title: str,
    description: str,
    tags: list[str],
) -> dict:
    """Download from S3 then upload to YouTube via Data API v3."""
    local_path = f"/tmp/voicevid_{project_id}_youtube.mp4"

    # Try youtube_shorts first, fall back to instagram_reels (same 9:16 vertical format)
    s3_key = None
    for prefix in ["youtube_shorts", "instagram_reels"]:
        candidate = f"projects/{project_id}/{prefix}/final.mp4"
        try:
            await gcs_service.download_file(candidate, local_path)
            s3_key = candidate
            break
        except Exception:
            continue

    if s3_key is None:
        return {
            "platform": "youtube",
            "status": "failed",
            "error": "S3 download failed: no video found (tried youtube_shorts and instagram_reels)",
        }

    def _blocking_upload() -> dict:
        from pathlib import Path as _Path

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        settings = get_settings()
        token_file = settings.youtube_token_file

        if not token_file or not _Path(token_file).exists():
            raise RuntimeError(
                "YouTube token not found. Run: python3 setup_social_auth.py youtube"
            )

        creds = Credentials.from_authorized_user_file(
            token_file,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _Path(token_file).write_text(creds.to_json())

        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:500],
                "categoryId": "22",  # People & Blogs
            },
            "status": {"privacyStatus": "public"},
        }

        media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = req.next_chunk()

        return {
            "platform": "youtube",
            "status": "published",
            "post_url": f"https://www.youtube.com/watch?v={response['id']}",
        }

    try:
        return await asyncio.to_thread(_blocking_upload)
    except Exception as exc:
        logger.exception("YouTube upload failed")
        return {"platform": "youtube", "status": "failed", "error": str(exc)}
    finally:
        Path(local_path).unlink(missing_ok=True)


# ── Instagram ─────────────────────────────────────────────────────────────────


async def _publish_instagram(
    project_id: str,
    caption: str,
) -> dict:
    """Publish to Instagram via Meta Graph API using a presigned S3 URL."""
    settings = get_settings()
    token = settings.instagram_access_token
    user_id = settings.instagram_user_id

    if not token or not user_id:
        return {
            "platform": "instagram",
            "status": "failed",
            "error": "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID must be set in .env",
        }

    s3_key = f"projects/{project_id}/instagram_reels/final.mp4"
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    try:
        # Presigned URL so the Graph API can fetch the video from S3
        video_url = await gcs_service.generate_presigned_url(s3_key, expires_in=3600)

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Create media container
            r = await client.post(
                f"{base}/{user_id}/media",
                params={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "access_token": token,
                },
            )
            r.raise_for_status()
            creation_id = r.json()["id"]
            logger.info("Instagram container created: %s", creation_id)

            # Step 2: Poll until container status is FINISHED (up to 5 minutes)
            for _ in range(30):
                await asyncio.sleep(10)
                status_r = await client.get(
                    f"{base}/{creation_id}",
                    params={"fields": "status_code", "access_token": token},
                )
                status_r.raise_for_status()
                status_code = status_r.json().get("status_code")
                logger.info("Instagram container status: %s", status_code)
                if status_code == "FINISHED":
                    break
                if status_code == "ERROR":
                    return {
                        "platform": "instagram",
                        "status": "failed",
                        "error": "Instagram container processing failed",
                    }

            # Step 3: Publish
            pub_r = await client.post(
                f"{base}/{user_id}/media_publish",
                params={"creation_id": creation_id, "access_token": token},
            )
            pub_r.raise_for_status()
            media_id = pub_r.json()["id"]

            return {
                "platform": "instagram",
                "status": "published",
                "post_url": f"https://www.instagram.com/p/{media_id}/",
            }

    except Exception as exc:
        logger.exception("Instagram upload failed")
        return {"platform": "instagram", "status": "failed", "error": str(exc)}


# ── TikTok ────────────────────────────────────────────────────────────────────


async def _publish_tiktok(
    project_id: str,
    title: str,
) -> dict:
    """Publish to TikTok via Content Posting API v2 (Direct Post)."""
    settings = get_settings()
    token = settings.tiktok_access_token

    if not token:
        return {
            "platform": "tiktok",
            "status": "failed",
            "error": "TIKTOK_ACCESS_TOKEN must be set in .env",
        }

    s3_key = f"projects/{project_id}/tiktok/final.mp4"
    local_path = f"/tmp/voicevid_{project_id}_tiktok.mp4"

    try:
        await gcs_service.download_file(s3_key, local_path)
    except Exception as exc:
        return {"platform": "tiktok", "status": "failed", "error": f"S3 download failed: {exc}"}

    try:
        video_bytes = Path(local_path).read_bytes()
        total_bytes = len(video_bytes)
        chunk_size = 10 * 1024 * 1024  # 10 MB chunks
        num_chunks = max(1, -(-total_bytes // chunk_size))  # ceiling division

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: Init upload
            init_r = await client.post(
                f"{TIKTOK_API_BASE}/post/publish/video/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title": title[:150] or "New Video",
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": total_bytes,
                        "chunk_size": min(chunk_size, total_bytes),
                        "total_chunk_count": num_chunks,
                    },
                },
            )
            init_r.raise_for_status()
            data = init_r.json().get("data", {})
            publish_id = data["publish_id"]
            upload_url = data["upload_url"]
            logger.info("TikTok init OK: publish_id=%s", publish_id)

            # Step 2: Upload chunks
            for i in range(num_chunks):
                chunk = video_bytes[i * chunk_size : (i + 1) * chunk_size]
                start = i * chunk_size
                end = start + len(chunk) - 1
                up_r = await client.put(
                    upload_url,
                    content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start}-{end}/{total_bytes}",
                        "Content-Length": str(len(chunk)),
                    },
                )
                up_r.raise_for_status()
                logger.info("TikTok chunk %d/%d uploaded", i + 1, num_chunks)

            # Step 3: Poll publish status (up to 5 minutes)
            poll_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            }
            for _ in range(30):
                await asyncio.sleep(10)
                status_r = await client.post(
                    f"{TIKTOK_API_BASE}/post/publish/status/fetch/",
                    headers=poll_headers,
                    json={"publish_id": publish_id},
                )
                status_r.raise_for_status()
                pub_status = status_r.json().get("data", {}).get("status")
                logger.info("TikTok publish status: %s", pub_status)
                if pub_status == "PUBLISH_COMPLETE":
                    return {
                        "platform": "tiktok",
                        "status": "published",
                        "post_url": None,  # TikTok API v2 does not return a direct post URL
                    }
                if pub_status in ("FAILED", "CANCELLED"):
                    return {
                        "platform": "tiktok",
                        "status": "failed",
                        "error": f"TikTok publish ended with status: {pub_status}",
                    }

        return {"platform": "tiktok", "status": "failed", "error": "Publish timed out after 5 minutes"}

    except Exception as exc:
        logger.exception("TikTok upload failed")
        return {"platform": "tiktok", "status": "failed", "error": str(exc)}
    finally:
        Path(local_path).unlink(missing_ok=True)


# ── Orchestrator ──────────────────────────────────────────────────────────────


async def _unknown_platform(platform: str) -> dict:
    return {"platform": platform, "status": "failed", "error": f"Unknown platform: {platform}"}


async def publish_to_platforms(
    project_id: str,
    platforms: list[str],
    social_copy: dict[str, dict],
    schedule=None,  # reserved — scheduled posting not yet implemented
) -> list[dict]:
    """Publish project videos to the requested social media platforms concurrently.

    Args:
        project_id: VoiceVid project UUID string.
        platforms:  List of publish platform names: "instagram", "youtube", "tiktok".
        social_copy: Dict of platform → {"caption": ..., "hashtags": [...], "title": ...}.
        schedule:   Reserved for future scheduled publishing support.

    Returns:
        List of result dicts with keys: platform, status, post_url, error.
    """
    # social_copy may use script-style keys (youtube_shorts, instagram_reels)
    # OR publish-style keys (youtube, instagram). Support both by building a lookup
    # that checks the short key first, then the long platform key.
    _COPY_KEY_ALIASES: dict[str, list[str]] = {
        "youtube": ["youtube", "youtube_shorts"],
        "instagram": ["instagram", "instagram_reels"],
        "tiktok": ["tiktok"],
    }

    def _get_copy(platform: str) -> dict:
        for key in _COPY_KEY_ALIASES.get(platform, [platform]):
            if key in social_copy:
                return social_copy[key]
        # Fall back to the first available platform copy (e.g. instagram_reels
        # when the script was generated for a single platform)
        if social_copy:
            return next(iter(social_copy.values()))
        return {}

    tasks = []

    for platform in platforms:
        copy = _get_copy(platform)
        caption = copy.get("caption", "")
        hashtags = copy.get("hashtags", [])
        title = copy.get("title", "") or copy.get("caption", "")
        full_caption = f"{caption}\n{' '.join(hashtags)}".strip() if hashtags else caption

        if platform == "youtube":
            # Append #Shorts so YouTube classifies the video as a Short
            yt_title = f"{title} #Shorts" if title and "#Shorts" not in title else (title or "New Video #Shorts")
            yt_description = f"{full_caption}\n\n#Shorts".strip() if "#Shorts" not in full_caption else full_caption
            tasks.append(_publish_youtube(project_id, title=yt_title[:100], description=yt_description[:5000], tags=hashtags))
        elif platform == "instagram":
            tasks.append(_publish_instagram(project_id, caption=full_caption))
        elif platform == "tiktok":
            tasks.append(_publish_tiktok(project_id, title=title or "New Video"))
        else:
            tasks.append(_unknown_platform(platform))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for platform, result in zip(platforms, results):
        if isinstance(result, Exception):
            output.append({"platform": platform, "status": "failed", "error": str(result)})
        else:
            output.append(result)

    return output
