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
        .options(
            selectinload(IntakeLog.user_supplement).selectinload(UserSupplement.supplement)
        )
        .where(
            IntakeLog.user_id == current.id,
            IntakeLog.scheduled_for >= start,
            IntakeLog.scheduled_for < end,
        )
        .order_by(IntakeLog.scheduled_for)
    )
    result = await session.execute(stmt)
    return [_build_intake_out(log) for log in result.scalars().all()]


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
        .options(
            selectinload(IntakeLog.user_supplement).selectinload(UserSupplement.supplement)
        )
        .where(
            IntakeLog.user_id == current.id,
            IntakeLog.scheduled_for >= now,
            IntakeLog.scheduled_for < end,
            IntakeLog.status == IntakeStatus.PENDING,
        )
        .order_by(IntakeLog.scheduled_for)
    )
    result = await session.execute(stmt)
    return [_build_intake_out(log) for log in result.scalars().all()]


def _build_intake_out(log: IntakeLog) -> dict:
    """Build the IntakeOut response dict with the nested UserSupplementSlim so
    the frontend can render the supplement name + category without a follow-up
    API call. Assumes `log.user_supplement` and `.supplement` are eager-loaded
    (use `selectinload` on the query)."""
    us = log.user_supplement
    supp = us.supplement if us else None
    return {
        "id": log.id,
        "user_supplement_id": log.user_supplement_id,
        "scheduled_for": log.scheduled_for,
        "status": log.status,
        "actual_taken_at": log.actual_taken_at,
        "dose_taken": log.dose_taken,
        "unit": log.unit,
        "confirmed_via": log.confirmed_via,
        "reminder_count": log.reminder_count,
        "user_supplement": {
            "id": us.id if us else None,
            "supplement_id": us.supplement_id if us else None,
            "schedule": [t.strftime("%H:%M") for t in get_schedule(us)] if us else [],
            "custom_dose_per_kg": us.custom_dose_per_kg if us else None,
            "custom_unit": us.custom_unit if us else None,
            "custom_fixed_dose": us.custom_fixed_dose if us else None,
            "supplement_name": supp.name if supp else None,
            "supplement_category": supp.category if supp else None,
        },
    }


async def _build_intake_out_full(log: IntakeLog, session: AsyncSession) -> dict:
    """Like _build_intake_out but also fetches UserSupplement + Supplement if
    they're not already eager-loaded. Used by confirm/skip/snooze which use
    `session.get(IntakeLog, ...)` and don't pre-load relationships."""
    if log.user_supplement is None:
        us = await session.get(UserSupplement, log.user_supplement_id)
    else:
        us = log.user_supplement
    supp = us.supplement if (us and us.supplement) else (
        await session.get(Supplement, us.supplement_id) if us else None
    )
    log.user_supplement = us  # cache for downstream code if needed
    return _build_intake_out(log)


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
    return await _build_intake_out_full(log, session)


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
    return await _build_intake_out_full(log, session)


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
    # Keep status as PENDING so the scheduler can re-remind at the snoozed
    # time. Setting SNOOZED put the row into a dead state (scheduler only
    # picks up PENDING logs). See bot_bridge.py for the matching action.
    log.status = IntakeStatus.PENDING
    log.reminder_count = 0
    await session.commit()
    await session.refresh(log)
    return await _build_intake_out_full(log, session)
