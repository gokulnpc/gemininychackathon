"""Weather audio — smart process pipeline test.

Uses the real audio file: backend/input/weather_caudio.m4a

Smart-process stages tested:
  Stage 0:  Transcribe audio      (ElevenLabs Scribe v2)
  Stage 1:  Reddit Research        (trending topics for detected niche)
  Stage 2:  Databricks Analytics   (historical performance data)
  Stage 3:  Nemotron Config        (5-agent auto-configuration)
  Stage 4:  Create series in S3
  Stage 5:  Script generation      (Claude agent: hook → scenes → CTA)
  Stage 6:  Voiceover              (ElevenLabs TTS + word timestamps)
  Stage 7:  Video generation       (Nova Canvas + FFmpeg, 1 image/5 words)
  Stage 8:  Caption generation     (SRT with Nemotron-chosen style)
  Stage 9:  Video composition      (FFmpeg: clips + voiceover + captions + music)
  Stage 10: Export & S3 upload

Run with server on port 8000:
    python3 test_smart_process_weather.py
"""

import asyncio
import base64
import sys
import uuid
from pathlib import Path

import os

import httpx

BASE_URL   = os.getenv("API_BASE_URL", "http://127.0.0.1:8000") + "/api/v1"
AUDIO_FILE = Path(__file__).parent / "input" / "weather_caudio.m4a"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

PROJECT_ID = str(uuid.uuid4())


# ── Helpers ────────────────────────────────────────────────────────────────────

def header(n: int, title: str):
    print(f"\n{'═' * 64}")
    print(f"  STEP {n}: {title}")
    print(f"{'═' * 64}")


def ok(msg: str):
    print(f"  ✓  {msg}")


def info(msg: str):
    print(f"  ·  {msg}")


def warn(msg: str):
    print(f"  ⚠  {msg}")


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


def print_nemotron_config(cfg: dict):
    if not cfg:
        warn("No Nemotron config in response")
        return
    print()
    print("  ┌─ Nemotron Auto-Config ──────────────────────────────────┐")
    print(f"  │  Series:      {cfg.get('series_name', '?'):<42} │")
    print(f"  │  Niche:       {cfg.get('niche', '?'):<42} │")
    print(f"  │  Art style:   {cfg.get('art_style', '?'):<42} │")
    print(f"  │  Captions:    {cfg.get('caption_style', '?'):<42} │")
    print(f"  │  Music:       {cfg.get('background_music', '?')} (vol={cfg.get('music_volume', '?')}){'':<20} │")
    print(f"  │  Voice:       {cfg.get('voice_name', '?')} ({cfg.get('voice_id', '?')[:24]})")
    print(f"  │  Duration:    {cfg.get('video_duration', '?'):<42} │")
    print(f"  │  Format:      {cfg.get('video_format', '?'):<42} │")
    print(f"  │  Platforms:   {', '.join(cfg.get('target_platforms', [])):<38} │")
    print(f"  │  By:          {cfg.get('configured_by', '?'):<42} │")
    print("  └─────────────────────────────────────────────────────────┘")
    reasoning = cfg.get("reasoning", "")
    if reasoning:
        print()
        print("  Nemotron reasoning:")
        # Wrap at 60 chars
        words = reasoning.split()
        line, lines = [], []
        for w in words:
            if sum(len(x) + 1 for x in line) + len(w) > 58:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        for l in lines:
            print(f"    {l}")
    print()


# ── Step 1: Encode audio ───────────────────────────────────────────────────────
header(1, f"Encode audio file  ({AUDIO_FILE.name})")

if not AUDIO_FILE.exists():
    fail(f"Audio file not found: {AUDIO_FILE}")

audio_bytes = AUDIO_FILE.read_bytes()
audio_b64 = base64.b64encode(audio_bytes).decode()
ok(f"File:    {AUDIO_FILE}")
ok(f"Size:    {len(audio_bytes):,} bytes  ({len(audio_bytes) // 1024} KB)")
ok(f"Base64:  {len(audio_b64):,} chars")


# ── Step 2: Run smart-process ──────────────────────────────────────────────────
header(2, "Run smart-process pipeline  (Reddit → Databricks → Nemotron → Claude → video)")
info(f"Project ID:  {PROJECT_ID}")
info("Letting Nemotron auto-configure everything from the audio...")
info("Stages: Transcribe → Reddit → Databricks → Nemotron → Script → Voiceover → Video → Upload")

resp = httpx.post(
    f"{BASE_URL}/projects/{PROJECT_ID}/smart-process",
    json={
        "audio_base64":     audio_b64,
        "audio_format":     "m4a",
        "target_platforms": ["instagram_reels", "tiktok", "youtube_shorts"],
        # niche is intentionally omitted — let Reddit auto-detect it from transcript
    },
    timeout=900.0,   # smart-process is longer: transcribe + reddit + nemotron + full pipeline
)

if resp.status_code != 200:
    fail(f"Smart-process failed {resp.status_code}: {resp.text[:800]}")

result = resp.json()

# ── Stage breakdown ────────────────────────────────────────────────────────────
print_stages(result.get("stages", []))

if result["status"] != "completed":
    fail(f"Pipeline status: {result['status']} | error: {result.get('error')}")

ok("Smart-process completed!")

# ── Nemotron config ────────────────────────────────────────────────────────────
header(3, "Nemotron auto-configuration results")
print_nemotron_config(result.get("nemotron_config", {}))

# ── Script details ─────────────────────────────────────────────────────────────
header(4, "Generated script (Claude agent)")
script = result.get("script", {})
hook = script.get("hook", {})
scenes = script.get("scenes", [])
metadata = script.get("metadata", {})

ok(f"Quality score:  {metadata.get('agent_quality_score', '?')}/100")
ok(f"Hook:           {hook.get('text', '?')}")
ok(f"Scenes:         {len(scenes)}")

for i, s in enumerate(scenes):
    emotion  = s.get("emotion", "?")
    duration = s.get("duration_seconds", "?")
    ok(f"  Scene {i+1}: emotion={emotion:<12} duration={duration}s  |  {s.get('voiceover_text', '')[:55]}...")

# ── Video URLs ─────────────────────────────────────────────────────────────────
video_urls = result.get("video_urls", {})
ok(f"Videos generated: {list(video_urls.keys())}")


# ── Step 5: Download final video ───────────────────────────────────────────────
header(5, "Download final video from S3")

sys.path.insert(0, ".")
from services import s3 as s3_service  # noqa: E402

output_path = OUTPUT_DIR / "smart_weather_final.mp4"
master_s3_key = f"projects/{PROJECT_ID}/master/composed.mp4"
info(f"Downloading: {master_s3_key}")

asyncio.run(s3_service.download_file(master_s3_key, str(output_path)))
size_kb = output_path.stat().st_size // 1024
ok(f"Saved: {output_path}  ({size_kb} KB)")


# ── Final summary ──────────────────────────────────────────────────────────────
nemotron_cfg = result.get("nemotron_config", {})

print(f"\n{'═' * 64}")
print("  SMART-PROCESS COMPLETE — Weather Audio")
print(f"{'═' * 64}")
print(f"  Project ID:      {PROJECT_ID}")
print(f"  Audio source:    {AUDIO_FILE.name}  ({len(audio_bytes) // 1024} KB)")
print(f"  Scenes:          {len(scenes)}")
print(f"  Quality:         {metadata.get('agent_quality_score', '?')}/100")
print()
print("  Nemotron decided:")
print(f"    Series:        {nemotron_cfg.get('series_name', '?')}")
print(f"    Niche:         {nemotron_cfg.get('niche', '?')}")
print(f"    Art style:     {nemotron_cfg.get('art_style', '?')}")
print(f"    Captions:      {nemotron_cfg.get('caption_style', '?')}")
print(f"    Music:         {nemotron_cfg.get('background_music', '?')}")
print(f"    Voice:         {nemotron_cfg.get('voice_name', '?')}")
print(f"    Format:        {nemotron_cfg.get('video_format', '?')}")
print(f"    Platforms:     {', '.join(nemotron_cfg.get('target_platforms', []))}")
print()
print(f"  Final video:     {output_path}  ({size_kb} KB)")
print()
print(f"  Play:  ffplay {output_path}")
print()
for platform, url in video_urls.items():
    print(f"  {platform:22s}  {url}")
print()
