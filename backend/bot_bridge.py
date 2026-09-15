"""Bridge between bots and the database/API.

The notifiers call a function with action kwargs and we translate that
to a DB operation. Returns a dict suitable for notifier-internal formatting.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .dose import compute_recommended_dose, get_schedule
from .models import (
    IntakeLog,
    IntakeStatus,
    Supplement,
    User,
    UserProfile,
    UserSupplement,
)

logger = logging.getLogger(__name__)


async def bot_action(session: AsyncSession, action: str, **kwargs) -> dict | None:
    """Translate bot commands -> DB ops.

    Actions:
      confirm  -> kwargs: intake_id, via
      snooze   -> kwargs: intake_id, minutes, via
      skip     -> kwargs: intake_id, via
      today    -> kwargs: (user_id or chat_id or None - resolves to first user for simplicity)
      list_supplements -> kwargs: (none)
    """
    if action == "confirm":
        intake_id = kwargs["intake_id"]
        via = kwargs.get("via", "bot")
        log = await session.get(IntakeLog, intake_id)
        if not log:
            return {"ok": False, "reason": "not_found"}
        if log.status == IntakeStatus.TAKEN:
            return {"ok": True, "already": True}
        us = await session.get(UserSupplement, log.user_supplement_id)
        supp = await session.get(Supplement, us.supplement_id) if us else None
        profile = await session.get(UserProfile, log.user_id)
        if us and supp:
            d, u = compute_recommended_dose(us, supp, profile)
            log.dose_taken = d
            log.unit = u
        log.status = IntakeStatus.TAKEN
        log.actual_taken_at = datetime.now()
        log.confirmed_via = via
        await session.commit()
        return {"ok": True, "supplement": supp.name if supp else "?"}

    if action == "snooze":
        intake_id = kwargs["intake_id"]
        minutes = int(kwargs.get("minutes", 30))
        log = await session.get(IntakeLog, intake_id)
        if not log:
            return {"ok": False, "reason": "not_found"}
        log.scheduled_for = datetime.now() + timedelta(minutes=minutes)
        log.status = IntakeStatus.SNOOZED
        await session.commit()
        return {"ok": True, "until": log.scheduled_for.isoformat()}

    if action == "skip":
        intake_id = kwargs["intake_id"]
        log = await session.get(IntakeLog, intake_id)
        if not log:
            return {"ok": False, "reason": "not_found"}
        log.status = IntakeStatus.SKIPPED
        await session.commit()
        return {"ok": True}

    if action == "today":
        # For single-user deployments; bots operate on the user's data.
        user = await _resolve_user(session, kwargs)
        if not user:
            return None
        await _generate_pending(session, user)
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        stmt = (
            select(IntakeLog)
            .options(selectinload(IntakeLog.user_supplement).selectinload(UserSupplement.supplement))
            .where(
                IntakeLog.user_id == user.id,
                IntakeLog.scheduled_for >= start,
                IntakeLog.scheduled_for < end,
            )
            .order_by(IntakeLog.scheduled_for)
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "time": r.scheduled_for.strftime("%H:%M"),
                "name": r.user_supplement.supplement.name if r.user_supplement and r.user_supplement.supplement else "?",
                "dose": r.dose_taken or "",
                "unit": r.unit or "",
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            }
            for r in rows
        ]

    if action == "list_supplements":
        user = await _resolve_user(session, kwargs)
        if not user:
            return []
        stmt = (
            select(UserSupplement)
            .options(selectinload(UserSupplement.supplement))
            .where(UserSupplement.user_id == user.id, UserSupplement.active.is_(True))
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [r.supplement.name for r in rows if r.supplement]

    return None


async def _resolve_user(session: AsyncSession, kwargs: dict) -> Optional[User]:
    """Resolve which user the bot is operating on. For now: first registered user."""
    user_id = kwargs.get("user_id")
    if user_id:
        u = await session.get(User, user_id)
        if u:
            return u
    # fallback: first user
    stmt = select(User).order_by(User.id).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _generate_pending(session: AsyncSession, user: User) -> None:
    """Same logic as routes.intake.generate_pending_for_user - duplicated to avoid circular import."""
    stmt = select(UserSupplement).where(
        UserSupplement.user_id == user.id, UserSupplement.active.is_(True)
    )
    rows = (await session.execute(stmt)).scalars().all()
    today = datetime.now().date()
    for us in rows:
        sched = get_schedule(us)
        today_logs = (await session.execute(
            select(IntakeLog).where(
                IntakeLog.user_id == user.id,
                IntakeLog.user_supplement_id == us.id,
                IntakeLog.scheduled_for >= datetime.combine(today, time(0, 0)),
                IntakeLog.scheduled_for < datetime.combine(today + timedelta(days=1), time(0, 0)),
            )
        )).scalars().all()
        existing_times = {r.scheduled_for.strftime("%H:%M") for r in today_logs}
        for slot in sched:
            key = slot.strftime("%H:%M")
            if key in existing_times:
                continue
            session.add(IntakeLog(
                user_id=user.id,
                user_supplement_id=us.id,
                scheduled_for=datetime.combine(today, slot),
                status=IntakeStatus.PENDING,
            ))
    await session.commit()
