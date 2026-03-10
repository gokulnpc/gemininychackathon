import asyncio
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.infra.firebase_admin import verify_id_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency — verifies Firebase ID token, auto-provisions user profile,
    and returns enriched claims: { uid, email, display_name, photo_url, credits }.

    Raises 401 if the token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        claims = verify_id_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    uid = claims["uid"]
    email = claims.get("email")
    display_name = claims.get("name")
    photo_url = claims.get("picture")

    # Auto-provision user profile and update last_seen_at on every request
    try:
        from services.storage import firestore_db
        profile = await firestore_db.get_or_create_user(
            uid=uid,
            email=email,
            display_name=display_name,
            photo_url=photo_url,
        )
    except Exception:
        logger.warning("Failed to provision user profile for uid=%s — continuing", uid)
        profile = {}

    return {
        "uid": uid,
        "email": email,
        "display_name": profile.get("display_name") or display_name,
        "photo_url": profile.get("photo_url") or photo_url,
        "credits": profile.get("credits", 1000),
    }
