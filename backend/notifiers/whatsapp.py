"""WhatsApp via CallMeBot (free, unofficial, no buttons).

CallMeBot only supports plain-text messages. Confirmation via WhatsApp is
*not* available with this provider. Users must reply via the web UI.

Set up:
  1. Save +34 644 59 71 47 in contacts as "CallMeBot".
  2. Send:  I allow callmebot to send me messages
  3. You'll receive an apikey; put it in WHATSAPP_APIKEY.
  4. Put your phone (international format, no +) in WHATSAPP_PHONE.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import httpx

from ..config import get_settings
from .base import Notifier, ReminderPayload

logger = logging.getLogger(__name__)

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


class WhatsAppNotifier(Notifier):
    name = "whatsapp"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def is_enabled(self) -> bool:
        s = get_settings()
        return s.whatsapp_enabled and bool(s.whatsapp_phone) and bool(s.whatsapp_apikey)

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("WhatsApp disabled - skipping start.")
            return
        self._client = httpx.AsyncClient(timeout=10.0)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        if not self._client:
            return None
        s = get_settings()
        dose = f"{payload.dose} {payload.unit}" if payload.dose else ""
        text = (
            f"💊 Supplement-Erinnerung\n"
            f"{payload.supplement_name} {dose}\n"
            f"⏰ Geplant: {payload.scheduled_for.strftime('%H:%M')}\n"
            f"Bitte im Web-UI abhaken: {payload.action_url or ''}"
        ).strip()

        url = f"{CALLMEBOT_URL}?phone={s.whatsapp_phone}&text={quote(text)}&apikey={s.whatsapp_apikey}"
        try:
            r = await self._client.get(url)
            if r.status_code != 200:
                logger.warning("CallMeBot send failed: %s %s", r.status_code, r.text[:200])
                return None
        except Exception as e:
            logger.warning("CallMeBot request error: %s", e)
            return None
        return "callmebot-ok"
