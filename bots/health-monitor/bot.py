#!/usr/bin/env python3
"""
Health Monitor Telegram Bot.
Only responds to the owner (CHAT_ID from config).
"""

import os
import subprocess
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import config
from fetch_data import fetch_from_phone, fetch_from_local
from parse_gadgetbridge import parse_db, save_parsed_data
from analyze import analyze
from notify import split_message

OWNER_ID = config.CHAT_ID


def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != OWNER_ID:
            return
        return await func(update, context)
    return wrapper


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Синхр. + Отчет", callback_data="sync_report")],
        [
            InlineKeyboardButton("Сегодня", callback_data="report_today"),
            InlineKeyboardButton("Вчера", callback_data="report_yesterday"),
        ],
        [
            InlineKeyboardButton("Обновить данные", callback_data="force_sync"),
            InlineKeyboardButton("Статус", callback_data="status"),
        ],
    ])


@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Монитор здоровья", reply_markup=main_keyboard())


@owner_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "force_sync":
        await query.edit_message_text("Принудительная синхронизация...")
        db_path = fetch_from_phone()
        if db_path:
            size = os.path.getsize(db_path)
            await query.edit_message_text(
                f"Данные обновлены: {size // 1024} KB",
                reply_markup=main_keyboard()
            )
        else:
            # Fallback to local
            db_path = fetch_from_local()
            if db_path:
                mtime = datetime.fromtimestamp(os.path.getmtime(db_path)).strftime("%H:%M")
                await query.edit_message_text(
                    f"Телефон недоступен. Локальная копия от {mtime}",
                    reply_markup=main_keyboard()
                )
            else:
                await query.edit_message_text(
                    "Телефон недоступен, локальной копии нет",
                    reply_markup=main_keyboard()
                )

    elif action in ("sync_report", "report_today", "report_yesterday"):
        await query.edit_message_text("Синхронизирую...")

        db_path = fetch_from_phone()
        if not db_path:
            db_path = fetch_from_local()
        if not db_path:
            await query.edit_message_text("Нет данных", reply_markup=main_keyboard())
            return

        if action == "report_yesterday":
            target = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target = datetime.now().strftime("%Y-%m-%d")

        try:
            health_data = parse_db(db_path, target_date=target)
            save_parsed_data(health_data)

            await query.edit_message_text("Анализирую...")
            report = analyze(health_data)

            full = f"**{target}**\n\n{report}"

            # Send as new message (edit has length limits)
            for chunk in split_message(full, 4000):
                try:
                    await context.bot.send_message(OWNER_ID, chunk, parse_mode="Markdown")
                except Exception:
                    await context.bot.send_message(OWNER_ID, chunk)

            # Replace original with keyboard
            await context.bot.send_message(OWNER_ID, "Монитор здоровья", reply_markup=main_keyboard())

        except Exception as e:
            await query.edit_message_text(f"Ошибка: {e}", reply_markup=main_keyboard())

    elif action == "status":
        lines = []

        try:
            r = subprocess.run(
                ["ssh", config.PHONE_SSH_HOST, "-o", "ConnectTimeout=3", "echo ok"],
                capture_output=True, text=True, timeout=10
            )
            lines.append(f"SSH: {'OK' if r.returncode == 0 else 'offline'}")
        except Exception:
            lines.append("SSH: offline")

        db_path = config.LOCAL_DB_PATH
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            mtime = datetime.fromtimestamp(os.path.getmtime(db_path)).strftime("%d.%m %H:%M")
            lines.append(f"БД: {size // 1024} KB ({mtime})")
        else:
            lines.append("БД: нет файла")

        await query.edit_message_text("\n".join(lines), reply_markup=main_keyboard())


@owner_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Монитор здоровья", reply_markup=main_keyboard())


def main():
    if not config.BOT_TOKEN or not config.CHAT_ID:
        raise SystemExit("Set HEALTH_BOT_TOKEN and CHAT_ID in .env (see .env.example)")
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Монитор здоровья запущен. Владелец: {OWNER_ID}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
