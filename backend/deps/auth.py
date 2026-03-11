import asyncio
import logging

from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.infra.firebase_admin import verify_id_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None),
) -> dict:
    """FastAPI dependency — verifies Firebase ID token, auto-provisions user profile,
    and returns enriched claims: { uid, email, display_name, photo_url, credits }.

    Raises 401 if the token is missing or invalid.
    """
    token_str = None
    if credentials and credentials.credentials:
        token_str = credentials.credentials
        logger.info(f"Auth: Using Bearer token from header (starts with {token_str[:10]}...)")
    elif token:
        token_str = token
        logger.info(f"Auth: Using token from query parameter (starts with {token_str[:10]}...)")

    if not token_str:
        logger.info("Auth: No token found in header or query")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - no token provided",
        )
    try:
        claims = verify_id_token(token_str)
        logger.info(f"Auth: Token verified for user {claims.get('uid')}")
    except Exception as e:
        logger.error(f"Auth: Firebase verification failed for token starts with {token_str[:10]}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
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
        "credits": profile.get("credits", 300),
    }
