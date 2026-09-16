"""Centralized config loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    tz: str = "Europe/Berlin"
    secret_key: str = "change-me-in-production-please"
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # Database
    database_url: str = "sqlite:///./data/whatssup.db"

    # Auth
    default_admin_username: str = "admin"
    default_admin_password: str = "changeme"

    # Reminder behavior
    reminder_interval_minutes: int = 30
    reminder_quiet_hours_start: int = 22
    reminder_quiet_hours_end: int = 7

    # Discord
    discord_enabled: bool = False
    discord_bot_token: Optional[str] = None
    discord_guild_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    discord_allowed_users: str = ""

    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_allowed_chats: str = ""

    # WhatsApp
    whatsapp_enabled: bool = False
    whatsapp_phone: Optional[str] = None
    whatsapp_apikey: Optional[str] = None

    @property
    def discord_allowed_user_set(self) -> set[str]:
        return {x.strip() for x in self.discord_allowed_users.split(",") if x.strip()}

    @property
    def telegram_allowed_chat_set(self) -> set[str]:
        return {x.strip() for x in self.telegram_allowed_chats.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
