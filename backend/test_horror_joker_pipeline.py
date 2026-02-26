"""Horror Joker Series — normal process pipeline test.

Series config (manual):
  - Format:      Storytelling
  - Niche:       Psychological horror / Joker-style dark monologue
  - Voice:       Adam (deep, authoritative)
  - Art style:   Creepy Comic
  - Captions:    Beast (1 word, ALL CAPS, heavy impact)
  - Music:       Quiet Before Storm (tense / dramatic)
  - Duration:    30-40 seconds
  - Platforms:   Instagram Reels + TikTok

Tests every pipeline component:
  Series creation → Script generation (Claude agent)
  → Voiceover (ElevenLabs) → Video generation (Nova Canvas + FFmpeg)
  → Captions (SRT) → Composition → S3 upload → Download

Run with server on port 8000:
    python3 test_horror_joker_pipeline.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

import os

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000") + "/api/v1"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

PROJECT_ID = str(uuid.uuid4())

TRANSCRIPT = (
    "Everyone calls me crazy. They say I lost my mind. "
    "But I didn't lose it — I found it. "
    "The moment I stopped pretending to smile, the world made perfect sense. "
    "You want to know the difference between me and you? "
    "I know that the joke is on all of us. "
    "Society gave us rules to follow, labels to wear, cages to call homes. "
    "And we thanked them for it. "
    "But here's the punchline nobody tells you: "
    "the people who built those cages never lived in one. "
    "So go ahead — laugh. Or don't. "
    "Either way, the curtain is falling."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def header(n: int, title: str):
    print(f"\n{'═' * 62}")
    print(f"  STEP {n}: {title}")
    print(f"{'═' * 62}")


def ok(msg: str):
    print(f"  ✓  {msg}")


def info(msg: str):
    print(f"  ·  {msg}")


def fail(msg: str):
    print(f"  ✗  {msg}")
    sys.exit(1)


def print_stages(stages: list[dict]):
    print()
    for stage in stages:
        icon = "✓" if stage["status"] == "completed" else "✗" if stage["status"] == "failed" else "○"
        detail = f"  —  {stage['detail']}" if stage.get("detail") else ""
        print(f"    {icon}  [{stage['stage']}]{detail}")
    print()


# ── Step 1: Create series ──────────────────────────────────────────────────────
header(1, "Create Horror Joker series")

resp = httpx.post(
    f"{BASE_URL}/series",
    json={
        "series_name": "The Joker Monologues",
        "video_format": "storytelling",
        "niche": "psychological horror and dark philosophical monologues",
        "voice_id": "pNInz6obpgDQGcFmaJgB",   # Adam — deep, authoritative
        "art_style": "creepy_comic",
        "caption_style": "beast",
        "video_duration": "30-40",
        "background_music": "quiet_before_storm",
        "music_volume": 0.20,
    },
    timeout=30.0,
)
if resp.status_code != 200:
    fail(f"Series creation failed {resp.status_code}: {resp.text}")

series_data = resp.json()
series_id = series_data["series_id"]
config = series_data["config"]
ok(f"Series ID:    {series_id}")
ok(f"Series name:  {config.get('series_name', '?')}")
ok(f"Voice:        Adam  ({config['voice_id']})")
ok(f"Art style:    {config['art_style']}")
ok(f"Captions:     {config['caption_style']}")
ok(f"Music:        {config['background_music']}  (vol={config['music_volume']})")
ok(f"Format:       {config.get('video_format', '?')}")


# ── Step 2: Run full pipeline ──────────────────────────────────────────────────
header(2, "Run full pipeline  (Claude → ElevenLabs → Nova Canvas → FFmpeg → S3)")
info(f"Project ID:  {PROJECT_ID}")
info(f"Transcript:  {TRANSCRIPT[:80]}...")

resp = httpx.post(
    f"{BASE_URL}/projects/{PROJECT_ID}/process",
    json={
        "transcript": TRANSCRIPT,
        "series_id": series_id,
        "target_platforms": ["instagram_reels", "tiktok"],
        "style": "dramatic",
        "brand_voice": "dark, philosophical, provocative — Joker-style inner monologue",
        "cta_preference": "follow for more dark truths",
    },
    timeout=600.0,
)

if resp.status_code != 200:
    fail(f"Pipeline failed {resp.status_code}: {resp.text[:500]}")

result = resp.json()
print_stages(result.get("stages", []))

if result["status"] != "completed":
    fail(f"Pipeline status: {result['status']} | error: {result.get('error')}")

ok("Pipeline completed!")

# Script details
script = result.get("script", {})
hook = script.get("hook", {})
scenes = script.get("scenes", [])
metadata = script.get("metadata", {})

ok(f"Quality score:  {metadata.get('agent_quality_score', '?')}/100")
ok(f"Hook:           {hook.get('text', '?')}")
ok(f"Scenes:         {len(scenes)}")

for i, s in enumerate(scenes):
    emotion = s.get("emotion", "?")
    ok(f"  Scene {i+1}: emotion={emotion}  |  {s.get('voiceover_text', '')[:65]}...")

# Video URLs
video_urls = result.get("video_urls", {})
ok(f"Videos generated: {list(video_urls.keys())}")


# ── Step 3: Download final video ───────────────────────────────────────────────
header(3, "Download final video from S3")

import sys; sys.path.insert(0, ".")
from services import s3 as s3_service  # noqa: E402

output_path = OUTPUT_DIR / "horror_joker_final.mp4"
master_s3_key = f"projects/{PROJECT_ID}/master/composed.mp4"
info(f"Downloading: {master_s3_key}")

asyncio.run(s3_service.download_file(master_s3_key, str(output_path)))
size_kb = output_path.stat().st_size // 1024
ok(f"Saved: {output_path}  ({size_kb} KB)")


# ── Done ───────────────────────────────────────────────────────────────────────
print(f"\n{'═' * 62}")
print("  PIPELINE COMPLETE — The Joker Monologues")
print(f"{'═' * 62}")
print(f"  Project ID:    {PROJECT_ID}")
print(f"  Series ID:     {series_id}")
print(f"  Transcript:    {TRANSCRIPT[:65]}...")
print(f"  Scenes:        {len(scenes)}")
print(f"  Quality:       {metadata.get('agent_quality_score', '?')}/100")
print(f"  Voice:         Adam (deep, authoritative)")
print(f"  Art style:     Creepy Comic")
print(f"  Captions:      Beast (ALL CAPS, 1 word max)")
print(f"  Music:         Quiet Before Storm (tense)")
print(f"  Motion:        shaky (dramatic/horror) · slide_left (mysterious)")
print(f"  Final video:   {output_path}  ({size_kb} KB)")
print()
print(f"  Play:  ffplay {output_path}")
print()
for platform, url in video_urls.items():
    print(f"  {platform:20s}  {url}")
print()
