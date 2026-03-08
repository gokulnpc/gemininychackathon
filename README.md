# Story Factory

**Turn any idea into a publish-ready short-form video — in minutes.**

Story Factory is an AI-powered content creation platform that transforms raw input (voice recording, text, or a trending preset topic) into a fully produced vertical video: voiceover, scene-by-scene images, animated Ken Burns motion, captions, background music, and multi-platform export — all in a single pipeline.

---

## Features & Functionality

### 1. Script Generation (AI Director)
A **Gemini 2.5 Pro ReAct agent** runs a multi-turn reasoning loop to produce a structured script from any input:

| Input mode | What happens |
|------------|--------------|
| **Speech** | Mic audio → Gemini transcribes + detects tone → feeds script agent |
| **Text** | Free-form text or PDF (OCR via Gemini) → script agent |
| **Preset** | Niche topic → Reddit trending hooks injected → script agent |

The agent loop (up to 14 turns) calls internal tools — `search_trending_hooks`, `analyze_brand_voice`, `optimize_for_platform`, `validate_script_quality` — before finalising a script with a quality score ≥ 70. Output includes scenes, voiceover, CTA, and social copy for TikTok / Instagram / YouTube.

### 2. Video Generation (5-Stage Pipeline)
Once a script is approved, a background worker (Cloud Tasks) runs:

```
TTS → Image Gen → Animate → Captions → Compose + Export
```

| Stage | Technology |
|-------|-----------|
| **Voiceover (TTS)** | Gemini 2.5 Flash Preview TTS — raw PCM16 → WAV |
| **Scene Images** | Gemini Image 3.1 Flash — 576×1024 per scene, character consistency via image-to-image chaining |
| **Animation** | FFmpeg `zoompan` Ken Burns filter (dolly, crane, zoom variants) |
| **Captions** | Word-level SRT, 7 style presets (Beast, Karaoke, Majestic, etc.) |
| **Composition** | FFmpeg: concat → mix audio → burn captions → mix music |
| **Export** | YouTube Shorts, Instagram Reels, TikTok (1080×1920, platform bitrates) |

### 3. Creative Director (Interleaved Multimodal)
A separate mode uses `gemini-2.0-flash-preview-image-generation` to stream interleaved text + image blocks in a single API call — producing storybooks, marketing packages, educational content, or social bundles. Supports optional TTS narration of the full package.

### 4. Recompose (Non-destructive Edit)
Change caption style or background music on a completed video **without re-running TTS or image generation**. The pipeline downloads the preserved `with_audio.mp4` from GCS, re-burns captions, re-mixes music, and re-uploads.

### 5. Publish
Direct YouTube upload via OAuth2 from the app. Instagram / TikTok manual download with formatted captions.

### 6. Dashboard & Project Management
Full project history with per-platform video playback, thumbnail preview, status tracking, and delete.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser (Next.js 15)                         │
│  Step wizard → script review → video player → publish modal         │
└────────────────────────────┬────────────────────────────────────────┘
                             │  REST + WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               voicevid-api  (Cloud Run, 512 MB, ×10)                │
│                         FastAPI + Uvicorn                           │
│                                                                     │
│  /api/v1/projects/{id}/generate-script  ──► Script Agent            │
│  /api/v1/projects/{id}/generate-video   ──► Cloud Tasks enqueue     │
│  /api/v1/projects/{id}/recompose        ──► Recompose service       │
│  /api/v1/creative-director/generate     ──► Interleaved multimodal  │
│  /api/v1/transcribe                     ──► Gemini audio            │
│  /api/v1/ocr-pdf                        ──► Gemini PDF OCR          │
│  /api/v1/auth/youtube                   ──► YouTube OAuth           │
│  /api/v1/projects/{id}/live-voice  (WS) ──► Gemini Live             │
└─────────────┬──────────────────────────┬───────────────────────────┘
              │ Cloud Tasks              │ Firestore + GCS
              ▼                          ▼
┌─────────────────────────┐   ┌──────────────────────────────────────┐
│  voicevid-worker        │   │         Google Cloud Services        │
│  (Cloud Run, 4 GB, ×5)  │   │                                      │
│                         │   │  Cloud Firestore — project metadata  │
│  TTS (Gemini Flash TTS) │   │  Cloud Storage  — video / audio /    │
│  Image Gen (Gemini 3.1) │   │                  image assets        │
│  FFmpeg animate         │   │  Secret Manager — API keys / OAuth   │
│  Caption burn           │   │  Artifact Registry — Docker images   │
│  Music mix              │   │  Cloud Build    — CI/CD pipeline     │
│  Platform export        │   │  Cloud Tasks    — async job queue    │
└─────────────────────────┘   └──────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Gemini API (via Vertex AI)                   │
│                                                                     │
│  gemini-2.5-pro          — Script ReAct agent + scoring             │
│  gemini-2.5-flash-tts    — Voiceover synthesis                      │
│  gemini-3.1-flash-image  — Scene image generation                   │
│  gemini-2.0-flash        — Interleaved text+image (Creative Dir.)   │
│  gemini-2.0-flash-live   — Real-time audio transcription            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Technologies Used

### Backend
| Technology | Role |
|-----------|------|
| **Python 3.12 + FastAPI** | API server, WebSocket endpoints |
| **Google Gemini (`google-genai` SDK)** | All AI — script, images, TTS, OCR, transcription |
| **Vertex AI** | Production inference for Gemini 2.5 Pro (stable models) |
| **FFmpeg** | Video processing — Ken Burns animation, caption burn, audio mix, platform export |
| **Google Cloud Run** | Serverless container hosting (API + Worker) |
| **Google Cloud Tasks** | Async job queue for long-running video pipeline |
| **Google Cloud Firestore** | Project metadata storage |
| **Google Cloud Storage** | Video, audio, and image asset storage |
| **Google Secret Manager** | API key and OAuth credential management |
| **Google Cloud Build + Artifact Registry** | Docker CI/CD pipeline |
| **SendGrid** | Email notifications on video completion |
| **Pillow** | Image manipulation |

### Frontend
| Technology | Role |
|-----------|------|
| **Next.js 15 (App Router)** | React framework |
| **Tailwind CSS v4** | Styling |
| **Framer Motion** | Animations |
| **Radix UI** | Accessible component primitives |
| **Web Audio API** | Raw PCM16 mic capture for live transcription |

### External Data Sources
- **Reddit API** — trending hooks and post content for preset-based scripts (niche-specific trending context)
- **YouTube Data API v3** — OAuth upload and channel management

---

## Google Cloud Deployment

The backend runs as two Cloud Run services in `us-central1`:

| Service | URL | Purpose |
|---------|-----|---------|
| `voicevid-api` | https://voicevid-api-arkk5ohwka-uc.a.run.app | Public API + WebSocket endpoints |
| `voicevid-worker` | https://voicevid-worker-arkk5ohwka-uc.a.run.app | Internal video pipeline worker |

**Health check:** https://voicevid-api-arkk5ohwka-uc.a.run.app/health
**API docs:** https://voicevid-api-arkk5ohwka-uc.a.run.app/docs

**GCP services in use:**
- Cloud Run (API + Worker services)
- Cloud Build (Docker image → Artifact Registry)
- Cloud Tasks (`video-generation` queue, `us-central1`)
- Cloud Firestore (project metadata)
- Cloud Storage (`storylab-assets` bucket)
- Secret Manager (`gemini-api-key`, `sendgrid-api-key`, `youtube-client-secrets`)
- Vertex AI (Gemini 2.5 Pro inference)

**Deployment is fully scripted** — see [`deploy.sh`](deploy.sh):
```bash
./deploy.sh   # builds image via Cloud Build, deploys both Cloud Run services
```

**Proof of deployment** — Cloud Run service logs:
```bash
gcloud run services logs read voicevid-api --region=us-central1 --project=story-labs-factory
gcloud run services logs read voicevid-worker --region=us-central1 --project=story-labs-factory
```

GCS usage: [`backend/services/gcs.py`](backend/services/gcs.py)
Vertex AI inference: [`backend/services/gemini_client.py`](backend/services/gemini_client.py)
Cloud Tasks dispatch: [`backend/services/pipeline_runner.py`](backend/services/pipeline_runner.py)

---

## Findings & Learnings

### Gemini Model Routing
The Gemini SDK (`google-genai ≥ 1.0`) silently switches to Vertex AI when `GOOGLE_CLOUD_PROJECT` is set in the environment — even if you pass an explicit `api_key`. The fix: always pass `vertexai=False` explicitly for API-key-based clients. This was critical for image generation, which uses a preview model only available via API key.

### Two-Service Architecture for Video
Video generation (TTS + 8 images + FFmpeg) takes 3–8 minutes per project. Keeping a lightweight public API service (512 MB, 60s timeout) separate from a beefy worker (4 GB, 15-min timeout) allows the API to stay responsive while the worker handles the heavy lifting via Cloud Tasks.

### Character Consistency in Image Generation
Scene image chaining (passing the previous scene's image as a reference alongside the character reference from scene 1) significantly improves visual consistency across scenes without any fine-tuning or LoRA — pure prompting + image context.

### Interleaved Multimodal
`gemini-2.0-flash-preview-image-generation` with `response_modalities=["TEXT", "IMAGE"]` returns a single stream of alternating text and image parts. This enables the Creative Director feature to produce a fully coherent package (story + illustrations) in one API call rather than orchestrating separate text and image requests.

### Secret Manager for OAuth Files
YouTube OAuth requires a `client_secrets.json` file path — not just an env var string. Mounting it as a Secret Manager volume (`--set-secrets=/secrets/file.json=secret-name:latest`) on Cloud Run makes it available as a real file at a known path without baking credentials into the Docker image.
