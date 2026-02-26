from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Google Cloud Storage
    gcs_bucket: str = "voicevid-assets"     # GCS bucket name

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

    # Google Cloud / Vertex AI (Veo 3 video generation)
    google_cloud_project: str = ""          # GCP project ID, e.g. my-project-123
    vertex_ai_location: str = "us-central1" # region for Veo 3

    # App
    app_name: str = "VoiceVid"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
