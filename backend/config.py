from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Google Cloud Storage
    gcs_bucket: str = "storylab-assets"     # GCS bucket name

    # Social publishing — YouTube (OAuth2)
    youtube_client_secrets_file: str = ""
    youtube_token_file: str = "/tmp/voicevid_youtube_token.json"

    # Social publishing — Instagram (Meta Graph API)
    instagram_access_token: str = ""
    instagram_user_id: str = ""

    # Social publishing — TikTok (Content Posting API v2)
    tiktok_access_token: str = ""

    # Google Gemini (script agent + reasoning + image generation)
    gemini_api_key: str = ""
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_fast_text_model: str = "gemini-2.5-flash"
    gemini_reasoning_model: str = "gemini-2.5-pro"
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_premium_tts_model: str = "gemini-2.5-pro-preview-tts"

    # Google Cloud / Vertex AI
    google_cloud_project: str = ""          # GCP project ID, e.g. my-project-123
    vertex_ai_location: str = "us-central1" # region for Vertex AI
    use_vertex_ai: bool = False             # set True on Cloud Run (USE_VERTEX_AI=true)

    # Async job queue — Cloud Tasks
    cloud_tasks_queue: str = "video-generation"
    cloud_tasks_location: str = "us-central1"
    # URL of the worker Cloud Run service (set via WORKER_URL env var on Cloud Run)
    # Locally: leave empty to fall back to synchronous in-process execution
    worker_url: str = ""
    # Optional dedicated Node timeline render worker for editor exports.
    # Locally: leave empty to fall back to the bundled CLI renderer.
    timeline_render_worker_url: str = ""
    # Public origins used to normalize canonical timeline media for server-side rendering.
    frontend_public_base_url: str = "http://localhost:3000"
    api_public_base_url: str = "http://localhost:8000"

    # Email notifications — SendGrid
    sendgrid_api_key: str = ""
    notification_from_email: str = "noreply@voicevid.app"

    # Google Document AI (optional — leave empty to use Gemini for PDF OCR)
    document_ai_processor_id: str = ""      # Processor ID from GCP Console
    document_ai_location: str = "us"        # "us" or "eu"

    # App
    app_name: str = "StoryLabs"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
