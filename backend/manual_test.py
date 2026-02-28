#!/usr/bin/env python3
"""
Manual test — Preset flow: Scary Stories (15s, Gothic Clay, with character reference)
======================================================================================
Uses:
  - source=preset  (scary_stories)
  - art_style=gothic_clay
  - user character reference: backend/input/gokul.jpeg  (main_character role)

Usage:
    python manual_test.py [--base-url http://localhost:8000]
"""

import argparse
import base64
import json
import os
import sys
import uuid

import httpx

BASE_URL = "http://localhost:8000"

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID = str(uuid.uuid4())

# Character reference image (main character role)
_INPUT_IMAGE = os.path.join(os.path.dirname(__file__), "input", "gokul.jpeg")

SCRIPT_PAYLOAD = {
    "source":            "preset",
    "preset":            "scary_stories",
    "topic_hint":        "a person who keeps waking up at exactly 3:17 AM every night — the shadow on the wall moves before they do",
    "target_platforms":  ["youtube_shorts"],
    "style":             "dramatic",
    "video_format":      "storytelling",
    "video_duration":    15,
    "art_style":         "gothic_clay",
    "caption_style":     "beast",
    "background_music":  "breathing_shadows",
    "cta_preference":    "follow for more horror",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sep(label: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print(f"{'─' * 50}")


def post(base: str, path: str, payload: dict, timeout: float) -> dict:
    url = f"{base}{path}"
    print(f"POST {url}\n")
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


def load_image_b64(path: str) -> str | None:
    if not os.path.exists(path):
        print(f"⚠  Character reference image not found: {path}")
        return None
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    size_kb = os.path.getsize(path) // 1024
    print(f"Character reference loaded: {path} ({size_kb} KB)")
    return data


# ── Main ──────────────────────────────────────────────────────────────────────

def main(base_url: str) -> None:
    print(f"\nProject ID : {PROJECT_ID}")
    print("Art style  : gothic_clay")
    print("Preset     : scary_stories")
    print("Char role  : main_character")

    # ── Phase 1: generate-script (preset flow) ────────────────────────────────
    sep("Phase 1 — Generate Script  (preset: scary_stories)")
    script = post(
        base_url,
        f"/api/v1/projects/{PROJECT_ID}/generate-script",
        SCRIPT_PAYLOAD,
        timeout=180.0,
    )

    print(f"Quality score : {script.get('metadata', {}).get('agent_quality_score', 'n/a')}/100")
    print(f"Hook          : {script.get('hook', {}).get('text', '')}")
    print(f"Scenes        : {len(script.get('scenes', []))}")
    for s in script.get("scenes", []):
        print(f"  Scene {s['scene_id']} [{s.get('duration_seconds')}s]: {s.get('voiceover_text', '')[:80]}")
    print(f"CTA           : {script.get('cta', {}).get('text', '')}")
    char_desc = script.get("metadata", {}).get("character_description", "")
    if char_desc:
        print(f"Char desc     : {char_desc[:120]}")

    # ── Phase 2: generate-video (with character reference image) ─────────────
    sep("Phase 2 — Generate Video  (gothic_clay, user=main_character)")

    # Load user photo as base64
    user_image_b64 = load_image_b64(_INPUT_IMAGE)

    video_payload = {
        "script":                script,
        "target_platforms":      ["youtube_shorts"],
        "caption_style":         "beast",
        "video_duration":        15,
        "art_style_override":    "gothic_clay",
        "music_preset_override": "breathing_shadows",
        # Character reference
        "user_reference_image_b64": user_image_b64,
        "user_character_role":      "main_character" if user_image_b64 else None,
    }

    pipeline = post(
        base_url,
        f"/api/v1/projects/{PROJECT_ID}/generate-video",
        video_payload,
        timeout=600.0,
    )

    sep("Result")
    print(f"Status: {pipeline.get('status')}\n")
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
