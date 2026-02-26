# ContentFactory

Content Factory is an AI-powered content generation platform that transforms raw user inputs: text, voice memos, or selected themes into fully produced video content. The platform removes the bottleneck between idea and published content by automating scripting, narrative shaping, and video generation end-to-end.

---

## Tech Stack

| Layer             | Technology                                                             |
| ----------------- | ---------------------------------------------------------------------- |
| Framework         | FastAPI + Uvicorn                                                      |
| Language          | Python 3.12                                                            |
| Storage           | AWS S3, Databricks Delta Lake                                          |
| Script AI         | Claude (claude-sonnet-4-6) via Anthropic Agent SDK                     |
| Reasoning AI      | NVIDIA Nemotron nano-9b-v2                                             |
| Image AI          | Google Gemini 2.5 Flash Image                                          |
| Voice AI          | ElevenLabs (Scribe v2 STT + TTS)                                       |
| Video Composition | FFmpeg                                                                 |
| Analytics         | Databricks Delta Lake + MLflow                                         |
| Publishing        | YouTube Data API v3, Meta Graph API v22, TikTok Content Posting API v2 |

---

## Architecture Diagram

<p align="center">
  <img src="image.png" alt="ContentFactory Architecture Diagram — full pipeline from user input through transcription, Nemotron auto-config, Claude script generation, Gemini image chain-editing, FFmpeg composition, and social publishing" width="600"/>
</p>

## Pipeline Execution Flow

Content Factory supports three input paths, but they all converge into the same backend pipeline that produces a structured script first, then a final 9:16 video.

### 1. Input Paths

- **Option A: Manual**
  The user selects all settings explicitly (voice, music, art style, captions, effects, duration).

- **Option B: Voice Idea**
  The user uploads or records audio. ElevenLabs Scribe v2 transcribes it to text and extracts tone signals that are passed into script generation.

- **Option C: Preset**
  The user chooses a preset theme. The system gathers niche signal and can auto-fill any missing creative settings before generating the script.

### 2. Configuration and Research

Once the user clicks **Generate Script**, the backend runs a configuration stage:

- **Reddit research** pulls niche signal by fetching hot and controversial posts for the selected theme.
- **Databricks Delta Lake** is queried to enrich topics and pull historical patterns from prior runs.
- **Nemotron** runs `auto_configure_series` to fill any settings not provided by the user (series name, default art, music, voice).
- The resolved configuration is stored in **S3** as a versioned JSON blob and returned to the client.

### 3. Script Generation and Quality Gate

After configuration, script generation is executed as a bounded agent loop:

- **Claude Agent SDK** starts an agent loop with a max turn limit.
- The agent attempts **Nemotron research hooks**; if unavailable, it falls back to a curated hook library.
- The agent iterates through tool calls to:
  - analyze brand voice
  - optimize for the target platform format
  - validate script quality and structure

- **Nemotron** scores the resulting script as a quality gate.
- The agent finalizes and returns a structured script (hook, scenes, narration, visual prompts, CTA).

If the user is not satisfied, they can regenerate the script, which reruns the agent loop while keeping the same configuration.

### 4. Video Generation

When the user clicks **Generate Video**, the pipeline moves from script to media:

- **Gemini 2.5 Flash Image** generates images per scene in vertical 9:16 format.
- Captions are generated as **SRT** from word-level timestamps and styled using the selected caption preset.
- **FFmpeg** composes the final video by animating images, mixing voice and music, and burning captions into the frames.

### 5. Publish

After review, users can connect social accounts and publish:

- **YouTube Data API v3** for YouTube Shorts
- **Meta Graph API v22** for Instagram Reels
- **TikTok Content Posting API v2** for TikTok uploads

### 6. Logging and Analytics

Every pipeline run writes status and metadata to Databricks `voicevid_projects`, and MLflow captures parameters, metrics, and artifact links for experiment tracking and debugging

## Analytics & Observability

- **Databricks Delta Lake** — Every pipeline run is written (ACID) to the `voicevid_projects` table via `services/delta.py`. Columns include: project_id, status, niche, art_style, quality_score, platforms, configured_by (manual vs Nemotron).
- **MLflow** — All runs are also logged locally to `backend/mlflow.db` (SQLite) with parameters, metrics, and artifact links.
- **Databricks Genie** — The `/api/v1/analytics/ask` endpoint proxies natural language questions to the Genie AI/BI space for ad-hoc analytics.
