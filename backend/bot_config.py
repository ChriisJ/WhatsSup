"""Effective bot configuration resolver.

Bots read their settings from this helper rather than directly from
``get_settings()``. The helper checks the DB first (admin can edit via the
web UI), then falls back to the env-var defaults. Notifier implementations
call this on every start so live changes in the admin UI take effect after
a reload.

Keeping the resolver in its own module avoids a circular import: routes/admin.py
imports the notifiers; notifiers import from here; this module imports
config + models + database - no notifier dependency.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import BotConfig


async def _row_or_none(session: AsyncSession, name: str) -> Optional[BotConfig]:
    return (await session.execute(select(BotConfig).where(BotConfig.name == name))).scalar_one_or_none()


async def get_effective_config(session: AsyncSession, name: str) -> dict:
    """Return the effective config dict for a bot. DB row wins over env defaults."""
    s = get_settings()
    row = await _row_or_none(session, name)
    if name == "discord":
        return {
            "enabled": (row.enabled if row else s.discord_enabled),
            "bot_token": (row.bot_token if row else s.discord_bot_token),
            "channel_id": (row.channel_id if row else s.discord_channel_id),
            "guild_id": (row.guild_id if row else s.discord_guild_id),
            "allowed_users": (row.allowed_users if row else s.discord_allowed_users),
            "allowed_chats": None,
            "phone": None,
            "apikey": None,
        }
    if name == "telegram":
        return {
            "enabled": (row.enabled if row else s.telegram_enabled),
            "bot_token": (row.bot_token if row else s.telegram_bot_token),
            "channel_id": None,
            "guild_id": None,
            "allowed_users": None,
            "allowed_chats": (row.allowed_chats if row else s.telegram_allowed_chats),
            "phone": None,
            "apikey": None,
        }
    if name == "whatsapp":
        return {
            "enabled": (row.enabled if row else s.whatsapp_enabled),
            "bot_token": None,
            "channel_id": None,
            "guild_id": None,
            "allowed_users": None,
            "allowed_chats": None,
            "phone": (row.phone if row else s.whatsapp_phone),
            "apikey": (row.apikey if row else s.whatsapp_apikey),
        }
    return {"enabled": False}


def parse_csv_set(s: Optional[str]) -> set[str]:
    """Parse a comma-separated string into a set of stripped non-empty strings."""
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}
