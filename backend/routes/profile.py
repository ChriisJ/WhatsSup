"""User profile (body weight, notifications)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_session
from ..models import User, UserProfile
from ..schemas import ProfileIn, ProfileOut
from ..security import get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _get_or_create_profile(session: AsyncSession, user: User) -> UserProfile:
    profile = await session.get(UserProfile, user.id)
    if not profile:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


@router.get("", response_model=ProfileOut)
async def get_profile(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_or_create_profile(session, current)


@router.put("", response_model=ProfileOut)
async def update_profile(
    body: ProfileIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await _get_or_create_profile(session, current)
    for k, v in body.model_dump().items():
        setattr(profile, k, v)
    await session.commit()
    await session.refresh(profile)
    return profile
