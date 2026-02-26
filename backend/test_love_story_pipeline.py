"""Love Story Series — normal process pipeline test.

Series config (manual):
  - Format:      Storytelling
  - Niche:       Romantic love story / emotional journey
  - Voice:       Rachel (warm, intimate)
  - Art style:   Watercolor Dream
  - Captions:    Elegant (sentence case, soft)
  - Music:       Happy Rhythm (uplifting / emotional)
  - Duration:    30-40 seconds
  - Platforms:   Instagram Reels + TikTok

Tests every pipeline component:
  Series creation → Script generation (Claude agent)
  → Voiceover (ElevenLabs) → Video generation (Gemini + FFmpeg)
  → Captions (SRT) → Composition → S3 upload → Download

Run with server on port 8000:
    python3 test_love_story_pipeline.py
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
    "I never believed in love at first sight — until I saw her. "
    "She was standing in the rain, laughing at nothing, completely unbothered. "
    "I thought: who is this person who finds joy where the rest of us find inconvenience? "
    "I didn't say a word that day. "
    "But something shifted inside me, like a door I'd forgotten was there slowly swinging open. "
    "Weeks passed. We kept crossing paths the way the universe does when it's trying to tell you something. "
    "Coffee shops. Bookstores. That one corner of the park nobody else seemed to know about. "
    "The day I finally spoke to her, my heart was louder than my voice. "
    "She smiled — the kind that starts slow and ends in the eyes — and said: took you long enough. "
    "She knew. She had always known. "
    "And in that moment, I understood: love isn't a lightning bolt. "
    "It's the quiet courage to walk toward the person who already feels like home."
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
header(1, "Create Love Story series")

resp = httpx.post(
    f"{BASE_URL}/series",
    json={
        "series_name": "Love in Quiet Moments",
        "video_format": "storytelling",
        "niche": "romantic love story and emotional journey",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",   # Rachel — warm, intimate
        "art_style": "ghibli",
        "caption_style": "elegant",
        "video_duration": "30-40",
        "background_music": "happy_rhythm",
        "music_volume": 0.18,
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
ok(f"Voice:        Rachel  ({config['voice_id']})")
ok(f"Art style:    {config['art_style']}")
ok(f"Captions:     {config['caption_style']}")
ok(f"Music:        {config['background_music']}  (vol={config['music_volume']})")
ok(f"Format:       {config.get('video_format', '?')}")


# ── Step 2: Run full pipeline ──────────────────────────────────────────────────
header(2, "Run full pipeline  (Claude → ElevenLabs → Gemini → FFmpeg → S3)")
info(f"Project ID:  {PROJECT_ID}")
info(f"Transcript:  {TRANSCRIPT[:80]}...")

resp = httpx.post(
    f"{BASE_URL}/projects/{PROJECT_ID}/process",
    json={
        "transcript": TRANSCRIPT,
        "series_id": series_id,
        "target_platforms": ["instagram_reels", "tiktok"],
        "style": "dramatic",
        "brand_voice": "warm, intimate, poetic — the feeling of falling in love told through quiet moments",
        "cta_preference": "follow for more love stories",
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

output_path = OUTPUT_DIR / "love_story_final.mp4"
master_s3_key = f"projects/{PROJECT_ID}/master/composed.mp4"
info(f"Downloading: {master_s3_key}")

asyncio.run(s3_service.download_file(master_s3_key, str(output_path)))
size_kb = output_path.stat().st_size // 1024
ok(f"Saved: {output_path}  ({size_kb} KB)")


# ── Done ───────────────────────────────────────────────────────────────────────
print(f"\n{'═' * 62}")
print("  PIPELINE COMPLETE — Love in Quiet Moments")
print(f"{'═' * 62}")
print(f"  Project ID:    {PROJECT_ID}")
print(f"  Series ID:     {series_id}")
print(f"  Transcript:    {TRANSCRIPT[:65]}...")
print(f"  Scenes:        {len(scenes)}")
print(f"  Quality:       {metadata.get('agent_quality_score', '?')}/100")
print(f"  Voice:         Rachel (warm, intimate)")
print(f"  Art style:     Ghibli")
print(f"  Captions:      Elegant (soft, sentence case)")
print(f"  Music:         Happy Rhythm (uplifting / emotional)")
print(f"  Motion:        Gemini chain-editing (living painting effect)")
print(f"  Final video:   {output_path}  ({size_kb} KB)")
print()
print(f"  Play:  ffplay {output_path}")
print()
for platform, url in video_urls.items():
    print(f"  {platform:20s}  {url}")
print()
