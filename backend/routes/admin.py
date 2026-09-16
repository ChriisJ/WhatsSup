"""Admin endpoints - bot configuration and runtime control.

All routes require an admin user. Bots can be configured live (no container
restart needed): saving a new config persists to the DB and triggers a hot
reload of the corresponding notifier.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import BotConfig, User
from ..schemas import BotConfigIn, BotConfigOut
from ..security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(current: User = Depends(get_current_user)) -> User:
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin-Berechtigung erforderlich")
    return current


def _resolve_notifier(request: Request, name: str):
    """Look up the Notifier object by name from app.state."""
    manager = getattr(request.app.state, "notifiers", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Notifier manager not initialized")
    table = {"discord": manager.discord, "telegram": manager.telegram, "whatsapp": manager.whatsapp}
    notifier = table.get(name)
    if notifier is None:
        raise HTTPException(status_code=400, detail=f"Unknown bot: {name}")
    return notifier


async def _build_out(session: AsyncSession, name: str, notifier) -> BotConfigOut:
    """Compose BotConfigOut merging DB row (if any) + notifier runtime status."""
    row = (await session.execute(select(BotConfig).where(BotConfig.name == name))).scalar_one_or_none()
    runtime_status = "stopped"
    runtime_message = None
    try:
        if await notifier.is_enabled():
            # We can't truly know if the bot is connected from the outside, but
            # 'enabled' is a good proxy. Real connection status would require
            # notifier-internal introspection - left as future work.
            runtime_status = "running"
    except Exception as e:
        runtime_status = "error"
        runtime_message = str(e)

    if row is not None:
        return BotConfigOut(
            name=row.name,
            enabled=row.enabled,
            bot_token=row.bot_token,
            channel_id=row.channel_id,
            guild_id=row.guild_id,
            allowed_users=row.allowed_users,
            allowed_chats=row.allowed_chats,
            phone=row.phone,
            apikey=row.apikey,
            updated_at=row.updated_at,
            runtime_status=runtime_status,
            runtime_message=runtime_message,
            is_db_override=True,
        )
    # No DB override - read env defaults from settings
    from ..config import get_settings
    s = get_settings()
    env_map = {
        "discord": dict(
            enabled=s.discord_enabled,
            bot_token=s.discord_bot_token,
            channel_id=s.discord_channel_id,
            guild_id=s.discord_guild_id,
            allowed_users=s.discord_allowed_users,
        ),
        "telegram": dict(
            enabled=s.telegram_enabled,
            bot_token=s.telegram_bot_token,
            allowed_chats=s.telegram_allowed_chats,
        ),
        "whatsapp": dict(
            enabled=s.whatsapp_enabled,
            phone=s.whatsapp_phone,
            apikey=s.whatsapp_apikey,
        ),
    }
    fields = env_map.get(name, {})
    return BotConfigOut(
        name=name,
        enabled=bool(fields.get("enabled", False)),
        bot_token=fields.get("bot_token"),
        channel_id=fields.get("channel_id"),
        guild_id=fields.get("guild_id"),
        allowed_users=fields.get("allowed_users"),
        allowed_chats=fields.get("allowed_chats"),
        phone=fields.get("phone"),
        apikey=fields.get("apikey"),
        runtime_status=runtime_status,
        runtime_message=runtime_message,
        is_db_override=False,
    )


@router.get("/bots/{name}", response_model=BotConfigOut)
async def get_bot_config(
    name: str,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if name not in {"discord", "telegram", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Unknown bot")
    notifier = _resolve_notifier(request, name)
    return await _build_out(session, name, notifier)


@router.put("/bots/{name}", response_model=BotConfigOut)
async def update_bot_config(
    name: str,
    body: BotConfigIn,
    request: Request,
    current: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if name not in {"discord", "telegram", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Unknown bot")
    notifier = _resolve_notifier(request, name)

    # Upsert the DB row.
    row = (await session.execute(select(BotConfig).where(BotConfig.name == name))).scalar_one_or_none()
    if row is None:
        row = BotConfig(name=name)
        session.add(row)
    row.enabled = body.enabled
    row.bot_token = body.bot_token or None
    row.channel_id = body.channel_id or None
    row.guild_id = body.guild_id or None
    row.allowed_users = body.allowed_users or None
    row.allowed_chats = body.allowed_chats or None
    row.phone = body.phone or None
    row.apikey = body.apikey or None
    row.updated_by = current.id
    await session.commit()
    await session.refresh(row)

    # Hot-reload the notifier.
    try:
        await notifier.stop()
    except Exception as e:
        logger.warning("Error stopping %s for reload: %s", name, e)
    if body.enabled:
        try:
            await notifier.start()
            logger.info("Bot %s hot-reloaded (DB override)", name)
        except Exception as e:
            logger.warning("Bot %s start failed after reload: %s", name, e)

    return await _build_out(session, name, notifier)


@router.post("/bots/{name}/restart", response_model=BotConfigOut)
async def restart_bot(
    name: str,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Force-restart the notifier without changing config (useful after a token
    rotation on the bot-provider side, or to recover from a transient error)."""
    if name not in {"discord", "telegram", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Unknown bot")
    notifier = _resolve_notifier(request, name)
    try:
        await notifier.stop()
    except Exception as e:
        logger.warning("Error stopping %s: %s", name, e)
    try:
        await notifier.start()
    except Exception as e:
        logger.warning("Error starting %s: %s", name, e)
    return await _build_out(session, name, notifier)


@router.delete("/bots/{name}", response_model=BotConfigOut)
async def delete_bot_override(
    name: str,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Remove the DB override; bot falls back to env-var defaults again."""
    if name not in {"discord", "telegram", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Unknown bot")
    notifier = _resolve_notifier(request, name)

    row = (await session.execute(select(BotConfig).where(BotConfig.name == name))).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()

    try:
        await notifier.stop()
    except Exception as e:
        logger.warning("Error stopping %s: %s", name, e)
    try:
        await notifier.start()
    except Exception as e:
        logger.warning("Error starting %s: %s", name, e)
    return await _build_out(session, name, notifier)
