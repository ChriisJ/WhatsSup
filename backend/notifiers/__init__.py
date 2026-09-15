"""Notifier package + manager that fans out reminders to all enabled channels."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .base import ConfirmResult, Notifier, ReminderPayload
from .discord_bot import DiscordNotifier
from .telegram_bot import TelegramNotifier
from .whatsapp import WhatsAppNotifier

logger = logging.getLogger(__name__)


@dataclass
class NotifierManager:
    discord: DiscordNotifier
    telegram: TelegramNotifier
    whatsapp: WhatsAppNotifier

    @classmethod
    def default(cls) -> "NotifierManager":
        return cls(
            discord=DiscordNotifier(),
            telegram=TelegramNotifier(),
            whatsapp=WhatsAppNotifier(),
        )

    def all_enabled(self) -> list[Notifier]:
        return [n for n in (self.discord, self.telegram, self.whatsapp) if n]

    async def start_all(self) -> None:
        for n in self.all_enabled():
            try:
                await n.start()
            except Exception as e:
                logger.exception("Failed to start notifier %s: %s", n.name, e)

    async def stop_all(self) -> None:
        for n in self.all_enabled():
            try:
                await n.stop()
            except Exception as e:
                logger.warning("Failed to stop notifier %s: %s", n.name, e)

    async def broadcast_reminder(self, user_id: int, payload: ReminderPayload) -> None:
        for n in self.all_enabled():
            try:
                await n.send_reminder(user_id, payload)
            except Exception as e:
                logger.warning("Notifier %s failed: %s", n.name, e)


__all__ = [
    "Notifier",
    "NotifierManager",
    "ReminderPayload",
    "DiscordNotifier",
    "TelegramNotifier",
    "WhatsAppNotifier",
]
