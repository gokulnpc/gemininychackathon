"""Lyria background music generation via Vertex AI.

Model: lyria-002
Output: ~30s WAV at 48kHz stereo — drop-in replacement for static MP3 presets.

Production features:
    - Input validation (project_id, prompt)
    - Retry with exponential backoff on transient errors (503, 429, timeout)
    - Recitation fallback (uses neutral prompt on content policy blocks)
    - WAV output validation (RIFF header + minimum size)
    - Secure temp file creation (mkstemp, not mktemp)
    - Optional seed for reproducible output
    - Duration estimation logged for debugging

Prerequisite:
    gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

MODEL = "lyria-002"

# Retry configuration for transient Vertex AI errors.
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds — doubles each retry

# Minimum valid WAV size (bytes) — anything smaller is likely corrupt.
MIN_WAV_SIZE = 1024

# Estimated bytes per second for 48kHz 16-bit stereo WAV.
_BYTES_PER_SEC = 48000 * 2 * 2  # 192,000

# Named preset → Lyria prompt (used when music_preset != "lyria")
_PRESET_PROMPTS: dict[str, str] = {
    "breathing_shadows":  "dark cinematic horror ambient, slow eerie drones, deep bass tension, tense suspense, no melody",
    "quiet_before_storm": "quiet brooding cinematic buildup, restrained low strings, anticipation and dread, minimalist",
    "brilliant_symphony": "uplifting orchestral symphony, triumphant brass and soaring strings, inspiring and epic",
    "happy_rhythm":       "upbeat feel-good pop background, positive driving rhythm, bright and energetic, commercial",
    "peaceful_vibes":     "calm peaceful ambient, soft gentle melodic tones, warm and relaxing, meditative background",
}

# Style / niche → Lyria prompt (used when music_preset == "lyria")
_STYLE_PROMPTS: dict[str, str] = {
    "dramatic":         "cinematic orchestral swell, epic emotional score, sweeping and grand",
    "modern_energetic": "upbeat energetic background music, driving rhythm, motivational and bright",
    "cinematic":        "epic cinematic ambient, sweeping orchestral underscore, atmospheric tension",
    "realism":          "subtle documentary underscore, quiet and understated, natural and organic",
    "scary_stories":    "dark horror ambient, eerie drones, tense suspense, unsettling, no melody",
    "gothic_clay":      "dark gothic orchestral, haunting strings, eerie chamber music, mysterious",
    "surreal":          "dreamlike ambient soundscape, floating ethereal tones, surreal and otherworldly",
    "oil_painting":     "classical chamber music, elegant and refined, sophisticated and graceful",
    "steampunk":        "industrial orchestral, percussive metallic rhythms, adventurous and dramatic",
    "sunrise":          "warm uplifting ambient, hopeful and expansive, gentle acoustic, golden-hour",
}

_FALLBACK_PROMPT = "neutral cinematic ambient background music, professional, unobtrusive, soft and minimal"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_lyria_prompt(style: str | None, niche: str | None) -> str:
    """Build the best Lyria prompt from available context."""
    if style and style.lower() in _STYLE_PROMPTS:
        return _STYLE_PROMPTS[style.lower()]
    if niche:
        return f"background music suited for {niche} video content, professional, engaging, unobtrusive"
    return _FALLBACK_PROMPT


def _validate_inputs(project_id: str, prompt: str) -> None:
    """Validate inputs before making the API call."""
    if not project_id or not project_id.strip():
        raise ValueError("project_id is required and cannot be empty")
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required and cannot be empty")


def _validate_wav_output(wav_bytes: bytes) -> None:
    """Validate that decoded bytes are a valid WAV file."""
    if len(wav_bytes) < MIN_WAV_SIZE:
        raise ValueError(
            f"Lyria output too small ({len(wav_bytes)} bytes) — likely corrupt or empty"
        )
    if not wav_bytes[:4] == b"RIFF":
        raise ValueError(
            f"Lyria output missing RIFF header — got {wav_bytes[:4]!r} instead"
        )


def _estimate_duration(wav_bytes: bytes) -> float:
    """Estimate WAV duration in seconds from byte size."""
    # Subtract ~44 bytes for WAV header
    return max(0.0, (len(wav_bytes) - 44) / _BYTES_PER_SEC)


def _is_transient(exc: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    msg = str(exc).lower()
    transient_indicators = ("503", "429", "timeout", "unavailable", "resource exhausted", "deadline")
    return any(indicator in msg for indicator in transient_indicators)


# ── Core API call ─────────────────────────────────────────────────────────────

def _invoke_lyria(
    prompt: str,
    project_id: str,
    location: str,
    seed: int | None = None,
) -> bytes:
    """Synchronous Vertex AI REST call with retry — run via asyncio.to_thread.

    Returns raw WAV bytes (validated).
    """
    _validate_inputs(project_id, prompt)

    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())

    url = (
        f"https://{location}-aiplatform.googleapis.com/v1"
        f"/projects/{project_id}/locations/{location}"
        f"/publishers/google/models/{MODEL}:predict"
    )

    parameters: dict = {"sample_count": 1}
    if seed is not None:
        parameters["seed"] = seed

    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": parameters,
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
    )

    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
            break  # success
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_exc = RuntimeError(f"Lyria HTTP {exc.code}: {error_body}")

            if attempt < MAX_RETRIES and _is_transient(last_exc):
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Lyria: transient error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, last_exc,
                )
                time.sleep(delay)
            else:
                raise last_exc from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = RuntimeError(f"Lyria network error: {exc}")

            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Lyria: network error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
            else:
                raise last_exc from exc
    else:
        raise last_exc  # type: ignore[misc]

    b64_wav = result["predictions"][0]["bytesBase64Encoded"]
    wav_bytes = base64.b64decode(b64_wav)

    # Validate output
    _validate_wav_output(wav_bytes)

    return wav_bytes


# ── Public async API ──────────────────────────────────────────────────────────

async def generate_music(
    music_preset: str,
    project_id: str,
    location: str = "us-central1",
    style: str | None = None,
    niche: str | None = None,
    seed: int | None = None,
) -> str:
    """Generate background music WAV using Lyria.

    Args:
        music_preset: "lyria" for context-aware AI music, or a named preset string.
        project_id:   GCP project ID.
        location:     Vertex AI region (default us-central1).
        style:        Art/video style from pipeline (used when music_preset="lyria").
        niche:        Content niche from series config (used when music_preset="lyria").
        seed:         Optional seed for reproducible output.

    Returns:
        Absolute path to a temp WAV file (~30s, 48kHz stereo).

    Raises:
        ValueError: If project_id is empty or WAV output is invalid.
        RuntimeError: Propagates Vertex AI errors after retry exhaustion.
    """
    if music_preset == "lyria":
        prompt = _build_lyria_prompt(style, niche)
    else:
        prompt = _PRESET_PROMPTS.get(music_preset, _FALLBACK_PROMPT)

    logger.info("Lyria: generating music (preset=%s, prompt=%.80s…)", music_preset, prompt)

    try:
        wav_bytes = await asyncio.to_thread(
            _invoke_lyria, prompt, project_id, location, seed
        )
    except RuntimeError as exc:
        if "recitation" in str(exc).lower():
            logger.warning("Lyria recitation block on original prompt — retrying with fallback")
            wav_bytes = await asyncio.to_thread(
                _invoke_lyria, _FALLBACK_PROMPT, project_id, location, seed
            )
        else:
            raise

    # Secure temp file (mkstemp, not mktemp)
    fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="lyria_music_")
    try:
        os.write(fd, wav_bytes)
    finally:
        os.close(fd)

    duration = _estimate_duration(wav_bytes)
    logger.info(
        "Lyria music saved → %s (%d bytes, ~%.1fs estimated)",
        tmp_path, len(wav_bytes), duration,
    )
    return tmp_path
