"""WhatsApp notifier via CallMeBot (free, unofficial, plain-text only).

CallMeBot is a third-party HTTP gateway that forwards text messages to a
WhatsApp number. No buttons, no per-intake tracking \u2014 the user confirms
intakes in the web UI or by replying via another channel.

Config (phone, apikey, enable flag) is loaded from the DB if an admin has
set it via the web UI, otherwise from env-var defaults. The admin route calls
set_config() + stop() + start() for a live reload - no container restart.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .base import Notifier, ReminderPayload

logger = logging.getLogger(__name__)


class WhatsAppNotifier(Notifier):
    name = "whatsapp"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def set_config(self, config: dict) -> None:
        self._config = dict(config)

    @property
    def config(self) -> dict:
        return self._config

    async def is_enabled(self) -> bool:
        return bool(self._config.get("enabled")) and bool(self._config.get("phone")) and bool(self._config.get("apikey"))

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("WhatsApp disabled or missing phone/apikey - skipping start.")
            return
        logger.info("WhatsApp notifier ready (phone=%s).", self._config.get("phone"))

    async def stop(self) -> None:
        # Nothing to stop - WhatsApp uses HTTP on demand.
        pass

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        if not await self.is_enabled():
            return None
        phone = self._config.get("phone")
        apikey = self._config.get("apikey")
        dose = f"{payload.dose} {payload.unit}" if payload.dose else ""
        text = (
            f"\ud83d\udc8a Supplement-Erinnerung\n"
            f"{payload.supplement_name} {dose}\n"
            f"\u23f0 Geplant: {payload.scheduled_for.strftime('%H:%M')}\n"
            f"\u2705 Im Web abhaken: {payload.action_url or '/'}"
        )
        url = f"https://api.callmebot.com/whatsapp.php?phone={quote(phone)}&text={quote(text)}&apikey={quote(apikey)}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    logger.info("WhatsApp reminder sent to %s", phone)
                    return "ok"
                logger.warning("CallMeBot returned %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("WhatsApp send failed: %s", e)
        return None
