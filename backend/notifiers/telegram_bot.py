"""Telegram notifier with InlineKeyboard buttons."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Bot, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from ..config import get_settings
from .base import Notifier, ReminderPayload

logger = logging.getLogger(__name__)


def _keyboard(intake_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Genommen", callback_data=f"taken:{intake_id}"),
            InlineKeyboardButton("⏰ Snooze 30", callback_data=f"snooze:{intake_id}"),
            InlineKeyboardButton("❌ Skip", callback_data=f"skip:{intake_id}"),
        ]
    ])


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self) -> None:
        self._app: Optional[Application] = None
        self._intake_repo = None
        self._last_chat_by_intake: dict[int, int] = {}

    def attach_intake_repo(self, repo) -> None:
        self._intake_repo = repo

    async def is_enabled(self) -> bool:
        return get_settings().telegram_enabled and bool(get_settings().telegram_bot_token)

    async def start(self) -> None:
        if not await self.is_enabled():
            logger.info("Telegram disabled - skipping start.")
            return
        s = get_settings()
        self._app = Application.builder().token(s.telegram_bot_token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("today", self._cmd_today))
        self._app.add_handler(CommandHandler("list", self._cmd_list))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))

        # run_polling is blocking; use a worker thread/coroutine
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

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hi! Ich bin dein MedTracker-Bot. Ich schicke dir Erinnerungen für deine Supplements.\n"
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
            marker = "✅" if log["status"] == "taken" else ("⏰" if log["status"] == "pending" else "❌")
            lines.append(f"{marker} {log['time']} – {log['name']} ({log['dose']} {log['unit']})")
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
        s = get_settings()
        chat_id = str(query.message.chat.id)
        if s.telegram_allowed_chat_set and chat_id not in s.telegram_allowed_chat_set:
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
            await query.answer("✅ Genommen!")
        elif action == "snooze":
            await self._intake_repo("snooze", intake_id=intake_id, minutes=30, via="telegram")
            await query.answer("⏰ Snooze 30 Minuten")
        elif action == "skip":
            await self._intake_repo("skip", intake_id=intake_id, via="telegram")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("❌ Übersprungen")

    async def send_reminder(self, user_id: int, payload: ReminderPayload) -> Optional[str]:
        if not self._app:
            return None
        s = get_settings()
        target_chat: Optional[int] = None
        if s.telegram_allowed_chat_set:
            try:
                target_chat = int(next(iter(s.telegram_allowed_chat_set)))
            except Exception:
                target_chat = None
        if target_chat is None and self._last_chat_by_intake:
            # No explicit config - we don't know where to send. Skip.
            return None
        if target_chat is None:
            return None

        dose = f"_{payload.dose} {payload.unit}_" if payload.dose else ""
        text = (
            f"💊 *Supplement-Erinnerung*\n"
            f"*{payload.supplement_name}* {dose}\n"
            f"⏰ Geplant: {payload.scheduled_for.strftime('%H:%M')}"
        )
        msg = await self._app.bot.send_message(
            chat_id=target_chat,
            text=text,
            reply_markup=_keyboard(payload.intake_id),
            parse_mode="Markdown",
        )
        self._last_chat_by_intake[payload.intake_id] = target_chat
        return str(msg.message_id)
