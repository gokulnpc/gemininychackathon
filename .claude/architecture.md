# Content Factory — System Architecture

## Full Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT  (manual_test.py / Frontend)                │
│                                                                                 │
│  POST /api/v1/projects/{id}/generate-script                                    │
│  POST /api/v1/projects/{id}/generate-video                                     │
└────────────────────────────┬────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend  (main.py)                               │
│                                                                                 │
│  Routers                    Services                      External APIs         │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                 │
│  routers/script.py          services/gemini_agent.py  ──► Gemini 2.5 Pro       │
│  routers/video.py           services/gemini_reasoning.py ► Gemini 2.5 Pro      │
│  routers/catalog.py         services/gemini_tts.py    ──► Gemini 2.5 Flash TTS │
│  routers/projects.py        services/gemini_image.py  ──► Gemini 2.5 Flash Img │
│  routers/auth.py            services/gemini_audio.py  ──► Gemini (voice flow)  │
│  routers/publish.py         services/ffmpeg.py        ──► FFmpeg (local)       │
│                             services/captions.py                               │
│                             services/gcs.py            ──► Google Cloud Storage │
│                             services/reddit.py          ──► Reddit API          │
│                             services/retry.py                                  │
│                                                                                 │
│  /outputs (StaticFiles) ◄── local video fallback when GCS not configured       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Script Generation

```
Input Source
────────────
source=text  ──► transcript (raw)
source=voice ──► gemini_audio.transcribe_with_tone()
                   │  Gemini multimodal: audio → transcript + detected_tone
                   └─► tone mapped to video style
source=preset ──► preset topic + reddit.fetch_trending(niche)
                   └─► Reddit hot/controversial posts injected as context

                    ┌──────────────────────────────────────┐
                    │   Gemini 2.5 Pro — Agent Loop         │
                    │   (gemini_agent.py, MAX_TURNS=14)     │
                    │                                       │
                    │  Turn 1: search_trending_hooks        │
                    │    └─► gemini_reasoning.research_hooks│
                    │         (Gemini 2.5 Pro reasoning)    │
                    │         fallback: _HOOK_LIBRARY dict  │
                    │                                       │
                    │  Turn 2: analyze_brand_voice          │
                    │    └─► pure Python _STYLE_RULES dict  │
                    │                                       │
                    │  Turn 3: optimize_for_platform        │
                    │    └─► pure Python _PLATFORM_GUIDELINES│
                    │                                       │
                    │  Turn 4: validate_script_quality      │
                    │    └─► gemini_reasoning.score_script  │
                    │         (independent quality scorer)  │
                    │         fallback: local scorer        │
                    │                                       │
                    │  Turn 5: finalize_script  ◄── exits   │
                    │    └─► quality_score ≥ 70 required    │
                    │                                       │
                    │  Each turn: call_with_retry()         │
                    │    3 retries, 2s→4s→8s backoff        │
                    │    retries: 503, 429, 500, connection │
                    └──────────────────────────────────────┘
                              │
                              ▼
                    ScriptGenerationResponse
                    ├── hook: { text, duration }
                    ├── scenes[]: { scene_id, duration_seconds=5,
                    │              visual_prompt (60+ words),
                    │              voiceover_text, emotion }
                    ├── cta: { text, type }
                    ├── social_copy: { platform: { caption, hashtags } }
                    ├── voiceover_full_script
                    └── metadata.character_description
```

---

## Phase 2 — Video Generation

```
Script + Settings
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 1 — TTS  (gemini_tts.py)                                                │
│                                                                                 │
│  gemini-2.5-flash-preview-tts                                                  │
│  voice: Aoede / Charon / Fenrir / Kore / Orbit / Autonoe / Zephyr / Puck       │
│  voiceover_full_script ──► raw PCM16 bytes ──► WAV (24kHz, 16-bit mono)        │
│  saved: /tmp/voicevid_tts_*.wav                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 2 — Image Generation  (gemini_image.py)                                 │
│                                                                                 │
│  gemini-2.5-flash-image  →  576×1024 PNG per scene                             │
│                                                                                 │
│  Scene 1 (generation):                                                          │
│    prompt + style_suffix ──────────────────────────────► PNG_1                 │
│                                                                                 │
│  Scene 2 (scene-evolution):                                                     │
│    edit_prompt + PNG_1 ─────────────────────────────────► PNG_2                │
│    (keep characters, change action/angle)                                       │
│                                                                                 │
│  Scene 3+ (consistent-scene):                                                   │
│    edit_prompt + PNG_1 (char ref) + PNG_prev ───────────► PNG_N                │
│    (preserve face/costume from PNG_1, new composition)                          │
│                                                                                 │
│  Art Style → _STYLE_SUFFIXES (19 styles):                                      │
│  monochrome / colour_block / runway / risograph / technicolour / gothic_clay /  │
│  dynamite / salon / sketch / cinematic / steampunk / sunrise / comic /          │
│  creepy_comic / painting / ghibli / polaroid / disney / realism                │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 3 — Animate Images  (ffmpeg.py)                                         │
│                                                                                 │
│  PNG ──► 5s MP4 clip via FFmpeg zoompan (Ken Burns effect)                     │
│                                                                                 │
│  Effect rotation:                                                               │
│    dolly_in → crane_down → zoom_in_right → dolly_out → zoom_in_left → crane_up │
│                                                                                 │
│  FFmpeg filter:  zoompan=z='min(zoom+0.004,1.5)':x=...:y=...:s=576x1024:d=125 │
│  Output codec:   libx264, yuv420p, 25fps, preset=fast                          │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 4 — Captions  (captions.py)                                             │
│                                                                                 │
│  voiceover_full_script ──► word-level SRT file                                 │
│                                                                                 │
│  Caption styles (FFmpeg force_style):                                           │
│  beast        Impact, 26pt, bold, white + thick black outline, upper-center    │
│  bold_stroke  Large bold with stroke                                           │
│  karaoke      Word-highlight progressive style                                 │
│  majestic     Serif, elegant positioning                                       │
│  red_highlight Yellow fill + red border                                        │
│  sleek        Clean minimal sans-serif                                         │
│  elegant      Thin refined font                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 5 — Composition  (ffmpeg.py)                                            │
│                                                                                 │
│  Pass 1: concat         scene_1.mp4 + scene_2.mp4 + ... ──► concat.mp4         │
│  Pass 2: mix voiceover  concat.mp4 + WAV  ──────────────► with_audio.mp4      │
│  Pass 3: burn captions  with_audio.mp4 + SRT ───────────► composed.mp4        │
│  Pass 4: mix music      composed.mp4 + music.mp3 (vol=0.15) ► composed_music  │
│                                                                                 │
│  Background music presets (assets/music/):                                     │
│  breathing_shadows / quiet_before_storm / brilliant_symphony /                 │
│  happy_rhythm / peaceful_vibes                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Stage 6 — Platform Export + Upload  (ffmpeg.py + gcs.py)                     │
│                                                                                 │
│  Platform specs:                                                                │
│  youtube_shorts  1080×1920, 10Mbps, 30fps, max 60s                            │
│  instagram_reels 1080×1920, 8Mbps,  30fps, max 90s                            │
│  tiktok          1080×1920, 8Mbps,  30fps, max 180s                           │
│                                                                                 │
│  Upload:                                                                        │
│  GCS configured   ──► gs://voicevid-assets/projects/{id}/{platform}/final.mp4 │
│                        returns public GCS URL                                   │
│  GCS unavailable  ──► backend/outputs/projects/{id}/{platform}/final.mp4      │
│                        returns http://localhost:8000/outputs/...               │
└─────────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Response                                                                       │
│                                                                                 │
│  {                                                                              │
│    "status": "completed",                                                       │
│    "stages": [ { stage, status, detail }, ... ],                               │
│    "video_urls": {                                                              │
│      "youtube_shorts": "https://storage.googleapis.com/... or localhost/...",  │
│      "master": "..."                                                            │
│    }                                                                            │
│  }                                                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Service Dependency Map

```
main.py
  ├── routers/script.py
  │     ├── services/gemini_agent.py
  │     │     ├── services/gemini_reasoning.py  (hook research + script scoring)
  │     │     └── services/retry.py             (exponential backoff)
  │     ├── services/gemini_audio.py            (voice flow only)
  │     ├── services/reddit.py                  (preset flow only)
  │     └── services/gcs.py                     (series config load)
  │
  ├── routers/video.py
  │     └── services/pipeline_runner.py
  │           ├── services/gemini_tts.py
  │           ├── services/gemini_image.py
  │           ├── services/ffmpeg.py
  │           ├── services/captions.py
  │           └── services/gcs.py
  │
  ├── routers/catalog.py
  │     └── services/gemini_tts.VOICE_CATALOGUE  (GET /voices)
  │
  ├── routers/projects.py
  └── routers/publish.py
        └── services/gcs.py
```

---

## Configuration (.env)

```
GEMINI_API_KEY          ──► All Gemini models (agent, TTS, image, reasoning)
GOOGLE_CLOUD_PROJECT    ──► GCS bucket project ID  (e.g. voicevid)
GCS_BUCKET              ──► Bucket name             (e.g. voicevid-assets)
YOUTUBE_CLIENT_SECRETS_FILE  ──► YouTube OAuth for publish flow
```

## Key Models Used

| Service | Model | Purpose |
|---------|-------|---------|
| gemini_agent.py | `gemini-2.5-pro` | Script director (ReAct agent loop) |
| gemini_reasoning.py | `gemini-2.5-pro` | Hook research + script scoring |
| gemini_tts.py | `gemini-2.5-flash-preview-tts` | Voiceover synthesis |
| gemini_image.py | `gemini-2.5-flash-image` | Scene image generation |
| gemini_audio.py | Gemini multimodal | Audio transcription + tone detection |
