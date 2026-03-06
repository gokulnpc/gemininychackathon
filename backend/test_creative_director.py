#!/usr/bin/env python3
"""
Manual test — Creative Director: Gemini Interleaved Multimodal Output
======================================================================
Tests POST /api/v1/creative-director/generate across all four modes.
Saves generated images to /tmp/creative_director_test/ for inspection.

Usage:
    python test_creative_director.py [--base-url http://localhost:8000] [--mode all|marketing|storybook|educational|social_content]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
ENDPOINT = "/api/v1/creative-director/generate"
OUTPUT_DIR = Path("/tmp/creative_director_test")

# ── Test cases — one per mode ──────────────────────────────────────────────────

TEST_CASES: dict[str, dict] = {
    "marketing": {
        "brief": "An AI-powered fitness coaching app that adapts workouts in real-time for busy professionals who have only 20 minutes a day",
        "mode": "marketing",
        "art_style": "cinematic",
    },
    "storybook": {
        "brief": "A curious girl named Mia discovers that every book in the village library is a door to a living world — and one day, she accidentally lets a dragon out",
        "mode": "storybook",
        "art_style": "ghibli",
    },
    "educational": {
        "brief": "How large language models work — from tokenisation and embeddings through attention and generation — explained for a smart non-technical audience",
        "mode": "educational",
        "art_style": "sketch",
    },
    "social_content": {
        "brief": "The 5 AM morning routine that transformed my productivity — cold shower, journaling, movement, no phone for first hour",
        "mode": "social_content",
        "art_style": "realism",
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def sep(label: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")


def post(base: str, payload: dict, timeout: float = 120.0) -> dict:
    url = f"{base}{ENDPOINT}"
    print(f"POST {url}")
    print(f"  mode={payload['mode']}  art_style={payload.get('art_style','none')}")
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        print(f"  HTTP {e.response.status_code}: {e.response.text[:400]}")
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"  Connection error: {e}")
        sys.exit(1)


def save_blocks(mode: str, blocks: list[dict], out_dir: Path) -> None:
    """Save image blocks to disk; print text blocks to stdout."""
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    img_count = 0
    for i, block in enumerate(blocks):
        if block["type"] == "text":
            print(f"\n  [text #{i}]\n  {block['content'][:300]}")
            if len(block["content"]) > 300:
                print(f"  ... ({len(block['content'])} chars total)")
        elif block["type"] == "image":
            img_count += 1
            ext = block.get("mime_type", "image/png").split("/")[-1]
            fname = mode_dir / f"block_{i:02d}_img{img_count}.{ext}"
            raw = base64.b64decode(block["content"])
            fname.write_bytes(raw)
            print(f"\n  [image #{i}] saved → {fname} ({len(raw):,} bytes)")


def print_summary(mode: str, result: dict, elapsed: float) -> None:
    print(f"\n  package_id    : {result.get('package_id')}")
    print(f"  total_blocks  : {len(result.get('blocks', []))}")
    print(f"  text_blocks   : {result.get('total_text_blocks')}")
    print(f"  images        : {result.get('total_images')}")
    print(f"  elapsed       : {elapsed:.1f}s")


def run_mode(base: str, mode: str) -> bool:
    payload = TEST_CASES[mode]
    sep(f"Mode: {mode.upper()}  |  art_style: {payload.get('art_style', 'none')}")
    print(f"  Brief: {payload['brief'][:100]}...")

    t0 = time.time()
    result = post(base, payload)
    elapsed = time.time() - t0

    save_blocks(mode, result.get("blocks", []), OUTPUT_DIR)
    print_summary(mode, result, elapsed)
    return True


def check_health(base: str) -> None:
    try:
        r = httpx.get(f"{base}/health", timeout=5.0)
        r.raise_for_status()
        print(f"Backend health: {r.json()}")
    except Exception as e:
        print(f"Backend not reachable at {base}: {e}")
        sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main(base_url: str, mode: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nCreative Director Test")
    print(f"  base_url   : {base_url}")
    print(f"  output_dir : {OUTPUT_DIR}")
    print(f"  mode(s)    : {mode}")

    check_health(base_url)

    modes_to_run = list(TEST_CASES.keys()) if mode == "all" else [mode]

    results = []
    for m in modes_to_run:
        ok = run_mode(base_url, m)
        results.append((m, ok))

    sep("SUMMARY")
    for m, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {m}")

    print(f"\nImages saved to: {OUTPUT_DIR}/")
    print("Open with:  open /tmp/creative_director_test/  (macOS)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Creative Director endpoint")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "marketing", "storybook", "educational", "social_content"],
        help="Which mode to test (default: all)",
    )
    args = parser.parse_args()
    main(args.base_url, args.mode)
