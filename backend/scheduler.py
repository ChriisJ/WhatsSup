"""APScheduler job: every minute, find PENDING intakes whose scheduled_for
is in the past (or now) and haven't been confirmed -> send a reminder,
increment reminder_count, and schedule the next check 30 minutes later.

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
    """Runs every minute. Sends reminders for past-due PENDING intakes
    that are due (and outside quiet hours unless already >30min overdue)."""
    if _in_quiet_hours(datetime.now()):
        # Allow overdue items to still nudge, but don't pester lightly-overdue ones
        pass

    s = get_settings()
    interval = s.reminder_interval_minutes

    now = datetime.now()
    window_start = now - timedelta(minutes=interval)  # only remind if scheduled before this
    cutoff_max_stale = now - timedelta(hours=4)  # nothing older than 4h gets reminders

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
            )
        )
        result = await session.execute(stmt)
        due = result.scalars().all()

        for log in due:
            us = log.user_supplement
            supp = us.supplement if us else None
            if not us or not supp:
                continue

            # Throttle: only remind if last reminder >= interval minutes ago OR never
            last_sent = log.scheduled_for + timedelta(minutes=log.reminder_count * interval)
            if last_sent > now - timedelta(seconds=interval * 60 - 60):
                # We sent one less than `interval` minutes ago
                continue

            # Quiet hours check
            if _in_quiet_hours(now) and now - log.scheduled_for < timedelta(minutes=interval):
                continue

            user = log.user
            profile = await session.get(UserProfile, user.id)
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
            if not profile:
                profile = UserProfile(user_id=user.id)
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
            log.reminder_count += 1
            logger.info(
                "Reminded user=%s supplement=%s channels=%s count=%s",
                user.username, supp.name, channels, log.reminder_count,
            )

        # Mark stale PENDING as MISSED
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
