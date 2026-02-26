from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # Bedrock model IDs (Nova Canvas for image generation)
    nova_canvas_model_id: str = "amazon.nova-canvas-v1:0"

    # S3
    s3_bucket: str = "voicevid-assets"

    # Social publishing — YouTube (OAuth2)
    youtube_client_secrets_file: str = ""   # path to client_secrets.json from Google Cloud Console
    youtube_token_file: str = "/tmp/voicevid_youtube_token.json"  # saved after first OAuth2 login

    # Social publishing — Instagram (Meta Graph API)
    instagram_access_token: str = ""        # long-lived page/user access token
    instagram_user_id: str = ""             # Instagram Business Account ID

    # Social publishing — TikTok (Content Posting API v2)
    tiktok_access_token: str = ""           # TikTok app access token

    # ElevenLabs
    elevenlabs_api_key: str = ""

    # Anthropic (Claude Agent SDK)
    anthropic_api_key: str = ""

    # NVIDIA (Nemotron content intelligence agent)
    nvidia_api_key: str = ""

    # Google Gemini (script agent + reasoning + image generation)
    gemini_api_key: str = ""

    # Google Cloud / Vertex AI (Veo 3 video generation)
    google_cloud_project: str = ""          # GCP project ID, e.g. my-project-123
    vertex_ai_location: str = "us-central1" # region for Veo 3

    # Databricks (MLflow tracking + Delta Lake)
    databricks_host: str = ""           # e.g. https://dbc-XXXX.cloud.databricks.com
    databricks_token: str = ""          # personal access token from Databricks
    mlflow_experiment_name: str = "VoiceVid Pipeline"
    databricks_sql_http_path: str = ""  # SQL Warehouse HTTP path, e.g. /sql/1.0/warehouses/abc123
    databricks_genie_space_id: str = "" # Genie Space ID for natural language queries (AI/BI → Genie)

    # App
    app_name: str = "VoiceVid"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
