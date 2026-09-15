"""Catalog + user supplement tracking endpoints."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..dose import compute_recommended_dose, get_schedule, next_occurrence
from ..interactions import find_interactions_for
from ..models import Supplement, User, UserProfile, UserSupplement
from ..schemas import (
    InteractionOut,
    SupplementCreate,
    SupplementOut,
    UserSupplementIn,
    UserSupplementOut,
)
from ..security import get_current_user

catalog_router = APIRouter(prefix="/api/supplements", tags=["supplements-catalog"])
tracking_router = APIRouter(prefix="/api/my-supplements", tags=["my-supplements"])


# ----------------------- Catalog -----------------------

@catalog_router.get("", response_model=list[SupplementOut])
async def list_catalog(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    stmt = select(Supplement).order_by(Supplement.category, Supplement.name)
    if q:
        stmt = stmt.where(Supplement.name.ilike(f"%{q}%"))
    if category:
        stmt = stmt.where(Supplement.category == category)
    result = await session.execute(stmt)
    return result.scalars().all()


@catalog_router.post("", response_model=SupplementOut)
async def create_catalog_entry(
    body: SupplementCreate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    existing = await session.execute(select(Supplement).where(Supplement.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")
    supp = Supplement(**body.model_dump())
    session.add(supp)
    await session.commit()
    await session.refresh(supp)
    return supp


# ----------------------- User's tracked supplements -----------------------

async def _enrich(us: UserSupplement, session: AsyncSession, user: User) -> UserSupplementOut:
    # Load related supplement
    supp = await session.get(Supplement, us.supplement_id)
    profile = await session.get(UserProfile, user.id)
    dose, unit = compute_recommended_dose(us, supp, profile)
    sched = get_schedule(us)
    nxt = next_occurrence(sched, datetime.now())
    return UserSupplementOut(
        id=us.id,
        supplement_id=us.supplement_id,
        supplement=SupplementOut.model_validate(supp),
        custom_dose_per_kg=us.custom_dose_per_kg,
        custom_unit=us.custom_unit,
        custom_fixed_dose=us.custom_fixed_dose,
        schedule=get_schedule(us) and [t.strftime("%H:%M") for t in get_schedule(us)] or [],
        active=us.active,
        notes=us.notes,
        recommended_dose=dose,
        recommended_unit=unit,
        next_due_at=nxt,
    )


@tracking_router.get("", response_model=list[UserSupplementOut])
async def list_my_supplements(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(UserSupplement)
        .options(selectinload(UserSupplement.supplement))
        .where(UserSupplement.user_id == current.id)
        .order_by(UserSupplement.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    out: list[UserSupplementOut] = []
    for us in rows:
        out.append(await _enrich(us, session, current))
    return out


@tracking_router.post("", response_model=UserSupplementOut)
async def add_my_supplement(
    body: UserSupplementIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Validate supplement exists
    supp = await session.get(Supplement, body.supplement_id)
    if not supp:
        raise HTTPException(status_code=404, detail="Supplement not found")

    # Reject duplicates
    existing = await session.execute(
        select(UserSupplement).where(
            UserSupplement.user_id == current.id,
            UserSupplement.supplement_id == body.supplement_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Supplement already in your list")

    # Validate schedule entries
    cleaned_schedule: list[str] = []
    for entry in body.schedule:
        try:
            h, m = entry.split(":")
            assert 0 <= int(h) < 24 and 0 <= int(m) < 60
            cleaned_schedule.append(f"{int(h):02d}:{int(m):02d}")
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {entry!r}. Use HH:MM.")

    us = UserSupplement(
        user_id=current.id,
        supplement_id=body.supplement_id,
        custom_dose_per_kg=body.custom_dose_per_kg,
        custom_unit=body.custom_unit,
        custom_fixed_dose=body.custom_fixed_dose,
        schedule_json=json.dumps(cleaned_schedule),
        active=body.active,
        notes=body.notes,
    )
    session.add(us)
    await session.commit()
    await session.refresh(us)
    return await _enrich(us, session, current)


@tracking_router.put("/{us_id}", response_model=UserSupplementOut)
async def update_my_supplement(
    us_id: int,
    body: UserSupplementIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    us = await session.get(UserSupplement, us_id)
    if not us or us.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")

    cleaned: list[str] = []
    for entry in body.schedule:
        try:
            h, m = entry.split(":")
            assert 0 <= int(h) < 24 and 0 <= int(m) < 60
            cleaned.append(f"{int(h):02d}:{int(m):02d}")
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid time: {entry!r}")

    us.custom_dose_per_kg = body.custom_dose_per_kg
    us.custom_unit = body.custom_unit
    us.custom_fixed_dose = body.custom_fixed_dose
    us.schedule_json = json.dumps(cleaned)
    us.active = body.active
    us.notes = body.notes
    await session.commit()
    await session.refresh(us)
    return await _enrich(us, session, current)


@tracking_router.delete("/{us_id}")
async def remove_my_supplement(
    us_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    us = await session.get(UserSupplement, us_id)
    if not us or us.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(us)
    await session.commit()
    return {"deleted": True}


# ----------------------- Interactions -----------------------

@tracking_router.get("/interactions/check", response_model=list[InteractionOut])
async def my_interactions(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return all interaction rules that touch the user's currently active supplements."""
    stmt = (
        select(UserSupplement)
        .options(selectinload(UserSupplement.supplement))
        .where(UserSupplement.user_id == current.id, UserSupplement.active.is_(True))
    )
    result = await session.execute(stmt)
    slugs = [r.supplement.slug for r in result.scalars().all()]
    rules = await find_interactions_for(session, slugs)
    return [
        InteractionOut(
            supplement_a=r.supplement_a_slug,
            supplement_b=r.supplement_b_slug,
            severity=r.severity,
            description=r.description,
            recommendation=r.recommendation,
        )
        for r in rules
    ]
