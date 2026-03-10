#!/usr/bin/env python3
"""
Manual end-to-end pipeline test — all three input flows.
=========================================================
Tests the full two-step flow for each source type:
  1. POST /api/v1/projects/{id}/generate-script
  2. POST /api/v1/projects/{id}/generate-video

All tests use gokul.jpeg as the user reference image (main_character role).
Voice test uses weather_caution.m4a as the audio input.

NOTE: generate-video runs synchronously in local dev (no WORKER_URL set).
      Each video test blocks for ~8-10 minutes. Use --skip-video to test
      only script generation quickly.

Usage:
    # Start the server first:
    #   cd backend && uvicorn main:app --reload

    python test_pipeline.py                    # run all 3 tests
    python test_pipeline.py --test preset      # preset flow only
    python test_pipeline.py --test text        # text flow only
    python test_pipeline.py --test voice       # voice flow only
    python test_pipeline.py --skip-video       # only test script generation
    python test_pipeline.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

BASE_URL = "http://localhost:8000"
INPUT_DIR = Path(__file__).parent / "input"
OUTPUT_DIR = Path("/tmp/pipeline_test")

USER_REF_IMAGE = INPUT_DIR / "gokul.jpeg"
VOICE_AUDIO    = INPUT_DIR / "weather_caudio.m4a"

# Timeout for generate-video (sync mode, up to 15 min)
VIDEO_TIMEOUT = 900

# This file is a manual end-to-end runner and should not be collected in
# automated pytest integration runs.
try:
    import pytest
    pytestmark = pytest.mark.skip(reason="Manual E2E runner; execute as a script, not as pytest tests.")
except Exception:
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _print_sep(label: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print('─' * 60)


def _print_script_summary(data: dict) -> None:
    hook = data.get("hook", {}).get("text", "—")
    scenes = data.get("scenes", [])
    quality = data.get("metadata", {}).get("agent_quality_score", "—")
    print(f"  Hook       : {hook[:80]}...")
    print(f"  Scenes     : {len(scenes)}")
    print(f"  Quality    : {quality}/100")
    for i, s in enumerate(scenes[:3], 1):
        print(f"  Scene {i}   : [{s.get('emotion','?')}] {s.get('voiceover_text','')[:60]}...")


def _print_video_summary(data: dict, out_dir: Path) -> None:
    status = data.get("status", "—")
    urls   = data.get("video_urls", {})
    thumb  = data.get("thumbnail_url")
    stages = data.get("stages", [])
    error  = data.get("error")

    print(f"  Status     : {status}")
    if error:
        print(f"  Error      : {error}")

    for stage in stages:
        icon = "✓" if stage.get("status") == "completed" else "✗"
        print(f"  {icon} {stage.get('stage', '?'):20s} {stage.get('detail') or ''}")

    for platform, url in urls.items():
        print(f"  Video [{platform}] : {url}")

    if thumb:
        # Try to save thumbnail locally
        if thumb.startswith("http"):
            print(f"  Thumbnail  : {thumb}")
        else:
            print(f"  Thumbnail  : {thumb}")


# ── Common generate-video payload builder ────────────────────────────────────

def _video_payload(script: dict, user_ref_b64: str) -> dict:
    return {
        "script":                   script,
        "target_platforms":         ["instagram_reels"],
        "caption_style":            "bold_stroke",
        "video_duration":           30,
        "voice_id":                 "Aoede",
        "art_style_override":       "cinematic",
        "music_preset_override":    "none",
        "user_reference_image_b64": user_ref_b64,
        "user_character_role":      "main_character",
    }


# ── Test 1: Preset flow ───────────────────────────────────────────────────────

def test_preset(client: httpx.Client, user_ref_b64: str, skip_video: bool) -> bool:
    _print_sep("TEST 1 — PRESET FLOW (scary_stories)")
    project_id = str(uuid4())

    # Step 1: generate-script
    print(f"\n[1/2] Generating script (project_id={project_id}) ...")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-script",
        json={
            "source":           "preset",
            "preset":           "scary_stories",
            "topic_hint":       "haunted forest at midnight",
            "target_platforms": ["instagram_reels"],
            "style":            "dramatic",
            "video_duration":   30,
            "caption_style":    "bold_stroke",
            "art_style":        "cinematic",
            "background_music": "breathing_shadows",
            "voice_id":         "Aoede",
            "video_format":     "storytelling",
        },
        timeout=300,
    )
    resp.raise_for_status()
    script = resp.json()
    print(f"  Script generated in {time.time() - t0:.1f}s")
    _print_script_summary(script)

    if skip_video:
        print("\n  [skip-video] Skipping generate-video step.")
        return True

    # Step 2: generate-video
    out_dir = OUTPUT_DIR / "preset"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[2/2] Generating video (this takes ~8-10 min) ...")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-video",
        json=_video_payload(script, user_ref_b64),
        timeout=VIDEO_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"  Video generated in {time.time() - t0:.1f}s")
    _print_video_summary(result, out_dir)

    # Save full response
    (out_dir / "response.json").write_text(json.dumps(result, indent=2))
    print(f"\n  Full response saved → {out_dir / 'response.json'}")
    return result.get("status") == "completed"


# ── Test 2: Text flow ─────────────────────────────────────────────────────────

def test_text(client: httpx.Client, user_ref_b64: str, skip_video: bool) -> bool:
    _print_sep("TEST 2 — TEXT FLOW")
    project_id = str(uuid4())

    transcript = (
        "The 5 rules billionaires follow that nobody talks about. "
        "Rule 1: They protect their time more than their money. "
        "Rule 2: They invest in learning, not just assets. "
        "Rule 3: They surround themselves with people smarter than them. "
        "Rule 4: They fail fast and move on without regret. "
        "Rule 5: They think in decades, not quarters."
    )

    # Step 1: generate-script
    print(f"\n[1/2] Generating script (project_id={project_id}) ...")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-script",
        json={
            "source":           "text",
            "transcript":       transcript,
            "target_platforms": ["instagram_reels"],
            "style":            "modern_energetic",
            "video_duration":   30,
            "caption_style":    "beast",
            "art_style":        "realism",
            "background_music": "happy_rhythm",
            "voice_id":         "Aoede",
            "video_format":     "five_things",
        },
        timeout=300,
    )
    resp.raise_for_status()
    script = resp.json()
    print(f"  Script generated in {time.time() - t0:.1f}s")
    _print_script_summary(script)

    if skip_video:
        print("\n  [skip-video] Skipping generate-video step.")
        return True

    # Step 2: generate-video
    out_dir = OUTPUT_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[2/2] Generating video (this takes ~8-10 min) ...")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-video",
        json=_video_payload(script, user_ref_b64),
        timeout=VIDEO_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"  Video generated in {time.time() - t0:.1f}s")
    _print_video_summary(result, out_dir)

    (out_dir / "response.json").write_text(json.dumps(result, indent=2))
    print(f"\n  Full response saved → {out_dir / 'response.json'}")
    return result.get("status") == "completed"


# ── Test 3: Voice flow ────────────────────────────────────────────────────────

def test_voice(client: httpx.Client, user_ref_b64: str, skip_video: bool) -> bool:
    _print_sep("TEST 3 — VOICE FLOW (weather_caution.m4a)")

    if not VOICE_AUDIO.exists():
        print(f"  ERROR: voice file not found: {VOICE_AUDIO}")
        return False

    project_id = str(uuid4())
    audio_b64  = _b64(VOICE_AUDIO)

    # Step 1: generate-script
    print(f"\n[1/2] Generating script (project_id={project_id}) ...")
    print(f"  Audio file : {VOICE_AUDIO} ({VOICE_AUDIO.stat().st_size // 1024} KB)")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-script",
        json={
            "source":           "voice",
            "audio_base64":     audio_b64,
            "audio_format":     "m4a",
            "target_platforms": ["instagram_reels"],
            "video_duration":   30,
            "caption_style":    "karaoke",
            "art_style":        "realism",
            "background_music": "none",
            "voice_id":         "Aoede",
            "video_format":     "storytelling",
        },
        timeout=300,
    )
    resp.raise_for_status()
    script = resp.json()
    print(f"  Script generated in {time.time() - t0:.1f}s")
    _print_script_summary(script)

    if skip_video:
        print("\n  [skip-video] Skipping generate-video step.")
        return True

    # Step 2: generate-video
    out_dir = OUTPUT_DIR / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[2/2] Generating video (this takes ~8-10 min) ...")
    t0 = time.time()
    resp = client.post(
        f"/api/v1/projects/{project_id}/generate-video",
        json=_video_payload(script, user_ref_b64),
        timeout=VIDEO_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"  Video generated in {time.time() - t0:.1f}s")
    _print_video_summary(result, out_dir)

    (out_dir / "response.json").write_text(json.dumps(result, indent=2))
    print(f"\n  Full response saved → {out_dir / 'response.json'}")
    return result.get("status") == "completed"


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end pipeline tests")
    parser.add_argument("--base-url",   default=BASE_URL, help="API base URL")
    parser.add_argument("--test",       choices=["preset", "text", "voice", "all"], default="all")
    parser.add_argument("--skip-video", action="store_true", help="Only test script generation (fast)")
    args = parser.parse_args()

    # Validate input files
    if not USER_REF_IMAGE.exists():
        print(f"ERROR: user reference image not found: {USER_REF_IMAGE}")
        print("       Place gokul.jpeg in backend/input/")
        sys.exit(1)

    print(f"\n Pipeline Tests — {args.base_url}")
    print(f" User ref     : {USER_REF_IMAGE} ({USER_REF_IMAGE.stat().st_size // 1024} KB)")
    print(f" Output dir   : {OUTPUT_DIR}")
    if args.skip_video:
        print(" Mode         : script-only (--skip-video)")
    else:
        print(" Mode         : full pipeline (script + video, ~8-10 min per test)")

    # Encode user reference image once
    user_ref_b64 = _b64(USER_REF_IMAGE)

    # Health check
    with httpx.Client(base_url=args.base_url) as client:
        try:
            r = client.get("/health", timeout=5)
            r.raise_for_status()
            print(f"\n Server health : OK ({args.base_url})")
        except Exception as e:
            print(f"\nERROR: Server not reachable at {args.base_url}")
            print(f"       Start it with: uvicorn main:app --reload")
            print(f"       ({e})")
            sys.exit(1)

        results: dict[str, bool] = {}
        run = args.test

        if run in ("preset", "all"):
            try:
                results["preset"] = test_preset(client, user_ref_b64, args.skip_video)
            except Exception as e:
                print(f"\n  FAILED: {e}")
                results["preset"] = False

        if run in ("text", "all"):
            try:
                results["text"] = test_text(client, user_ref_b64, args.skip_video)
            except Exception as e:
                print(f"\n  FAILED: {e}")
                results["text"] = False

        if run in ("voice", "all"):
            try:
                results["voice"] = test_voice(client, user_ref_b64, args.skip_video)
            except Exception as e:
                print(f"\n  FAILED: {e}")
                results["voice"] = False

    # Summary
    _print_sep("RESULTS")
    all_passed = True
    for test_name, passed in results.items():
        icon = "✓" if passed else "✗"
        print(f"  {icon}  {test_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  All tests passed!")
    else:
        print("  Some tests failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
