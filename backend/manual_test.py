#!/usr/bin/env python3
"""
Manual test — Horror Story YouTube Short (15s)
==============================================
Hardcoded config. No prompts.

Usage:
    python manual_test.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import uuid

import httpx

BASE_URL = "http://localhost:8000"

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID = str(uuid.uuid4())

SCRIPT_PAYLOAD = {
    "source": "text",
    "transcript": (
        "A horror story about a person who keeps waking up at exactly 3:17 AM "
        "every night. At first they ignore it. Then they notice the shadow on "
        "the wall that doesn't belong to anything in the room. Then one night "
        "the shadow moves before they do."
    ),
    "target_platforms": ["youtube_shorts"],
    "style": "dramatic",
    "video_format": "storytelling",
    "video_duration": 15,
    "art_style": "creepy_comic",
    "caption_style": "beast",
    "background_music": "breathing_shadows",
    "brand_voice": None,
    "cta_preference": "follow for more horror",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def sep(label: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print(f"{'─' * 50}")


def post(base: str, path: str, payload: dict, timeout: float) -> dict:
    url = f"{base}{path}"
    print(f"POST {url}")
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text}")
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Connection error: {e}")
        sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main(base_url: str) -> None:
    print(f"\nProject ID: {PROJECT_ID}")

    # ── Phase 1: generate-script ──────────────────────────────────────────────
    sep("Phase 1 — Generate Script")
    script = post(
        base_url,
        f"/api/v1/projects/{PROJECT_ID}/generate-script",
        SCRIPT_PAYLOAD,
        timeout=120.0,
    )

    print(f"\nQuality score : {script.get('metadata', {}).get('agent_quality_score', 'n/a')}/100")
    print(f"Hook          : {script.get('hook', {}).get('text', '')}")
    print(f"Scenes        : {len(script.get('scenes', []))}")
    for s in script.get("scenes", []):
        print(f"  Scene {s['scene_id']} [{s.get('duration_seconds')}s]: {s.get('voiceover_text', '')[:80]}")
    print(f"CTA           : {script.get('cta', {}).get('text', '')}")

    # ── Phase 2: generate-video ───────────────────────────────────────────────
    sep("Phase 2 — Generate Video  (may take a few minutes)")

    video_payload = {
        "script":                script,
        "target_platforms":      ["youtube_shorts"],
        "caption_style":         "beast",
        "video_duration":        15,
        "art_style_override":    "creepy_comic",
        "music_preset_override": "breathing_shadows",
    }

    pipeline = post(
        base_url,
        f"/api/v1/projects/{PROJECT_ID}/generate-video",
        video_payload,
        timeout=600.0,
    )

    sep("Result")
    print(f"Status: {pipeline.get('status')}")
    for stage in pipeline.get("stages", []):
        icon = "✓" if stage["status"] == "completed" else "✗"
        detail = f"  — {stage['detail']}" if stage.get("detail") else ""
        print(f"  {icon}  {stage['stage']:<25}{detail}")

    urls = pipeline.get("video_urls", {})
    if urls:
        print("\nVideo URLs:")
        for platform, url in urls.items():
            print(f"  {platform:<22}  {url}")

    if pipeline.get("error"):
        print(f"\nError: {pipeline['error']}")

    print(f"\nProject ID: {PROJECT_ID}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    main(args.base_url)
