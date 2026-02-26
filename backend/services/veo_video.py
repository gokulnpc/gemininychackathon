"""Veo 3 video generation for Content Factory.

Replaces gemini_image.py + FFmpeg image animation.

Instead of generating a static image and animating it with zoompan effects,
Veo 3 generates an actual video clip per scene — real motion, physics, and
native audio (ambient sound). This is a fundamentally better pipeline.

Two modes:
  - Text-to-video  (scene 0 or scene boundaries): text prompt → 5-8s video clip
  - Image-to-video (within a scene):              first-frame image + prompt → clip

Output: 9:16 MP4 clip per scene, then FFmpeg concatenates + adds voiceover + captions.

Falls back to gemini_image if Vertex AI is not configured.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time

from config import get_settings

logger = logging.getLogger(__name__)

VEO_MODEL = "veo-3.0-generate-preview"
LOCATION = "us-central1"

_STYLE_SUFFIX = (
    "vertical 9:16 portrait composition, "
    "ultra-cinematic, dramatic directional lighting, "
    "rich vivid colors, hyper-detailed"
)


# ── Vertex AI Veo REST helpers ─────────────────────────────────────────────────

def _get_access_token() -> str | None:
    """Get a Google Cloud access token using Application Default Credentials."""
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception as e:
        logger.debug("GCP credentials unavailable: %s", e)
        return None


def _veo_generate_sync(
    prompt: str,
    project_id: str,
    duration_seconds: int = 6,
    image_b64: str | None = None,
    image_mime: str = "image/png",
) -> bytes | None:
    """Synchronous Veo 3 call via Vertex AI REST API. Returns raw MP4 bytes or None."""
    import json
    import urllib.request

    token = _get_access_token()
    if not token:
        return None

    url = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{project_id}/locations/{LOCATION}/"
        f"publishers/google/models/{VEO_MODEL}:predictLongRunning"
    )

    instance: dict = {"prompt": f"{prompt}, {_STYLE_SUFFIX}"}
    if image_b64:
        instance["image"] = {"bytesBase64Encoded": image_b64, "mimeType": image_mime}

    body = json.dumps({
        "instances": [instance],
        "parameters": {
            "durationSeconds": duration_seconds,
            "aspectRatio": "9:16",
            "negativePrompt": "blur, distorted, low quality, watermark",
        },
    }).encode()

    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            operation = json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("Veo submit failed: %s", e)
        return None

    operation_name = operation.get("name")
    if not operation_name:
        logger.warning("Veo: no operation name in response")
        return None

    logger.info("Veo operation started: %s", operation_name)

    # Poll until done (max 5 minutes)
    poll_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{operation_name}"
    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(10)
        poll_req = urllib.request.Request(
            poll_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                status = json.loads(resp.read().decode())
        except Exception as e:
            logger.warning("Veo poll failed: %s", e)
            continue

        if status.get("done"):
            if "error" in status:
                logger.warning("Veo operation failed: %s", status["error"])
                return None

            # Extract video bytes from response
            response_data = status.get("response", {})
            predictions = response_data.get("predictions", [])
            if predictions:
                import base64
                video_b64 = predictions[0].get("bytesBase64Encoded", "")
                if video_b64:
                    logger.info("Veo video received (%d b64 chars)", len(video_b64))
                    return base64.b64decode(video_b64)
            logger.warning("Veo done but no video in response")
            return None

    logger.warning("Veo timed out after 5 minutes")
    return None


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 6,
    first_frame_path: str | None = None,
) -> str:
    """Generate a video clip using Veo 3 on Vertex AI.

    Args:
        prompt:           Scene visual description.
        duration_seconds: Clip length (5-8s recommended per scene).
        first_frame_path: If provided, use this image as the first frame
                          (image-to-video mode for smoother scene transitions).

    Returns:
        Absolute path to a 9:16 MP4 temp file.

    Falls back to gemini_image.generate_image() + FFmpeg animation if
    Vertex AI is not configured.
    """
    settings = get_settings()
    project_id = settings.google_cloud_project

    # ── Try Veo 3 ─────────────────────────────────────────────────────────────
    if project_id:
        image_b64: str | None = None
        image_mime = "image/png"

        if first_frame_path and os.path.exists(first_frame_path):
            import base64
            with open(first_frame_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(first_frame_path)[1].lower()
            image_mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

        logger.info("Veo [%s] %ds → %s", "img2vid" if image_b64 else "txt2vid", duration_seconds, prompt[:80])

        video_bytes = await asyncio.to_thread(
            _veo_generate_sync,
            prompt, project_id, max(5, min(8, duration_seconds)), image_b64, image_mime,
        )

        if video_bytes:
            tmp_path = tempfile.mktemp(suffix=".mp4", prefix="voicevid_veo_")
            with open(tmp_path, "wb") as f:
                f.write(video_bytes)
            logger.info("Veo clip saved → %s (%d bytes)", tmp_path, len(video_bytes))
            return tmp_path

        logger.warning("Veo generation failed — falling back to Gemini image + FFmpeg")

    # ── Fallback: Gemini image → FFmpeg zoompan (original pipeline) ───────────
    from services import gemini_image, ffmpeg as ffmpeg_svc

    image_path = await gemini_image.generate_image(
        prompt=prompt,
        previous_image_path=first_frame_path,
    )

    tmp_path = tempfile.mktemp(suffix=".mp4", prefix="voicevid_fallback_")
    effect = "zoom_in"  # default effect for fallback
    ffmpeg_svc.animate_image(
        image_path=image_path,
        effect=effect,
        duration=float(duration_seconds),
        output_path=tmp_path,
    )

    # Clean up temp image
    try:
        os.unlink(image_path)
    except OSError:
        pass

    logger.info("Fallback clip saved → %s", tmp_path)
    return tmp_path
