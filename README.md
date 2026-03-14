# Story Factory — Gemini Live Agent Challenge Submission

**Turn any idea into a publish-ready short-form video — guided by a live AI that sees, hears, and edits alongside you.**

Story Factory is a multimodal AI video creation and editing platform powered by Gemini Live API. It transforms raw input (voice, text, or a trending preset topic) into a fully produced vertical video — voiceover, scene images, animated motion, captions, music, and multi-platform export — while an interactive voice agent (Scout) can edit the result in real-time, see your screen, and respond naturally to interruptions.

---

## Hackathon Tracks Addressed

| Track | How Story Factory covers it |
|-------|-----------------------------|
| **Live Agents (Primary)** | Scout — a Gemini Live voice agent that edits videos through natural conversation, handles interruptions, and maintains session state across tool calls |
| **Creative Storyteller** | Creative Director mode uses `gemini-2.0-flash-preview-image-generation` to stream interleaved text + image blocks in one API call — storyboards, marketing packages, illustrated scripts |
| **UI Navigator** | Screen Sharing Agent — Scout captures the user's screen at 1 FPS, streams frames into the Live session, and references the visual editor state when making or explaining edits |

**Mandatory tech:** Gemini Live API · Google GenAI SDK · Google Cloud (Cloud Run, Cloud Tasks, Firestore, GCS, Vertex AI)

---

## What We Built

A real-time AI-assisted short-form video editor with three layers:

1. **Generate** — voice/text/preset → full video in one automated 7-stage pipeline (TTS, images, animation, captions, music, export)
2. **Edit** — talk to Scout (the live voice agent) to refine the result; Scout sees your screen and applies targeted edits without re-rendering from scratch
3. **Publish** — direct upload to YouTube Shorts, Instagram Reels, or TikTok

---

## Features & Functionality

### 1. Scout — Live Voice Edit Agent *(Live Agents track)*

Scout is a Gemini Live-powered conversational agent that:

- Listens continuously via WebSocket (16 kHz PCM16 audio), responding with low-latency voice output (24 kHz)
- Supports **natural interruptions** — Voice Activity Detection (VAD) lets the user cut Scout off mid-sentence and redirect
- Has **20+ edit tools**: music changes, caption style updates, text overlay insertion/deletion, element trimming/repositioning, volume control, and AI music generation via Lyria
- Maintains **stateful session context** — Scout tracks the current project, selected elements, and timeline position across turns
- Streams tool results back as both voice and structured JSON events, so the UI updates live while Scout narrates the change

**Route:** `WS /api/v1/projects/{id}/edit-voice`
**Key files:** [`backend/routers/voice/edit.py`](backend/routers/voice/edit.py) · [`backend/services/gemini/editing/voice_runtime.py`](backend/services/gemini/editing/voice_runtime.py)

---

### 2. Screen Sharing Agent *(UI Navigator track)*

When the user clicks "Share Screen", Scout gains visual awareness:

- Browser captures the screen via `getDisplayMedia()`, encodes each frame as JPEG (80% quality), and sends it as base64 JSON over the same WebSocket at 1 FPS
- Scout receives frames inline in the Gemini Live context window — it can reference what it sees ("I can see your title card is overlapping the subject's face")
- Screenshot also auto-triggers on "inspect" keywords (`analyze`, `what's wrong`, `feedback`, etc.)
- No DOM access required — Scout interprets the editor's visual state purely from pixel data

**Key files:** [`frontend-sky/hooks/use-voice-edit-session.ts`](frontend-sky/hooks/use-voice-edit-session.ts) · [`backend/services/gemini/editing/voice_runtime.py`](backend/services/gemini/editing/voice_runtime.py)

---

### 3. Script Generation (AI Director)

A **Gemini 2.5 Pro ReAct agent** runs a multi-turn reasoning loop (up to 14 turns) to produce a structured script from any input:

| Input mode | What happens |
|------------|--------------|
| **Speech** | Mic audio → Gemini transcribes + detects tone → feeds script agent |
| **Text** | Free-form text or PDF (OCR via Gemini) → script agent |
| **Preset** | Niche topic → Reddit trending hooks injected → script agent |

Internal tools: `search_trending_hooks`, `analyze_brand_voice`, `optimize_for_platform`, `validate_script_quality`. Output: scenes, voiceover text, CTA, and social copy for TikTok / Instagram / YouTube.

**Route:** `POST /api/v1/projects/{id}/generate-script`

---

### 4. 7-Stage Video Pipeline

Once a script is approved, a background worker (Cloud Tasks) runs:

```
Stage 1.5  Reference subject inference  (optional — from uploaded photo)
Stage 2    Script generation            Gemini 2.5 Pro ReAct agent
Stage 3    Voiceover (TTS)             Gemini 2.5 Flash TTS → WAV + word timestamps
Stage 4    Scene images                Gemini Image 3.1 Flash — 576×1024 per scene
Stage 4c   Visual QA                   Reject low-quality images, regenerate
Stage 4b   Thumbnail                   Separate thumbnail image
Stage 5    Captions                    Word-level SRT from TTS timestamps
Stage 6    Composition                 FFmpeg: concat + Ken Burns + caption burn + music
Stage 7    Export                      Platform resize + GCS upload
         + Timeline                    Twick-compatible JSON timeline
```

| Stage | Technology |
|-------|-----------|
| **Voiceover** | Gemini 2.5 Flash Preview TTS — raw PCM16 → WAV |
| **Scene Images** | Gemini Image 3.1 Flash — character consistency via image-to-image chaining |
| **Animation** | FFmpeg `zoompan` Ken Burns filter (dolly, crane, zoom variants) |
| **Captions** | Word-level SRT, 8 style presets (Beast, Karaoke, Majestic, etc.) |
| **Composition** | FFmpeg: concat → mix audio → burn captions → mix music |
| **Export** | YouTube Shorts, Instagram Reels, TikTok (1080×1920, platform bitrates) |

**Routes:** `POST /api/v1/projects/{id}/generate-video` · `GET /api/v1/projects/{id}/status`

---

### 5. Creative Director — Interleaved Multimodal *(Creative Storyteller track)*

Uses `gemini-2.0-flash-preview-image-generation` with `response_modalities=["TEXT", "IMAGE"]` to stream a single interleaved output — alternating text narration and generated images in one coherent flow. Use cases: illustrated storybooks, marketing asset packages, educational explainers with inline diagrams.

**Route:** `POST /api/v1/creative-director/generate-stream`
**Key file:** [`backend/services/gemini/interleaved.py`](backend/services/gemini/interleaved.py)

---

### 6. Timeline Render Worker

A standalone Node.js service (Cloud Run) that renders a Twick JSON timeline into an MP4 using Puppeteer (headless Chromium) + `@twick/renderer` + FFmpeg:

```
POST /render  →  Twick ProjectJSON  →  Puppeteer + Twick visualizer  →  FFmpeg  →  MP4
```

This allows non-destructive editor exports: the user tweaks the Twick timeline in-browser, hits Export, and the worker renders the exact frame-for-frame timeline without touching the original TTS audio or scene images.

**Key files:** [`timeline-render-worker/server.mjs`](timeline-render-worker/server.mjs) · [`timeline-render-worker/render-timeline.mjs`](timeline-render-worker/render-timeline.mjs)

---

### 7. Recompose — Non-destructive Edit

Change caption style or background music on a completed video without re-running TTS or image generation. Downloads the preserved `with_audio.mp4` from GCS, re-burns captions, re-mixes music, re-uploads.

**Route:** `POST /api/v1/projects/{id}/recompose`

---

### 8. Publish

Direct YouTube upload via OAuth2. Instagram / TikTok manual download with formatted captions and hashtags.

**Route:** `POST /api/v1/projects/{id}/publish`

---

## Architecture

![Architecture Diagram](docs/architecture.svg)

---

## Technologies Used

### Backend
| Technology | Role |
|-----------|------|
| **Python 3.12 + FastAPI** | API server, WebSocket + SSE endpoints |
| **Google GenAI SDK (`google-genai`)** | All Gemini calls — script, images, TTS, OCR, transcription, Live API |
| **Vertex AI** | Production inference for stable Gemini models |
| **FFmpeg** | Ken Burns animation, caption burn, audio mix, platform export |
| **Cloud Run** | Serverless container hosting (API + Worker services) |
| **Cloud Tasks** | Async job queue for long-running video pipeline |
| **Cloud Firestore** | Project metadata storage |
| **Cloud Storage** | Video, audio, image, and asset storage |
| **Secret Manager** | API key and OAuth credential management |
| **Cloud Build + Artifact Registry** | Docker CI/CD pipeline |
| **Firebase Admin SDK** | User authentication verification |
| **SendGrid** | Email notifications on video completion |
| **Pillow** | Image manipulation |

### Timeline Render Worker
| Technology | Role |
|-----------|------|
| **Node.js** | Service runtime |
| **Puppeteer** | Headless Chromium for Twick renderer |
| **@twick/core + @twick/renderer** | Timeline-to-video rendering |
| **@twick/ffmpeg** | FFmpeg integration in Node context |

### Frontend
| Technology | Role |
|-----------|------|
| **Next.js 15 (App Router)** | React 19 framework |
| **Tailwind CSS v4** | Styling |
| **Framer Motion** | Animations |
| **Radix UI** | Accessible component primitives |
| **Web Audio API** | Raw PCM16 mic capture + VAD for live sessions |
| **MediaDevices API** | Screen capture (`getDisplayMedia`) |
| **Firebase Auth** | User authentication |

### External Data Sources
- **Reddit API** — trending hooks and post content for preset-based scripts
- **YouTube Data API v3** — OAuth upload and channel management
- **Lyria (Google)** — AI music generation for background tracks

---

## Spin-Up Instructions

### Prerequisites
- Python 3.12+, Node.js 20+, `pnpm`, `ffmpeg` installed locally
- Gemini API key (get one at [aistudio.google.com](https://aistudio.google.com))
- Firebase project (for Auth) and GCP project (for GCS, Firestore)

### Backend

```bash
cd backend
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env — minimum required:
#   GEMINI_API_KEY=...
#   GOOGLE_CLOUD_PROJECT=your-project-id
#   GCS_BUCKET=your-bucket
#   FIREBASE_PROJECT_ID=your-project-id
#   USE_VERTEX_AI=false
#   WORKER_URL=   # leave blank for local sync pipeline

uvicorn main:app --reload --port 8000
# API docs: http://localhost:8000/docs
# Health:   http://localhost:8000/health
```

### Frontend

```bash
cd frontend-sky
pnpm install

# Copy and fill in environment variables
cp .env.local.example .env.local
# Edit .env.local:
#   NEXT_PUBLIC_API_URL=http://localhost:8000
#   NEXT_PUBLIC_FIREBASE_API_KEY=...
#   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
#   NEXT_PUBLIC_FIREBASE_PROJECT_ID=...

pnpm dev
# App: http://localhost:3000
```

### Timeline Render Worker (optional — for editor exports)

```bash
cd timeline-render-worker
npm install
node server.mjs
# Render endpoint: http://localhost:4001/render
# Health check:    http://localhost:4001/health
```

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Gemini API key from AI Studio |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID |
| `GCS_BUCKET` | Yes | Cloud Storage bucket name |
| `FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `USE_VERTEX_AI` | No | `true` for Vertex AI, `false` for API key (default: false) |
| `WORKER_URL` | No | Internal URL of voicevid-worker (blank = sync local pipeline) |
| `SENDGRID_API_KEY` | No | Email notifications on video completion |
| `REDDIT_CLIENT_ID` | No | Reddit API — preset script trending hooks |
| `REDDIT_CLIENT_SECRET` | No | Reddit API secret |

---

## Google Cloud Deployment

The backend runs as two Cloud Run services in `us-central1`:

| Service | URL | Purpose |
|---------|-----|---------|
| `voicevid-api` | https://voicevid-api-arkk5ohwka-uc.a.run.app | Public API + WebSocket endpoints |
| `voicevid-worker` | Internal (Cloud Tasks only) | Video pipeline worker |

**Health check:** https://voicevid-api-arkk5ohwka-uc.a.run.app/health
**API docs:** https://voicevid-api-arkk5ohwka-uc.a.run.app/docs

**Deployment is fully scripted:**
```bash
./deploy.sh   # Cloud Build → Artifact Registry → Cloud Run (both services)
```

**Verify deployment:**
```bash
gcloud run services logs read voicevid-api --region=us-central1 --project=voicevid
gcloud run services logs read voicevid-worker --region=us-central1 --project=voicevid
```

**GCP services in use:**
- Cloud Run (voicevid-api + voicevid-worker)
- Cloud Build (Docker image → Artifact Registry → Cloud Run)
- Cloud Tasks (`video-generation` queue, us-central1, max 2 retries)
- Cloud Firestore (`projects` collection)
- Cloud Storage (`storylab-assets` bucket)
- Secret Manager (`gemini-api-key`, `sendgrid-api-key`, `youtube-client-secrets`)
- Vertex AI (Gemini 2.5 Pro stable inference)

**Key source references:**
- GCS integration: [`backend/services/storage/gcs.py`](backend/services/storage/gcs.py)
- Gemini client: [`backend/services/gemini/client.py`](backend/services/gemini/client.py)
- Cloud Tasks dispatch: [`backend/services/infra/task_queue.py`](backend/services/infra/task_queue.py)
- Deployment config: [`deploy.sh`](deploy.sh) · [`cloudbuild.yaml`](backend/cloudbuild.yaml)

---

## Findings & Learnings

### Gemini Model Routing (API Key vs Vertex AI)
The `google-genai` SDK silently switches to Vertex AI when `GOOGLE_CLOUD_PROJECT` is set — even when an explicit `api_key` is provided. Fix: always pass `vertexai=False` explicitly for API-key-based clients. This was critical for preview models (image generation, TTS preview) that are only available via API key, not Vertex AI.

### Two-Service Architecture for Video
Video generation (TTS + 8 images + FFmpeg) takes 3–8 minutes per project. Separating a lightweight public API (512 MB, 60s timeout) from a beefy worker (4 GB, 900s timeout) keeps the API responsive while Cloud Tasks queues the heavy lifting. Worker ingress is **internal only** — it is never publicly reachable.

### Character Consistency Without Fine-Tuning
Passing the previous scene's image alongside a character reference image (scene 1) as context for each new image generation significantly improves visual consistency across scenes — purely via image context, no LoRA or fine-tuning required.

### Interleaved Multimodal in a Single API Call
`gemini-2.0-flash-preview-image-generation` with `response_modalities=["TEXT", "IMAGE"]` returns a single stream of alternating text and image parts. This lets the Creative Director produce a fully coherent illustrated package (narration + images) in one API call rather than coordinating separate text and image requests.

### Secret Manager for OAuth Files
YouTube OAuth requires a `client_secrets.json` file path, not just an env var string. Mounting it as a Secret Manager volume (`--set-secrets=/secrets/file.json=secret-name:latest`) on Cloud Run makes it available as a real file at a known path without baking credentials into the Docker image.

### Screen Frame Streaming over WebSocket
Streaming screen frames at 1 FPS into a Gemini Live session requires careful framing: each frame is sent as a base64-encoded JSON message alongside the ongoing audio stream. The Live API accepts both modalities concurrently, allowing Scout to reference the visual editor state mid-conversation without pausing the audio turn.

### Voice Activity Detection for Natural Interruptions
Browser-side VAD (RMS threshold on captured PCM16 audio) lets the user cut Scout off mid-response without a push-to-talk button. When silence is detected after speech, the frontend marks the turn as complete and sends the audio chunk — keeping the conversation feel natural and interruptible without server-side VAD complexity.

### Twick + Puppeteer for Timeline Export
Rendering a Twick JSON timeline to MP4 server-side requires a real browser (Twick uses React + WebGL). Puppeteer in headless mode spins up a Chromium instance running the Twick visualizer, captures frames, and pipes them to FFmpeg — giving exact visual fidelity between what the user sees in the editor and the final export.
