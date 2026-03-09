"""Lyria background music generation via Vertex AI.

Model: lyria-002
Output: ~32.8s WAV at 48kHz stereo — drop-in replacement for static MP3 presets.

User selects MusicPreset.lyria to get AI-generated music tuned to their video's
style/niche. All other MusicPreset values use static MP3 files from assets/music/.

Prerequisite:
    gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import tempfile
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

MODEL = "lyria-002"

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


def _build_lyria_prompt(style: str | None, niche: str | None) -> str:
    """Build the best Lyria prompt from available context."""
    if style and style.lower() in _STYLE_PROMPTS:
        return _STYLE_PROMPTS[style.lower()]
    if niche:
        return f"background music suited for {niche} video content, professional, engaging, unobtrusive"
    return _FALLBACK_PROMPT


def _invoke_lyria(prompt: str, project_id: str, location: str) -> bytes:
    """Synchronous Vertex AI REST call — run via asyncio.to_thread."""
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
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sample_count": 1},
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Lyria HTTP {exc.code}: {body}") from exc

    b64_wav = result["predictions"][0]["audioContent"]
    return base64.b64decode(b64_wav)


async def generate_music(
    music_preset: str,
    project_id: str,
    location: str = "us-central1",
    style: str | None = None,
    niche: str | None = None,
) -> str:
    """Generate background music WAV using Lyria.

    Args:
        music_preset: "lyria" for context-aware AI music, or a named preset string.
        project_id:   GCP project ID.
        location:     Vertex AI region (default us-central1).
        style:        Art/video style from pipeline (used when music_preset="lyria").
        niche:        Content niche from series config (used when music_preset="lyria").

    Returns:
        Absolute path to a temp WAV file (~32.8s, 48kHz stereo).

    Raises:
        Exception: Propagates Vertex AI errors — caller should catch and handle.
    """
    if music_preset == "lyria":
        prompt = _build_lyria_prompt(style, niche)
    else:
        prompt = _PRESET_PROMPTS.get(music_preset, _FALLBACK_PROMPT)

    logger.info("Lyria: generating music (preset=%s, prompt=%.80s…)", music_preset, prompt)

    try:
        wav_bytes = await asyncio.to_thread(_invoke_lyria, prompt, project_id, location)
    except RuntimeError as exc:
        if "recitation" in str(exc).lower():
            logger.warning("Lyria recitation block on original prompt — retrying with fallback")
            wav_bytes = await asyncio.to_thread(_invoke_lyria, _FALLBACK_PROMPT, project_id, location)
        else:
            raise

    tmp_path = tempfile.mktemp(suffix=".wav", prefix="lyria_music_")
    with open(tmp_path, "wb") as f:
        f.write(wav_bytes)

    logger.info("Lyria music saved → %s (%d bytes)", tmp_path, len(wav_bytes))
    return tmp_path
