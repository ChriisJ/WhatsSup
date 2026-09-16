"""APScheduler job: every minute, find PENDING intakes whose scheduled_for
is in the past and haven't been confirmed -> send a reminder and update
``last_reminded_at`` for throttling.

This implements the "alle 30 Minuten eine Erinnerung, bis ich es aktiv abharke"
requirement without needing one job per intake.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import get_settings
from .dose import compute_recommended_dose
from .models import (
    IntakeLog,
    IntakeStatus,
    UserProfile,
    UserSupplement,
)
from .notifiers import NotifierManager, ReminderPayload

logger = logging.getLogger(__name__)


# Hard cap on how many reminders we'll send for a single PENDING intake.
# Default: 6 reminders * 30min = 3h, after which we stop pestering (the 6h
# auto-MISSED cutoff below still applies).
_MAX_REMINDERS = 6


def _in_quiet_hours(now: datetime) -> bool:
    s = get_settings()
    start = s.reminder_quiet_hours_start
    end = s.reminder_quiet_hours_end
    h = now.hour
    if start <= end:
        return start <= h < end
    # window wraps midnight, e.g. 22-7
    return h >= start or h < end


async def reminder_tick(
    session_maker,
    notifiers: NotifierManager,
) -> None:
    """Runs every minute. Sends reminders for past-due PENDING intakes.

    Throttling: a reminder is sent only if either no reminder has been sent
    yet, or the last one was sent at least ``reminder_interval_minutes``
    ago. A hard cap of ``_MAX_REMINDERS`` prevents infinite spam.

    Quiet hours: suppress reminders for items that are only slightly overdue
    (< interval); already-overdue items still get a nudge so morning
    supplements queued during the night are seen at 07:00 sharp.
    """
    s = get_settings()
    interval = s.reminder_interval_minutes
    now = datetime.now()
    cutoff_max_stale = now - timedelta(hours=4)  # don't remind anything older than 4h
    quiet = _in_quiet_hours(now)

    async with session_maker() as session:
        stmt = (
            select(IntakeLog)
            .options(
                selectinload(IntakeLog.user_supplement)
                .selectinload(UserSupplement.supplement),
                selectinload(IntakeLog.user),
            )
            .where(
                IntakeLog.status == IntakeStatus.PENDING,
                IntakeLog.scheduled_for <= now,
                IntakeLog.scheduled_for >= cutoff_max_stale,
                IntakeLog.reminder_count < _MAX_REMINDERS,
            )
        )
        result = await session.execute(stmt)
        due = result.scalars().all()

        for log in due:
            us = log.user_supplement
            supp = us.supplement if us else None
            if not us or not supp:
                continue

            # Throttle against the actual timestamp of the last reminder.
            if log.last_reminded_at is not None:
                elapsed = now - log.last_reminded_at
                if elapsed < timedelta(minutes=interval):
                    # Already reminded within this window; skip.
                    continue
            else:
                # Never reminded. Suppress during quiet hours unless it's
                # already overdue by more than the interval (i.e. it was
                # due during the previous quiet period).
                if quiet and now - log.scheduled_for < timedelta(minutes=interval):
                    continue

            user = log.user
            profile = await session.get(UserProfile, user.id)
            if not profile:
                profile = UserProfile(user_id=user.id)

            dose, unit = compute_recommended_dose(us, supp, profile)
            payload = ReminderPayload(
                intake_id=log.id,
                supplement_name=supp.name,
                dose=dose,
                unit=unit,
                scheduled_for=log.scheduled_for,
                action_url=f"/?intake={log.id}",
            )

            # Decide which channels to send to
            channels: list[str] = []
            if profile.notify_web:
                channels.append("web")
            if profile.notify_discord and await notifiers.discord.is_enabled():
                channels.append("discord")
            if profile.notify_telegram and await notifiers.telegram.is_enabled():
                channels.append("telegram")
            if profile.notify_whatsapp and await notifiers.whatsapp.is_enabled():
                channels.append("whatsapp")

            await notifiers.broadcast_reminder(user.id, payload)
            log.last_reminded_at = now
            log.reminder_count += 1
            logger.info(
                "Reminded user=%s supplement=%s channels=%s count=%s/%s",
                user.username, supp.name, channels, log.reminder_count, _MAX_REMINDERS,
            )

        # Mark very stale PENDING as MISSED (still 6h cutoff - gives the
        # _MAX_REMINDERS cap room to be the first line of defence).
        miss_cutoff = now - timedelta(hours=6)
        stale = await session.execute(
            select(IntakeLog).where(
                IntakeLog.status == IntakeStatus.PENDING,
                IntakeLog.scheduled_for < miss_cutoff,
            )
        )
        for log in stale.scalars().all():
            log.status = IntakeStatus.MISSED

        await session.commit()


def start_scheduler(session_maker, notifiers: NotifierManager) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    sched.add_job(
        reminder_tick,
        trigger=IntervalTrigger(minutes=1),
        args=[session_maker, notifiers],
        id="reminder_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=5),
    )
    sched.start()
    logger.info("APScheduler started (1-minute tick).")
    return sched