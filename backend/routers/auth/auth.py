"""Social media authentication endpoints.

Endpoints:
  GET  /api/v1/auth/status             — which platforms are configured
  GET  /api/v1/auth/youtube            — start YouTube OAuth2, returns auth URL
  GET  /api/v1/auth/youtube/callback   — Google redirects here; saves token
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CALLBACK_PATH = "/api/v1/auth/youtube/callback"

# In-memory store for pending OAuth2 flows (state → Flow object)
_pending_flows: dict = {}


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def auth_status():
    """Return which platforms are configured and ready to publish."""
    settings = get_settings()
    youtube_ok = False
    if settings.youtube_token_file and Path(settings.youtube_token_file).exists():
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(
                settings.youtube_token_file, YOUTUBE_SCOPES
            )
            youtube_ok = creds.valid or bool(creds.refresh_token)
        except Exception:
            pass

    return {
        "youtube": youtube_ok,
        "instagram": bool(settings.instagram_access_token and settings.instagram_user_id),
        "tiktok": bool(settings.tiktok_access_token),
    }


# ── YouTube OAuth2 ────────────────────────────────────────────────────────────


@router.get("/youtube")
async def youtube_auth_init(redirect_uri: str | None = None):
    """Start the YouTube OAuth2 flow.

    Returns a Google authorization URL. The frontend should redirect the user
    to this URL. After granting permission, Google redirects to the callback.

    Args:
        redirect_uri: Override the callback URL (default: http://localhost:8000/api/v1/auth/youtube/callback).
    """
    settings = get_settings()

    if not settings.youtube_client_secrets_file:
        raise HTTPException(
            status_code=400,
            detail="YOUTUBE_CLIENT_SECRETS_FILE is not set in .env",
        )
    if not Path(settings.youtube_client_secrets_file).exists():
        raise HTTPException(
            status_code=400,
            detail=f"client_secrets.json not found at: {settings.youtube_client_secrets_file}",
        )

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib",
        )

    callback_uri = redirect_uri or f"http://localhost:8000{YOUTUBE_CALLBACK_PATH}"

    flow = Flow.from_client_secrets_file(
        settings.youtube_client_secrets_file,
        scopes=YOUTUBE_SCOPES,
        redirect_uri=callback_uri,
    )
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")

    _pending_flows[state] = flow
    logger.info("YouTube OAuth2 flow started, state=%s", state)

    return {"auth_url": auth_url, "state": state}


@router.get("/youtube/callback", response_class=HTMLResponse)
async def youtube_auth_callback(code: str, state: str):
    """Handle the Google OAuth2 redirect after the user grants permission.

    Exchanges the authorization code for credentials and saves them to disk.
    Returns an HTML confirmation page — this endpoint is opened in a browser tab.
    """
    flow = _pending_flows.pop(state, None)
    if not flow:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth2 state. Restart the auth flow.",
        )

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.exception("YouTube token exchange failed")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    settings = get_settings()
    token_path = Path(settings.youtube_token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(flow.credentials.to_json())
    logger.info("YouTube token saved to %s", token_path)

    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head><title>VoiceVid — YouTube Auth</title>
<style>
  body { font-family: system-ui, sans-serif; display: flex; justify-content: center;
         align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
  .card { background: white; border-radius: 12px; padding: 48px; text-align: center;
          box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 400px; }
  h2 { color: #1a1a1a; margin-bottom: 8px; }
  p  { color: #666; margin-bottom: 0; }
  .check { font-size: 56px; margin-bottom: 16px; }
</style>
</head>
<body>
  <div class="card">
    <div class="check">✅</div>
    <h2>YouTube Connected</h2>
    <p>VoiceVid can now publish videos to your YouTube channel.<br>
       You can close this tab.</p>
  </div>
</body>
</html>
""")
