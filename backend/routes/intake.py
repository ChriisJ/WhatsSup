"""Intake log: confirm, skip, snooze, list, today's plan."""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import select

from ..database import get_session
from ..dose import (
    compute_recommended_dose,
    get_schedule,
    next_occurrence,
)
from ..models import IntakeLog, IntakeStatus, Supplement, User, UserProfile, UserSupplement
from ..schemas import IntakeConfirmIn, IntakeOut
from ..security import get_current_user

router = APIRouter(prefix="/api/intake", tags=["intake"])


async def _ensure_pending_for_today(
    session: AsyncSession, user: User, us: UserSupplement
) -> None:
    """Create a PENDING IntakeLog for today's scheduled time if it doesn't already exist.
    Idempotent within the day: only one PENDING per scheduled slot per day."""
    sched = get_schedule(us)
    today = datetime.now().date()
    for slot in sched:
        scheduled_dt = datetime.combine(today, slot)
        # Check existing for this slot
        stmt = select(IntakeLog).where(
            and_(
                IntakeLog.user_id == user.id,
                IntakeLog.user_supplement_id == us.id,
                IntakeLog.scheduled_for >= datetime.combine(today, time(0, 0)),
                IntakeLog.scheduled_for < datetime.combine(today + timedelta(days=1), time(0, 0)),
            )
        )
        existing = (await session.execute(stmt)).scalars().all()
        # Avoid duplicates if a record exists for this exact HH:MM
        if any(abs((rec.scheduled_for - scheduled_dt).total_seconds()) < 60 for rec in existing):
            continue
        session.add(IntakeLog(
            user_id=user.id,
            user_supplement_id=us.id,
            scheduled_for=scheduled_dt,
            status=IntakeStatus.PENDING,
        ))
    await session.commit()


async def generate_pending_for_user(session: AsyncSession, user: User) -> None:
    """Generate today's pending intake logs for all the user's active supplements."""
    stmt = (
        select(UserSupplement)
        .where(UserSupplement.user_id == user.id, UserSupplement.active.is_(True))
    )
    result = await session.execute(stmt)
    for us in result.scalars().all():
        await _ensure_pending_for_today(session, user, us)


@router.get("/today", response_model=list[IntakeOut])
async def today_plan(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await generate_pending_for_user(session, current)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    stmt = (
        select(IntakeLog)
        .where(
            IntakeLog.user_id == current.id,
            IntakeLog.scheduled_for >= start,
            IntakeLog.scheduled_for < end,
        )
        .order_by(IntakeLog.scheduled_for)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/upcoming", response_model=list[IntakeOut])
async def upcoming(
    hours: int = Query(default=24, ge=1, le=168),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await generate_pending_for_user(session, current)
    now = datetime.now()
    end = now + timedelta(hours=hours)
    stmt = (
        select(IntakeLog)
        .where(
            IntakeLog.user_id == current.id,
            IntakeLog.scheduled_for >= now,
            IntakeLog.scheduled_for < end,
            IntakeLog.status == IntakeStatus.PENDING,
        )
        .order_by(IntakeLog.scheduled_for)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/{intake_id}/confirm", response_model=IntakeOut)
async def confirm(
    intake_id: int,
    body: IntakeConfirmIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(IntakeLog, intake_id)
    if not log or log.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")
    if log.status == IntakeStatus.TAKEN:
        return log  # idempotent

    us = await session.get(UserSupplement, log.user_supplement_id)
    supp = await session.get(Supplement, us.supplement_id) if us else None
    profile = await session.get(UserProfile, current.id)
    if us and supp:
        if body.dose_taken is None:
            d, u = compute_recommended_dose(us, supp, profile)
            body.dose_taken = d
            if body.unit is None:
                body.unit = u

    log.status = IntakeStatus.TAKEN
    log.actual_taken_at = datetime.now()
    log.dose_taken = body.dose_taken
    log.unit = body.unit
    log.notes = body.notes
    log.confirmed_via = "web"
    await session.commit()
    await session.refresh(log)
    return log


@router.post("/{intake_id}/skip", response_model=IntakeOut)
async def skip(
    intake_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(IntakeLog, intake_id)
    if not log or log.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")
    log.status = IntakeStatus.SKIPPED
    await session.commit()
    await session.refresh(log)
    return log


@router.post("/{intake_id}/snooze", response_model=IntakeOut)
async def snooze(
    intake_id: int,
    minutes: int = Query(default=30, ge=5, le=240),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(IntakeLog, intake_id)
    if not log or log.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")
    log.scheduled_for = datetime.now() + timedelta(minutes=minutes)
    log.status = IntakeStatus.SNOOZED
    await session.commit()
    await session.refresh(log)
    return log
