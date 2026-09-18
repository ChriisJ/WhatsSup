"""Discord notifier using discord.py v2 with interactive Buttons.

Reminder messages contain three buttons:
  [\u2705 Genommen] [\u23f0 Snooze 30min] [\u274c Skip]
Clicking one updates the corresponding IntakeLog and edits the original message.

Config (token, channel, allowed users) is loaded from the DB if an admin has
set it via the web UI, otherwise from the env-var defaults. The admin route
calls set_config() + stop() + start() for a live reload - no container restart.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View

from .base import ConfirmResult, Notifier, ReminderPayload

logger = logging.getLogger(__name__)


def _build_view(intake_id: int, notifier: "DiscordNotifier") -> View:
    class _V(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(
            label="Genommen",
            style=ButtonStyle.success,
            custom_id=f"taken:{intake_id}",
        )
        async def taken_btn(self, interaction: Interaction, button: Button):
            await notifier._handle_button(interaction, intake_id, "taken")

        @discord.ui.button(
            label="Snooze 30min",
            style=ButtonStyle.secondary,
            custom_id=f"snooze:{intake_id}",
        )
        async def snooze_btn(self, interaction: Interaction, button: Button):
            await notifier._handle_button(interaction, intake_id, "snooze")

        @discord.ui.button(
            label="Skippen",
            style=ButtonStyle.danger,
            custom_id=f"skip:{intake_id}",
        )
        async def skip_btn(self, interaction: Interaction, button: Button):
            await notifier._handle_button(interaction, intake_id, "skip")

    return _V()


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(self) -> None:
        self._client: Optional[discord.Client] = None
        self._task: Optional[asyncio.Task] = None
        self._intake_repo = None  # set by main wiring: IntakeRepo-style callable
        self._last_message_ids: dict[int, int] = {}
        # Effective runtime config. Populated by set_config() from admin route
        # or by main.py lifespan from DB/env at startup. NOT cached lru_settings.
        self._config: dict[str, Any] = {}

    # ----- Config injection -----

    def set_config(self, config: dict) -> None:
        """Replace the effective config. Does NOT (re)start the bot \u2014 call
        stop()/start() separately to apply."""
        self._config = dict(config)

    @property
    def config(self) -> dict:
        return self._config

    # ----- Wiring -----

    def attach_intake_repo(self, repo) -> None:
        """Attach a callable (action, **kwargs) -> coroutine from the main app."""
        self._intake_repo = repo

    # ----- Notifier interface -----

    async def is_enabled(self) -> bool:
        return bool(self._config.get("enabled")) and bool(self._config.get("bot_token"))

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("Discord disabled or no token - skipping start.")
            return

        token = self._config.get("bot_token")
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        notifier_ref = self

        @self._client.event
        async def on_ready():
            logger.info("Discord bot logged in as %s", self._client.user)

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return
            content = (message.content or "").strip().lower()
            if content.startswith("!med "):
                await self._handle_command(message, content[5:])

        async def _runner():
            try:
                await self._client.start(token)
            except Exception as e:
                logger.exception("Discord bot crashed: %s", e)

        self._task = asyncio.create_task(_runner())

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ----- Commands + reminder dispatch -----

    async def _handle_command(self, message: discord.Message, cmd: str):
        if not self._intake_repo:
            return
        if cmd == "today":
            logs = await self._intake_repo("today", user_id=None, message=message)
            if not logs:
                await message.channel.send("Heute keine Eintr\u00e4ge.")
                return
            lines = ["**Heute auf dem Plan:**"]
            for log in logs:
                marker = "\u2705" if log["status"] == "taken" else ("\u23f0" if log["status"] == "pending" else "\u274c")
                lines.append(f"{marker} {log['time']} - {log['name']} ({log['dose']} {log['unit']})")
            await message.channel.send("\n".join(lines))
        elif cmd == "list":
            sups = await self._intake_repo("list_supplements", user_id=None, message=message)
            if not sups:
                await message.channel.send("Du trackst aktuell nichts.")
                return
            await message.channel.send("\n".join([f"- {s}" for s in sups]))

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        if not self._client:
            return None
        channel = None
        channel_id = self._config.get("channel_id")
        if channel_id:
            try:
                channel = await self._client.fetch_channel(int(channel_id))
            except Exception:
                channel = None
        if channel is None:
            try:
                channel = await self._client.fetch_user(user_id).get_or_create_dm()
            except Exception:
                logger.warning("Could not resolve channel for Discord reminder")
                return None

        dose = f"{payload.dose} {payload.unit}" if payload.dose else ""
        embed = discord.Embed(
            title="\ud83d\udc8a Supplement-Erinnerung",
            description=f"**{payload.supplement_name}** {dose}".strip(),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Geplant",
            value=payload.scheduled_for.strftime("%H:%M"),
            inline=True,
        )
        if payload.action_url:
            embed.add_field(name="Web-UI", value=f"[\u00d6ffnen]({payload.action_url})", inline=False)

        view = _build_view(payload.intake_id, self)
        msg = await channel.send(embed=embed, view=view)
        self._last_message_ids[payload.intake_id] = msg.id
        return str(msg.id)

    async def _handle_button(self, interaction: Interaction, intake_id: int, action: str):
        # Discord requires a response within 3 seconds or it shows "didn't
        # respond in time". Defer immediately so we can take our time with
        # the DB work; the followup/edit_message calls below become the
        # "real" response once the work is done.
        try:
            await interaction.response.defer()
        except Exception:
            # Already responded to, or interaction expired - continue anyway.
            pass

        if not self._intake_repo:
            await interaction.followup.send("Backend nicht verbunden.", ephemeral=True)
            return

        # Permission check (if allow-list configured)
        allowed = self._config.get("allowed_users_set") or set()
        if allowed and str(interaction.user.id) not in allowed:
            await interaction.followup.send("Nicht autorisiert.", ephemeral=True)
            return

        try:
            if action == "taken":
                await self._intake_repo("confirm", intake_id=intake_id, via="discord")
                try:
                    await interaction.message.edit(
                        embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                        view=None,
                    )
                except Exception:
                    pass
                await interaction.followup.send("\u2705 Genommen markiert.", ephemeral=True)
            elif action == "snooze":
                await self._intake_repo("snooze", intake_id=intake_id, minutes=30, via="discord")
                await interaction.followup.send("\u23f0 Snooze 30 Minuten.", ephemeral=True)
            elif action == "skip":
                await self._intake_repo("skip", intake_id=intake_id, via="discord")
                try:
                    await interaction.message.edit(
                        embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                        view=None,
                    )
                except Exception:
                    pass
                await interaction.followup.send("\u274c \u00dcbersprungen.", ephemeral=True)
            else:
                await interaction.followup.send(f"Unbekannte Aktion: {action}", ephemeral=True)
        except Exception as exc:
            logger.exception("Discord button handler failed for intake=%s action=%s", intake_id, action)
            try:
                await interaction.followup.send(f"\u274c Fehler: {exc}", ephemeral=True)
            except Exception:
                pass
