"""Notifier abstraction + a registry of available channels."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ReminderPayload:
    """What a notifier needs to render a reminder."""
    intake_id: int
    supplement_name: str
    dose: Optional[float]
    unit: Optional[str]
    scheduled_for: datetime
    action_url: Optional[str] = None  # fallback web link


@dataclass
class ConfirmResult:
    """Result returned by a notifier when it receives a button/tap."""
    intake_id: int
    confirmed: bool
    snooze_minutes: Optional[int] = None
    via: str = "unknown"
    raw: dict = field(default_factory=dict)


class Notifier:
    """Base class. Concrete impls: DiscordNotifier, TelegramNotifier, WhatsAppNotifier."""

    name: str = "base"

    async def start(self) -> None:
        """Initialize the channel (login, start polling, etc). Called once at startup."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Graceful shutdown."""
        raise NotImplementedError

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        """Send a reminder; return message id if the channel supports callbacks (Discord/Telegram)."""
        raise NotImplementedError

    async def is_enabled(self) -> bool:
        return False
