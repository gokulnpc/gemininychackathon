# Content Factory — System Architecture

## Full Pipeline

```
CLIENT  (manual_test.py / Frontend)
  POST /api/v1/projects/{id}/generate-script
  POST /api/v1/projects/{id}/generate-video
  POST /api/v1/projects/{id}/recompose              ← Phase 4
  POST /api/v1/creative-director/generate           ← Phase 3
  POST /api/v1/creative-director/generate-stream    ← Phase 3 (SSE)
        │
        ▼
FastAPI Backend  (backend/main.py)

Routers                        Services                        External APIs
──────────────────────────────────────────────────────────────────────────────
routers/script.py              services/gemini_agent.py    ──► Gemini 2.5 Pro (Vertex AI)
routers/video.py               services/gemini_reasoning.py ►  Gemini 2.5 Pro (Vertex AI)
routers/catalog.py             services/gemini_tts.py      ──► Gemini 2.5 Flash TTS (API key)
routers/projects.py            services/gemini_image.py    ──► Gemini 3.1 Flash Image (API key)
routers/auth.py                services/gemini_audio.py    ──► Gemini multimodal (API key)
routers/publish.py             services/gemini_interleaved.py ► Gemini 2.0 Flash (API key)
routers/creative_director.py   services/gemini_client.py   ──► Vertex AI / API Key factory
routers/recompose.py           services/ffmpeg.py          ──► FFmpeg (local)
                               services/captions.py
                               services/gcs.py             ──► Google Cloud Storage
                               services/firestore_db.py    ──► Cloud Firestore
                               services/reddit.py          ──► Reddit API
                               services/pipeline_runner.py
                               services/recompose.py
                               services/retry.py
```

---

## Phase 1 — Script Generation

```
Input Source
────────────
source=text   ──► transcript (raw)
source=voice  ──► gemini_audio.transcribe_with_tone()  → transcript + detected_tone
source=preset ──► preset topic + reddit.fetch_trending(niche) → context injected

        Gemini 2.5 Pro — Agent Loop (gemini_agent.py, MAX_TURNS=14)
        ─────────────────────────────────────────────────────────────
        Turn 1: search_trending_hooks  → gemini_reasoning.research_hooks
        Turn 2: analyze_brand_voice    → _STYLE_RULES dict
        Turn 3: optimize_for_platform  → _PLATFORM_GUIDELINES dict
        Turn 4: validate_script_quality → gemini_reasoning.score_script
        Turn 5: finalize_script  ← exits (quality_score ≥ 70 required)
        Each turn: call_with_retry() — 3 retries, 2s→4s→8s backoff

ScriptGenerationResponse
  ├── hook: { text, duration }
  ├── scenes[]: { scene_id, duration_seconds=5, visual_prompt, voiceover_text, emotion }
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
  Stage 1 — TTS  (gemini_tts.py)
    gemini-2.5-flash-preview-tts  →  WAV (24kHz, 16-bit mono)
      │
  Stage 2 — Image Generation  (gemini_image.py)
    gemini-3.1-flash-image-preview  →  576×1024 PNG per scene
    Scene 1: prompt + style_suffix → PNG_1
    Scene 2: edit_prompt + PNG_1   → PNG_2  (character continuity)
    Scene N: edit_prompt + PNG_1 (char ref) + PNG_prev → PNG_N
      │
  Stage 3 — Animate  (ffmpeg.py)
    PNG → 5s MP4 via zoompan Ken Burns (dolly_in→crane_down→zoom_in_right…)
      │
  Stage 4 — Captions  (captions.py)
    voiceover_full_script → word-level SRT
    Styles: beast / bold_stroke / karaoke / majestic / red_highlight / sleek / elegant
      │
  Stage 5 — Composition  (ffmpeg.py)
    Pass 1: concat clips → concat.mp4
    Pass 2: mix voiceover → with_audio.mp4  ← PRESERVED in GCS for recompose
    Pass 3: burn captions → composed.mp4
    Pass 4: mix music (vol=0.15) → composed_music.mp4
    Music presets: breathing_shadows / quiet_before_storm / brilliant_symphony /
                   happy_rhythm / peaceful_vibes
      │
  Stage 6 — Export + Upload  (ffmpeg.py + gcs.py)
    youtube_shorts  1080×1920, 10Mbps, 30fps
    instagram_reels 1080×1920, 8Mbps,  30fps
    tiktok          1080×1920, 8Mbps,  30fps
    GCS configured  → gs://voicevid-assets/projects/{id}/{platform}/final.mp4
    GCS fallback    → backend/outputs/projects/{id}/{platform}/final.mp4

  Metadata saved to Firestore collection: projects/{project_id}
  Includes: voiceover_full_script, caption_style, background_music, video_duration
  (required by Phase 4 recompose)
```

---

## Phase 3 — Creative Director (Interleaved Multimodal)

```
POST /api/v1/creative-director/generate          ← blocking, full response
POST /api/v1/creative-director/generate-stream   ← SSE streaming, one block/event
      │
      ▼
CreativeDirectorRequest
  ├── brief:              Creative brief (topic, audience, goals, tone)
  ├── mode:               storybook | marketing | educational | social_content
  ├── art_style:          Optional art style applied to all images
  ├── include_narration:  bool (default False) — generate TTS WAV of all text blocks
  └── voice_id:           str (default "Aoede") — Gemini TTS voice

      │
      ▼
services/gemini_interleaved.py
  Model: gemini-2.0-flash-preview-image-generation
  Config: response_modalities=["TEXT", "IMAGE"]  ← interleaved output key

  Single Gemini call → alternating text + image parts in one response stream:
    part.text        → {"type": "text",  "content": "..."}
    part.inline_data → {"type": "image", "content": "<base64>", "mime_type": "image/png"}

  generate_creative_package() returns: (blocks: list[dict], narration_b64: str | None)

  Mode prompts
  ────────────
  storybook        Story paragraphs alternating with scene illustrations (4-6 scenes)
  marketing        Headline → hero image → body copy → lifestyle image → CTA → hashtags
  educational      Concept explanation → diagram image → key takeaway (×3-4 concepts)
  social_content   Hook → post image → caption → carousel image → hashtags → A/B variants

  SSE streaming (/generate-stream)
  ─────────────────────────────────
  Blocks streamed one-by-one after Gemini call completes (progressive reveal effect)
  Each event: data: {"type":"text"|"image", "content":"..."}
  Final event: data: {"type":"done","package_id":"...","total_images":N,...}
  Error event: data: {"type":"error","content":"..."}

      │
      ▼
CreativePackageResponse
  ├── package_id
  ├── mode
  ├── brief
  ├── blocks[]:            list[InterleavedBlock]  (ordered, interleaved text + images)
  ├── total_images
  ├── total_text_blocks
  └── narration_audio_b64: Optional[str]  (base64 WAV, only when include_narration=true)
```

---

## Phase 4 — Recompose (Edit Caption Style & Background Music)

```
POST /api/v1/projects/{project_id}/recompose
      │
      ▼
RecomposeRequest
  ├── caption_style:    CaptionStyleEnum
  ├── background_music: MusicPreset
  ├── target_platforms: Optional[list[Platform]]  (defaults to original platforms)
  └── music_volume:     float (default 0.15)

Guard conditions (returns HTTP error if not met):
  404 — project not found in Firestore
  409 — project status ≠ "completed"
  422 — voiceover_full_script missing (pre-dates recompose support; re-run generate-video)

      │
      ▼
services/recompose.py — 5-stage pipeline (NO Gemini calls, NO TTS, NO image gen)
  Stage 1: download_source  — fetch with_audio.mp4 from GCS
                              (projects/{id}/master/with_audio.mp4)
  Stage 2: captions         — regenerate SRT from voiceover_full_script (pure Python)
  Stage 3: burn_captions    — FFmpeg subtitle burn with new style
  Stage 4: background_music — FFmpeg audio mix with new music preset (skipped if "none")
  Stage 5: export_upload    — platform resize + upload to GCS, overwrite existing finals

  Overwrites: projects/{id}/master/composed.mp4
              projects/{id}/{platform}/final.mp4 (per platform)
  Updates Firestore metadata: caption_style, background_music, video_urls, recomposed_at
```

---

## Key Models

| Service | Model | Purpose |
|---------|-------|---------|
| gemini_agent.py | `gemini-2.5-pro` | Script director ReAct agent |
| gemini_reasoning.py | `gemini-2.5-pro` | Hook research + script scoring |
| gemini_tts.py | `gemini-2.5-flash-preview-tts` | Voiceover synthesis |
| gemini_image.py | `gemini-3.1-flash-image-preview` | Scene image generation |
| gemini_audio.py | Gemini multimodal | Audio transcription + tone |
| gemini_interleaved.py | `gemini-2.0-flash-preview-image-generation` | Interleaved text+image |
| gemini_client.py | — | Dual-path client factory: Vertex AI on GCP, API key locally |

---

## Configuration (.env)

```
GEMINI_API_KEY          ──► Preview model calls (image gen, TTS, interleaved, audio)
GOOGLE_CLOUD_PROJECT    ──► GCS + Firestore + Vertex AI project ID
GCS_BUCKET              ──► Bucket name (default: voicevid-assets)
USE_VERTEX_AI           ──► true on Cloud Run → uses Vertex AI for 2.5 Pro models
VERTEX_AI_LOCATION      ──► Region for Vertex AI (default: us-central1)
YOUTUBE_CLIENT_SECRETS_FILE  ──► YouTube OAuth
```

See `backend/.env.example` for template. Never commit `backend/.env`.

## Deployment

```bash
# One-command deploy to Cloud Run
./deploy.sh

# Or with overrides:
REGION=us-east1 GOOGLE_CLOUD_PROJECT=my-proj ./deploy.sh
```

Key files:
- `deploy.sh` — orchestrates Cloud Build + Cloud Run deploy
- `backend/cloudbuild.yaml` — Cloud Build pipeline (Docker → Artifact Registry → Cloud Run)
- `backend/cloudrun_service.yaml` — declarative Cloud Run IaC definition
- API key stored in Secret Manager as `gemini-api-key:latest`

## GCP Services Used

| Service | Purpose |
|---------|---------|
| Cloud Run | Hosts FastAPI backend |
| Cloud Build | CI/CD pipeline (build + deploy) |
| Artifact Registry | Docker image registry |
| Cloud Storage (GCS) | Video files, audio, images |
| Cloud Firestore | Project metadata (collection: `projects`) |
| Secret Manager | GEMINI_API_KEY at rest |
| Vertex AI | Gemini 2.5 Pro inference on GCP |

## Service Dependency Map

```
main.py
  ├── routers/script.py
  │     ├── services/gemini_agent.py
  │     │     ├── services/gemini_client.py   ← shared auth factory
  │     │     ├── services/gemini_reasoning.py
  │     │     │     └── services/gemini_client.py
  │     │     └── services/retry.py
  │     ├── services/gemini_audio.py
  │     │     └── services/gemini_client.py   (force_api_key=True)
  │     ├── services/reddit.py
  │     └── services/gcs.py
  ├── routers/video.py
  │     ├── services/pipeline_runner.py
  │     │     ├── services/gemini_tts.py
  │     │     │     └── services/gemini_client.py   (force_api_key=True)
  │     │     ├── services/gemini_image.py
  │     │     │     └── services/gemini_client.py   (force_api_key=True)
  │     │     ├── services/ffmpeg.py
  │     │     ├── services/captions.py
  │     │     └── services/gcs.py
  │     └── services/firestore_db.py          ← metadata save
  ├── routers/projects.py
  │     ├── services/firestore_db.py          ← list / get / delete
  │     └── services/gcs.py                  (video stream + thumbnail)
  ├── routers/recompose.py
  │     ├── services/recompose.py
  │     │     ├── services/captions.py
  │     │     ├── services/ffmpeg.py
  │     │     └── services/gcs.py
  │     └── services/firestore_db.py          ← metadata load + save
  ├── routers/creative_director.py
  │     └── services/gemini_interleaved.py
  │           ├── services/gemini_client.py   (force_api_key=True)
  │           └── services/gemini_tts.py      (when include_narration=true)
  ├── routers/catalog.py
  ├── routers/auth.py
  └── routers/publish.py
        └── services/gcs.py
```
