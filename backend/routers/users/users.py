"""User profile router.

GET  /api/v1/users/me  — return current user's profile + credits
PATCH /api/v1/users/me — update display_name and/or photo_url
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps.auth import get_current_user
from services.storage import firestore_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["users"])


class UserProfile(BaseModel):
    uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    credits: int = 300
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    photo_url: Optional[str] = None


@router.get("/users/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the current user's profile and credit balance."""
    profile = await firestore_db.get_user(current_user["uid"])
    if profile is None:
        # Should not happen (get_current_user auto-provisions), but handle gracefully
        profile = current_user
    return UserProfile(**{k: profile.get(k) for k in UserProfile.model_fields})


class CreditsResponse(BaseModel):
    credits: int
    credit_cost_per_video: int = 100
    starting_credits: int = 300


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(current_user: dict = Depends(get_current_user)):
    """Return the current user's credit balance."""
    profile = await firestore_db.get_user(current_user["uid"])
    credits = profile.get("credits", 300) if profile else current_user.get("credits", 300)
    return CreditsResponse(credits=credits)


@router.patch("/users/me", response_model=UserProfile)
async def update_me(
    body: UpdateUserRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update display_name and/or photo_url for the current user."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = await firestore_db.update_user(current_user["uid"], updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {e}")

    return UserProfile(**{k: updated.get(k) for k in UserProfile.model_fields})
