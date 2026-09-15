"""Discord notifier using discord.py v2 with interactive Buttons.

Reminder messages contain three buttons:
  [✅ Genommen] [⏰ Snooze 30min] [❌ Skip]
Clicking one updates the corresponding IntakeLog and edits the original message.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View

from ..config import get_settings
from ..models import IntakeStatus
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
        self._last_message_ids: dict[int, int] = {}  # intake_id -> discord msg id

    def attach_intake_repo(self, repo) -> None:
        """Attach a callable (intake_id, action) -> coroutine from the main app."""
        self._intake_repo = repo

    async def is_enabled(self) -> bool:
        return get_settings().discord_enabled and bool(get_settings().discord_bot_token)

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("Discord disabled - skipping start.")
            return

        s = get_settings()
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
                # quick commands: !med list, !med today
                await self._handle_command(message, content[5:])

        async def _runner():
            try:
                await self._client.start(s.discord_bot_token)
            except Exception as e:
                logger.exception("Discord bot crashed: %s", e)

        self._task = asyncio.create_task(_runner())

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass

    async def _handle_command(self, message: discord.Message, cmd: str):
        if not self._intake_repo:
            return
        if cmd == "today":
            logs = await self._intake_repo("today", user_id=None, message=message)
            if not logs:
                await message.channel.send("Heute keine Einträge.")
                return
            lines = ["**Heute auf dem Plan:**"]
            for log in logs:
                marker = "✅" if log["status"] == "taken" else ("⏰" if log["status"] == "pending" else "❌")
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
        s = get_settings()
        channel = None
        if s.discord_channel_id:
            try:
                channel = await self._client.fetch_channel(int(s.discord_channel_id))
            except Exception:
                channel = None
        if channel is None:
            # Try DM the user
            try:
                channel = await self._client.fetch_user(user_id).get_or_create_dm()
            except Exception:
                logger.warning("Could not resolve channel for Discord reminder")
                return None

        dose = f"{payload.dose} {payload.unit}" if payload.dose else ""
        embed = discord.Embed(
            title="💊 Supplement-Erinnerung",
            description=f"**{payload.supplement_name}** {dose}".strip(),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Geplant",
            value=payload.scheduled_for.strftime("%H:%M"),
            inline=True,
        )
        if payload.action_url:
            embed.add_field(name="Web-UI", value=f"[Öffnen]({payload.action_url})", inline=False)

        view = _build_view(payload.intake_id, self)
        msg = await channel.send(embed=embed, view=view)
        self._last_message_ids[payload.intake_id] = msg.id
        return str(msg.id)

    async def _handle_button(self, interaction: Interaction, intake_id: int, action: str):
        if not self._intake_repo:
            await interaction.response.send_message("Backend nicht verbunden.", ephemeral=True)
            return

        # Permission check (if list configured)
        s = get_settings()
        if s.discord_allowed_user_set:
            if str(interaction.user.id) not in s.discord_allowed_user_set:
                await interaction.response.send_message("Nicht autorisiert.", ephemeral=True)
                return

        if action == "taken":
            await self._intake_repo("confirm", intake_id=intake_id, via="discord")
            await interaction.response.edit_message(
                content=None,
                embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                view=None,
            )
            await interaction.followup.send("✅ Genommen markiert.", ephemeral=True)
        elif action == "snooze":
            await self._intake_repo("snooze", intake_id=intake_id, minutes=30, via="discord")
            await interaction.response.send_message("⏰ Snooze 30 Minuten.", ephemeral=True)
        elif action == "skip":
            await self._intake_repo("skip", intake_id=intake_id, via="discord")
            await interaction.response.edit_message(
                content=None,
                embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                view=None,
            )
            await interaction.followup.send("❌ Übersprungen.", ephemeral=True)
