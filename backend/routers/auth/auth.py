"""Social media authentication endpoints.

Endpoints:
  GET     /api/v1/auth/status             — current user's connected platforms
  GET     /api/v1/auth/youtube            — start user-scoped YouTube OAuth2
  GET     /api/v1/auth/youtube/callback   — Google redirects here; saves token
  DELETE  /api/v1/auth/youtube            — disconnect current user's YouTube account
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from config import get_settings
from deps.auth import get_current_user
from services.storage import youtube_auth_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CALLBACK_PATH = "/api/v1/auth/youtube/callback"
YOUTUBE_STATE_TTL = timedelta(minutes=30)


def _build_youtube_flow(redirect_uri: str, state: str | None = None):
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

    flow_kwargs = {
        "scopes": YOUTUBE_SCOPES,
        "redirect_uri": redirect_uri,
    }
    if state is not None:
        flow_kwargs["state"] = state

    return Flow.from_client_secrets_file(
        settings.youtube_client_secrets_file,
        **flow_kwargs,
    )


def _youtube_credentials_valid(credentials_json: str) -> bool:
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_info(
        json.loads(credentials_json),
        YOUTUBE_SCOPES,
    )
    return creds.valid or bool(creds.refresh_token)


def _fetch_youtube_channel_info(credentials) -> dict | None:
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=credentials)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        return None

    item = items[0]
    snippet = item.get("snippet", {})
    return {
        "channel_id": item.get("id"),
        "channel_title": snippet.get("title"),
    }


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def auth_status(current_user: dict = Depends(get_current_user)):
    """Return which platforms are configured and ready to publish."""
    youtube_ok = False
    try:
        credentials_json = await youtube_auth_store.get_youtube_credentials_json(current_user["uid"])
        if credentials_json:
            youtube_ok = _youtube_credentials_valid(credentials_json)
    except Exception:
        pass

    settings = get_settings()
    return {
        "youtube": youtube_ok,
        "instagram": bool(settings.instagram_access_token and settings.instagram_user_id),
        "tiktok": bool(settings.tiktok_access_token),
    }


# ── YouTube OAuth2 ────────────────────────────────────────────────────────────


@router.get("/youtube")
async def youtube_auth_init(
    redirect_uri: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Start the YouTube OAuth2 flow.

    Returns a Google authorization URL. The frontend should redirect the user
    to this URL. After granting permission, Google redirects to the callback.

    Args:
        redirect_uri: Override the callback URL (default: http://localhost:8000/api/v1/auth/youtube/callback).
    """
    callback_uri = redirect_uri or f"http://localhost:8000{YOUTUBE_CALLBACK_PATH}"
    flow = _build_youtube_flow(callback_uri)
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    await youtube_auth_store.create_pending_youtube_oauth_state(
        uid=current_user["uid"],
        state=state,
        redirect_uri=callback_uri,
        code_verifier=getattr(flow, "code_verifier", None),
    )
    logger.info("YouTube OAuth2 flow started for uid=%s, state=%s", current_user["uid"], state)

    return {"auth_url": auth_url, "state": state}


@router.get("/youtube/callback", response_class=HTMLResponse)
async def youtube_auth_callback(code: str, state: str):
    """Handle the Google OAuth2 redirect after the user grants permission.

    Exchanges the authorization code for credentials and saves them to disk.
    Returns an HTML confirmation page — this endpoint is opened in a browser tab.
    """
    pending = await youtube_auth_store.get_pending_youtube_oauth_state(state)
    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth2 state. Restart the auth flow.",
        )

    created_at = pending.get("created_at")
    try:
        created_at_dt = datetime.fromisoformat(created_at)
    except Exception:
        created_at_dt = None
    if created_at_dt is None or datetime.now(timezone.utc) - created_at_dt > YOUTUBE_STATE_TTL:
        await youtube_auth_store.delete_pending_youtube_oauth_state(state)
        raise HTTPException(
            status_code=400,
            detail="OAuth2 state expired. Restart the auth flow.",
        )

    flow = _build_youtube_flow(pending["redirect_uri"], state=state)
    code_verifier = pending.get("code_verifier")

    try:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    except Exception as exc:
        await youtube_auth_store.delete_pending_youtube_oauth_state(state)
        logger.exception("YouTube token exchange failed")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    channel_info = None
    try:
        channel_info = _fetch_youtube_channel_info(flow.credentials)
    except Exception:
        logger.warning("Failed to fetch YouTube channel metadata for state=%s", state, exc_info=True)

    await youtube_auth_store.save_youtube_credentials(
        uid=pending["uid"],
        credentials_json=flow.credentials.to_json(),
        channel_info=channel_info,
    )
    await youtube_auth_store.delete_pending_youtube_oauth_state(state)
    logger.info("YouTube token saved for uid=%s", pending["uid"])

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


@router.delete("/youtube")
async def youtube_auth_disconnect(current_user: dict = Depends(get_current_user)):
    await youtube_auth_store.delete_youtube_credentials(current_user["uid"])
    return {"status": "disconnected"}
