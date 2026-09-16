"""Telegram notifier with InlineKeyboard buttons.

Config (token, allowed chats) is loaded from the DB if an admin has set it
via the web UI, otherwise from env-var defaults. The admin route calls
set_config() + stop() + start() for a live reload - no container restart.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from telegram import Bot, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .base import Notifier, ReminderPayload

logger = logging.getLogger(__name__)


def _keyboard(intake_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Genommen", callback_data=f"taken:{intake_id}"),
            InlineKeyboardButton("\u23f0 Snooze 30", callback_data=f"snooze:{intake_id}"),
            InlineKeyboardButton("\u274c Skip", callback_data=f"skip:{intake_id}"),
        ]
    ])


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self) -> None:
        self._app: Optional[Application] = None
        self._intake_repo = None
        self._last_chat_by_intake: dict[int, int] = {}
        self._config: dict[str, Any] = {}

    # ----- Config injection -----

    def set_config(self, config: dict) -> None:
        self._config = dict(config)

    @property
    def config(self) -> dict:
        return self._config

    # ----- Wiring -----

    def attach_intake_repo(self, repo) -> None:
        self._intake_repo = repo

    # ----- Notifier interface -----

    async def is_enabled(self) -> bool:
        return bool(self._config.get("enabled")) and bool(self._config.get("bot_token"))

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("Telegram disabled or no token - skipping start.")
            return
        token = self._config.get("bot_token")
        self._app = Application.builder().token(token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("today", self._cmd_today))
        self._app.add_handler(CommandHandler("list", self._cmd_list))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot started.")

    async def stop(self) -> None:
        if self._app:
            try:
                await self._app.updater.stop_polling()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
            self._app = None

    # ----- Commands + callback handler -----

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hi! Ich bin dein WhatsSup-Bot. Ich schicke dir Erinnerungen f\u00fcr deine Supplements.\n"
            "Befehle: /today, /list"
        )

    async def _cmd_today(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._intake_repo:
            return
        chat_id = update.effective_chat.id
        logs = await self._intake_repo("today", user_id=None, chat_id=chat_id)
        if not logs:
            await update.message.reply_text("Heute nichts auf dem Plan.")
            return
        lines = ["*Heute auf dem Plan:*"]
        for log in logs:
            marker = "\u2705" if log["status"] == "taken" else ("\u23f0" if log["status"] == "pending" else "\u274c")
            lines.append(f"{marker} {log['time']} \u2013 {log['name']} ({log['dose']} {log['unit']})")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_list(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._intake_repo:
            return
        sups = await self._intake_repo("list_supplements", user_id=None)
        if not sups:
            await update.message.reply_text("Du trackst aktuell nichts.")
            return
        await update.message.reply_text("\n".join([f"- {s}" for s in sups]))

    async def _on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query: CallbackQuery = update.callback_query
        await query.answer()
        chat_id = str(query.message.chat.id)
        allowed = self._config.get("allowed_chats_set") or set()
        if allowed and chat_id not in allowed:
            await query.edit_message_text("Nicht autorisiert.")
            return

        data = (query.data or "").split(":", 1)
        if len(data) != 2:
            return
        action, intake_id_str = data
        try:
            intake_id = int(intake_id_str)
        except ValueError:
            return

        if action == "taken":
            await self._intake_repo("confirm", intake_id=intake_id, via="telegram")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("\u2705 Genommen!")
        elif action == "snooze":
            await self._intake_repo("snooze", intake_id=intake_id, minutes=30, via="telegram")
            await query.answer("\u23f0 Snooze 30 Minuten")
        elif action == "skip":
            await self._intake_repo("skip", intake_id=intake_id, via="telegram")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("\u274c \u00dcbersprungen")

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        if not self._app:
            return None
        targets: list[int] = []
        for raw in (self._config.get("allowed_chats_set") or set()):
            try:
                targets.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not targets and self._last_chat_by_intake:
            targets = [self._last_chat_by_intake[payload.intake_id]]
        if not targets:
            logger.warning(
                "Telegram enabled but no chat configured and no prior "
                "interaction; have the user send /start to your bot first."
            )
            return None

        dose = f"_{payload.dose} {payload.unit}_" if payload.dose else ""
        text = (
            f"\ud83d\udc8a *Supplement-Erinnerung*\n"
            f"*{payload.supplement_name}* {dose}\n"
            f"\u23f0 Geplant: {payload.scheduled_for.strftime('%H:%M')}"
        )

        sent_ids: list[str] = []
        for chat_id in targets:
            try:
                msg = await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=_keyboard(payload.intake_id),
                    parse_mode="Markdown",
                )
                sent_ids.append(str(msg.message_id))
                self._last_chat_by_intake[payload.intake_id] = chat_id
            except Exception as e:
                logger.warning(
                    "Telegram send failed for chat=%s intake=%s: %s",
                    chat_id, payload.intake_id, e,
                )
        return ",".join(sent_ids) if sent_ids else None
