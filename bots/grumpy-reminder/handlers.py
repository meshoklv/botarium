from datetime import datetime, timedelta
from typing import Optional

import re
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import logger
from keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_confirmation_keyboard,
    get_reminder_action_keyboard,
    get_snooze_keyboard,
)
from services.ai_service import ai_service
from services.database import db
from services.reminder_service import reminder_service
from services.transcription import transcription_service
from services.time_service import normalize_datetime, storage_to_local, resolve_timezone
from services.timezone_service import fallback_timezone


class BotHandlers:
    """Telegram handlers for aggressive reminder bot."""

    TIMEZONE_FLAG = "awaiting_timezone"

    @staticmethod
    async def _prompt_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE, message: Optional[str] = None):
        context.user_data[BotHandlers.TIMEZONE_FLAG] = True
        prompt = message or (
            "Чтобы не косячить со временем, назови свой город или часовой пояс."
            " Например: Москва, Нью-Йорк или Europe/Berlin."
        )
        if update.message:
            await update.message.reply_text(prompt)
        elif update.callback_query:
            await update.callback_query.edit_message_text(prompt)

    @staticmethod
    def _get_timezone_info(telegram_id: int) -> tuple[Optional[str], ZoneInfo]:
        tz_name = db.get_client_timezone(telegram_id)
        zone = resolve_timezone(tz_name)
        return tz_name, zone

    @staticmethod
    async def _handle_timezone_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        telegram_id = update.effective_user.id
        detection = {}
        try:
            detection = await ai_service.detect_timezone(text)
        except Exception as exc:
            logger.error("Timezone detection failed: %s", exc)
            detection = {}

        tz_name = detection.get("timezone") if detection else None
        note = detection.get("note") if detection else None

        if not tz_name:
            tz_name = fallback_timezone(text)
            note = note or text

        if not tz_name:
            await update.message.reply_text(
                "Не понял, что это за место. Скажи город и страну или прямой часовой пояс типа Europe/Berlin."
            )
            return

        db.update_client_timezone(telegram_id, tz_name)
        context.user_data[BotHandlers.TIMEZONE_FLAG] = False

        description = note or tz_name
        await update.message.reply_text(
            f"Настроил часовой пояс под {description}. Теперь кидай задачи.",
            reply_markup=get_main_menu_keyboard(),
        )

    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        telegram_id = user.id
        db.get_or_create_client(telegram_id, user.first_name, user.last_name, user.username)

        # Check if user is offended
        if db.is_user_offended(telegram_id):
            await update.message.reply_text("ПОШЁЛ НАХУЙ.")
            return

        message = (
            "Здорова, лентяй. Я твой бешеный будильник и буду гнать тебя до результата.\n\n"
            "Кидай задачу и время вроде \"Напомни в 07:00 отжаться\". Если проще — проори голосом, я всё равно пойму."
        )

        await update.message.reply_text(
            message,
            reply_markup=get_main_menu_keyboard(),
        )

        tz_name, _ = BotHandlers._get_timezone_info(telegram_id)
        if tz_name:
            context.user_data[BotHandlers.TIMEZONE_FLAG] = False
        else:
            await BotHandlers._prompt_timezone(update, context)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "<b>Как со мной жить:</b>\n"
            "• Говори сразу, что делать и когда: <i>\"Напомни позвонить маме завтра в 12\"</i>\n"
            "• Хочешь голосом — кричи, я переведу\n"
            "• Пока времени нет, я буду душить вопросами\n\n"
            "<b>Команды:</b>\n"
            "/start — пинок с нуля\n"
            "/help — если потерялся\n"
            "/my_reminders — твой позорный список дел\n"
            "/cancel — выкинуть текущий черновик\n"
            "/cancel_reminder N — отключить напоминание по номеру\n"
            "/edit_reminder N новое_время — изменить время напоминания\n"
            "/timezone — сменить часовой пояс\n\n"
            "<b>Управление напоминаниями:</b>\n"
            "• Отключить: \"отключи напоминание 1\", \"выруби 2\" или /cancel_reminder 1\n"
            "• Изменить время: \"перенеси зал на 15:00\", \"измени 2 на завтра\" или /edit_reminder 1 завтра в 10:00\n\n"
            "В нужный момент я ору каждые 5 минут, пока ты не нажмёшь \"Сделал\". Так что лучше не тормози."
        )

        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )

    @staticmethod
    async def my_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, context, "Сначала скажи, где живёшь, чтобы время совпало.")
            return

        reminders = reminder_service.get_user_reminders(telegram_id, zone)

        if not reminders:
            await update.message.reply_text(
                "Пусто. Значит, можно нагрузить тебя новым делом — пиши, что и когда.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        lines = ["<b>Твои напоминания:</b>\n"]
        status_map = {
            "pending": "ожидает запуска",
            "awaiting_confirmation": "жду подтверждения",
            "sent": "уже ору",
            "completed": "закрыто",
            "cancelled": "отменено",
            "snoozed": "отложено",
        }

        # Store reminder_index_map in context
        context.user_data['reminder_index_map'] = {}

        for idx, reminder in enumerate(reminders, start=1):
            human_time = reminder.get("scheduled_time_human") or BotHandlers._format_time(reminder["scheduled_time"], zone)
            status = status_map.get(reminder["status"], reminder["status"])

            # Store mapping
            context.user_data['reminder_index_map'][str(idx)] = reminder['id']

            lines.append(
                f"• <b>{idx}.</b> <b>{reminder['task']}</b>\n"
                f"  Когда: {human_time}\n"
                f"  Статус: {status}\n"
            )

        lines.append("\n💡 <i>Чтобы отключить — напиши \"отключи напоминание 1\" или \"выруби 2\"</i>")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )

    @staticmethod
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        db.clear_temp_reminder(telegram_id)
        db.clear_conversation_history(telegram_id)

        await update.message.reply_text(
            "Выкинул черновик. Не расслабляйся — кидай свежую задачу.",
            reply_markup=get_main_menu_keyboard(),
        )

    @staticmethod
    async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await BotHandlers._prompt_timezone(update, context, "Обновим часовую зону. Говори город или часовой пояс.")

    @staticmethod
    async def cancel_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel_reminder <number> command."""
        telegram_id = update.effective_user.id
        text = update.message.text.strip()
        parts = text.split()

        if len(parts) < 2:
            await update.message.reply_text(
                "Укажи номер напоминания. Например: /cancel_reminder 1\n"
                "Список напоминаний смотри в /my_reminders",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        try:
            index = parts[1]
            reminder_map = context.user_data.get('reminder_index_map', {})

            if index not in reminder_map:
                await update.message.reply_text(
                    f"Не нашёл напоминание с номером {index}. Вызови /my_reminders чтобы увидеть актуальный список.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            reminder_id = reminder_map[index]
            reminder = db.get_reminder(reminder_id)

            if not reminder:
                await update.message.reply_text(
                    "Это напоминание уже не существует. Проверь список заново.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            reminder_service.cancel_reminder(reminder_id)
            await update.message.reply_text(
                f"Напоминание №{index} отключено. Больше про \"{reminder['task']}\" не буду орать.",
                reply_markup=get_main_menu_keyboard(),
            )

        except (ValueError, IndexError):
            await update.message.reply_text(
                "Неправильный формат. Используй: /cancel_reminder 1",
                reply_markup=get_main_menu_keyboard(),
            )

    @staticmethod
    async def edit_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /edit_reminder <number> <new_time> command."""
        telegram_id = update.effective_user.id
        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, context, "Сначала настрой часовой пояс.")
            return

        text = update.message.text.strip()
        parts = text.split(maxsplit=2)

        if len(parts) < 3:
            await update.message.reply_text(
                "Укажи номер и новое время. Например: /edit_reminder 1 завтра в 15:00\n"
                "Список напоминаний смотри в /my_reminders",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        try:
            index = parts[1]
            new_time_text = parts[2]
            reminder_map = context.user_data.get('reminder_index_map', {})

            if index not in reminder_map:
                await update.message.reply_text(
                    f"Не нашёл напоминание с номером {index}. Вызови /my_reminders чтобы увидеть актуальный список.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            reminder_id = reminder_map[index]
            reminder = db.get_reminder(reminder_id)

            if not reminder:
                await update.message.reply_text(
                    "Это напоминание уже не существует. Проверь список заново.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            if reminder['status'] in ['cancelled', 'completed']:
                await update.message.reply_text(
                    f"Напоминание №{index} уже {reminder['status']}. Нельзя изменить время.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            # Use AI to parse the new time
            result = await ai_service.process_message(telegram_id, f"измени время на {new_time_text}", tz_name)
            new_datetime = result.get("extracted_data", {}).get("datetime")

            if not new_datetime:
                await update.message.reply_text(
                    "Не понял новое время. Попробуй так: /edit_reminder 1 завтра в 15:00",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            normalized = normalize_datetime(new_datetime, zone)
            db.update_reminder_time(reminder_id, normalized.storage_iso, new_datetime)

            # Reset escalation when time is changed
            db.update_escalation_level(reminder_id, 0, datetime.now().isoformat())
            db.set_user_offended(telegram_id, offended=False)

            await update.message.reply_text(
                f"Изменил время для \"{reminder['task']}\" на {normalized.human}. Не забудь сделать!",
                reply_markup=get_main_menu_keyboard(),
            )

        except Exception as exc:
            logger.error(f"Failed to edit reminder via command: {exc}")
            await update.message.reply_text(
                "Что-то пошло не так. Проверь формат: /edit_reminder 1 завтра в 15:00",
                reply_markup=get_main_menu_keyboard(),
            )

    @staticmethod
    async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id

        # Check if user is offended
        if db.is_user_offended(telegram_id):
            await update.message.reply_text("ПОШЁЛ НАХУЙ.")
            return

        try:
            voice_file = await update.message.voice.get_file()
            transcription = await transcription_service.transcribe_voice(voice_file)

            if not transcription:
                await update.message.reply_text("Не расслышал. Попробуй ещё раз голосом или текстом.")
                return

            logger.info("Voice transcription: %s", transcription)
            tz_name, _ = BotHandlers._get_timezone_info(telegram_id)
            if context.user_data.get(BotHandlers.TIMEZONE_FLAG) or not tz_name:
                await BotHandlers._handle_timezone_response(update, context, transcription)
                return

            await BotHandlers._process_user_message(update, context, telegram_id, transcription)

        except Exception as exc:
            logger.error("Voice handler error: %s", exc)
            await update.message.reply_text("Что-то пошло не так. Напиши текстом, вдруг поможет.")

    @staticmethod
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        text = update.message.text.strip()

        # Check if user is offended
        if db.is_user_offended(telegram_id):
            await update.message.reply_text("ПОШЁЛ НАХУЙ.")
            return

        if context.user_data.get(BotHandlers.TIMEZONE_FLAG):
            await BotHandlers._handle_timezone_response(update, context, text)
            return

        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, context)
            return

        if BotHandlers._is_time_request(text):
            await BotHandlers._reply_with_current_time(update, telegram_id)
            return

        # Check for cancel reminder commands
        cancel_match = BotHandlers._parse_cancel_command(text)
        if cancel_match:
            await BotHandlers._handle_cancel_reminder_text(update, context, cancel_match)
            return

        if text == "➕ Новое напоминание":
            await update.message.reply_text(
                "Давай без соплей. Пиши цель и время: \"Напомни добить отчёт в 14:30\". Можешь голосом — я распознаю.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        if text == "⏰ Мои напоминания":
            await BotHandlers.my_reminders_command(update, context)
            return

        if text == "ℹ️ Помощь":
            await BotHandlers.help_command(update, context)
            return

        if text == "❌ Отменить":
            await BotHandlers.cancel_command(update, context)
            return

        await BotHandlers._process_user_message(update, context, telegram_id, text)

    @staticmethod
    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        telegram_id = update.effective_user.id
        data = query.data or ""

        try:
            if data.startswith("confirm:"):
                await BotHandlers._handle_confirmation_callbacks(update, telegram_id, context)
                return

            if data.startswith("reminder_done:"):
                reminder_id = int(data.split(":")[1])
                db.update_reminder_status(reminder_id, "completed")

                # Reset escalation level
                db.update_escalation_level(reminder_id, 0, datetime.now().isoformat())

                # Remove offense state if any
                db.set_user_offended(telegram_id, offended=False)

                # Aggressive completion messages
                completion_messages = [
                    "Молодец, гадёныш!",
                    "Охуенно! Так держать!",
                    "Неплохо, продолжай!",
                    "Красава! Не останавливайся!",
                    "Вот это дело!",
                    "Заебись! Дальше давай!",
                    "Так держать, ёпта!",
                    "Нихуя себе, справился!",
                ]
                from random import choice
                ack = choice(completion_messages)
                await query.edit_message_text(ack)
                return

            if data.startswith("reminder_cancel:"):
                reminder_id = int(data.split(":")[1])
                db.update_reminder_status(reminder_id, "cancelled")
                await query.edit_message_text("Ок, слил. Надеюсь, потом не будешь ныть.")
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text="Ещё что-то придумал — давай сюда.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

            if data.startswith("reminder_snooze:"):
                reminder_id = int(data.split(":")[1])
                await query.edit_message_reply_markup(reply_markup=get_snooze_keyboard(reminder_id))
                return

            if data.startswith("snooze_back:"):
                reminder_id = int(data.split(":")[1])
                await query.edit_message_reply_markup(
                    reply_markup=get_reminder_action_keyboard(reminder_id)
                )
                return

            if data.startswith("snooze:"):
                _, reminder_id_str, minutes_str = data.split(":")
                reminder_id = int(reminder_id_str)
                minutes = int(minutes_str)
                reminder = db.get_reminder(reminder_id)

                if not reminder:
                    await query.edit_message_text("Не нашёл это напоминание. Создай новое.")
                    return

                # Reset escalation level when snoozed
                db.update_escalation_level(reminder_id, 0, datetime.now().isoformat())

                # Remove offense state if any
                db.set_user_offended(telegram_id, offended=False)

                _, zone = BotHandlers._get_timezone_info(telegram_id)
                current_local = storage_to_local(reminder["scheduled_time"], zone).local
                new_local = current_local + timedelta(minutes=minutes)
                normalized = normalize_datetime(new_local.isoformat(), zone)
                db.update_reminder_time(reminder_id, normalized.storage_iso, new_local.isoformat())
                await query.edit_message_text(
                    f"Отложил на {minutes} минут. Не расслабляйся, я вернусь в {normalized.human}."
                )
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text="Подготовься морально — скоро опять буду орать.",
                    reply_markup=get_main_menu_keyboard(),
                )
                return

        except Exception as exc:
            logger.error("Callback handler error: %s", exc)
            await query.edit_message_text("Что-то пошло не так. Попробуй снова.")

    @staticmethod
    async def _process_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, message: str):
        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, context)
            return
        try:
            result = await ai_service.process_message(telegram_id, message, tz_name)
        except Exception as exc:
            logger.error("AI processing failed: %s", exc)
            await update.message.reply_text("Мозг вскипел. Напиши попроще.")
            return

        # Check if AI wants to cancel a reminder
        if result.get("action") == "cancel_reminder":
            cancel_query = result.get("cancel_query", "")
            if cancel_query:
                await BotHandlers._handle_ai_cancel_request(update, telegram_id, cancel_query, zone)
            else:
                # AI couldn't determine which reminder to cancel
                await update.message.reply_text(result["response_text"], parse_mode=ParseMode.HTML)
            return

        # Check if AI wants to edit a reminder time
        if result.get("action") == "edit_reminder":
            edit_query = result.get("edit_query", "")
            new_datetime = result.get("new_datetime", "")
            if edit_query and new_datetime:
                await BotHandlers._handle_ai_edit_request(update, context, telegram_id, edit_query, new_datetime, zone)
            else:
                # AI couldn't determine which reminder to edit or new time
                await update.message.reply_text(result["response_text"], parse_mode=ParseMode.HTML)
            return

        followup = result.get("suggested_followup")
        response_text = result["response_text"]

        if followup:
            combined = f"{response_text.strip()}\n\n{followup.strip()}"
            await update.message.reply_text(combined, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)

        if result.get("is_complete"):
            await BotHandlers._show_confirmation(update, telegram_id, result["reminder_data"], zone)

    @staticmethod
    async def _show_confirmation(update: Update, telegram_id: int, reminder_data: dict, zone: ZoneInfo):
        if not reminder_data:
            return

        confirmation = reminder_service.format_confirmation(reminder_data, zone)
        confirmation += "\n\nВсё сходится или опять тупишь?"

        await update.message.reply_text(
            confirmation,
            reply_markup=get_confirmation_keyboard(),
        )

    @staticmethod
    async def _handle_confirmation_callbacks(update: Update, telegram_id: int, context):
        query = update.callback_query
        data = query.data.split(":")[1]
        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, context, "Сначала скажи, где ты, чтобы не путать часы.")
            return

        if data == "yes":
            temp = db.get_temp_reminder(telegram_id)
            if not temp or not temp.get("task") or not temp.get("datetime"):
                await query.edit_message_text("Не понял, что подтверждать. Кинь задачу заново.")
                return

            reminder_id = reminder_service.create_reminder(telegram_id, temp, zone)
            normalized = normalize_datetime(temp["datetime"], zone)
            scheduled_time = normalized.human
            await query.edit_message_text(
                f"Готово. В {scheduled_time} подниму тебя с матом и пендалями."
            )
            # Removed idle_prompt - bot stays silent after confirmation
            logger.info("User %s confirmed reminder %s", telegram_id, reminder_id)
            return

        if data == "edit":
            await query.edit_message_text(
                "Хорошо, уточни что правим — текст задачи или время?",
                reply_markup=None,
            )
            return

        if data == "cancel":
            db.clear_temp_reminder(telegram_id)
            db.clear_conversation_history(telegram_id)
            await query.edit_message_text("Выбросил. Хочешь новый пинок — формулируй.")
            try:
                idle_prompt = (await ai_service.generate_idle_prompt()).strip()
            except Exception as exc:
                logger.error("idle prompt failed: %s", exc)
                idle_prompt = "Я тут, жду следующую тупую задачку."
            if not idle_prompt:
                idle_prompt = "Я тут, жду следующую тупую задачку."
            await context.bot.send_message(
                chat_id=telegram_id,
                text=idle_prompt,
                reply_markup=get_main_menu_keyboard(),
            )
            return
    @staticmethod
    def _format_time(dt_str: str, zone: ZoneInfo) -> str:
        try:
            normalized = normalize_datetime(dt_str, zone)
            return normalized.human
        except Exception:
            return dt_str

    @staticmethod
    def _is_time_request(text: str) -> bool:
        lowered = text.lower()
        return bool(re.search(r"(какое|сколько).*(время|час)", lowered))

    @staticmethod
    async def _reply_with_current_time(update: Update, telegram_id: int):
        tz_name, zone = BotHandlers._get_timezone_info(telegram_id)
        if not tz_name:
            await BotHandlers._prompt_timezone(update, None, "Сначала скажи свой город или пояс — иначе никак.")
            return
        current_dt = datetime.now(zone)
        normalized = normalize_datetime(current_dt.isoformat(), zone)
        await update.message.reply_text(f"У тебя сейчас {normalized.human}. Давай уже строй планы.")

    @staticmethod
    def _parse_cancel_command(text: str) -> Optional[str]:
        """Parse text for cancel reminder commands. Returns reminder index if found."""
        pattern = r'(отключи|выруби|отмени|удали|сними|убери)\s+(напоминание\s*)?(\d+)'
        match = re.search(pattern, text.lower())
        if match:
            return match.group(3)  # Return the number
        return None

    @staticmethod
    async def _handle_cancel_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE, index: str):
        """Handle canceling a reminder by index from text command."""
        telegram_id = update.effective_user.id
        reminder_map = context.user_data.get('reminder_index_map', {})

        if index not in reminder_map:
            await update.message.reply_text(
                f"Не нашёл напоминание с номером {index}. Вызови /my_reminders чтобы увидеть актуальный список.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        reminder_id = reminder_map[index]
        reminder = db.get_reminder(reminder_id)

        if not reminder:
            await update.message.reply_text(
                "Это напоминание уже не существует. Проверь список заново.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        reminder_service.cancel_reminder(reminder_id)
        await update.message.reply_text(
            f"Напоминание №{index} отключено. Больше про \"{reminder['task']}\" не буду орать.",
            reply_markup=get_main_menu_keyboard(),
        )

    @staticmethod
    async def _handle_ai_cancel_request(update: Update, telegram_id: int, cancel_query: str, zone: ZoneInfo):
        """Handle AI-initiated reminder cancellation by searching for matching task."""
        reminders = reminder_service.get_user_reminders(telegram_id, zone)

        # Filter reminders that match the query
        matching = []
        query_lower = cancel_query.lower()
        for reminder in reminders:
            if reminder['status'] in ['cancelled', 'completed']:
                continue
            task_lower = reminder['task'].lower()
            if query_lower in task_lower:
                matching.append(reminder)

        if not matching:
            await update.message.reply_text(
                f"Не нашёл напоминаний про \"{cancel_query}\". Вызови /my_reminders чтобы увидеть весь список.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if len(matching) == 1:
            # Exactly one match - cancel it
            reminder = matching[0]
            reminder_service.cancel_reminder(int(reminder['id']))
            await update.message.reply_text(
                f"Отключил напоминание \"{reminder['task']}\". Больше не буду про это орать.",
                reply_markup=get_main_menu_keyboard(),
            )
        else:
            # Multiple matches - ask user to clarify
            lines = [f"Нашёл несколько напоминаний про \"{cancel_query}\":\n"]
            for idx, reminder in enumerate(matching, start=1):
                lines.append(f"{idx}. {reminder['task']}")
            lines.append(f"\nКакое конкретно отключить? Напиши номер или используй /my_reminders.")
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=get_main_menu_keyboard(),
            )

    @staticmethod
    async def _handle_ai_edit_request(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        telegram_id: int,
        edit_query: str,
        new_datetime: str,
        zone: ZoneInfo
    ):
        """Handle AI-initiated reminder time change."""
        reminders = reminder_service.get_user_reminders(telegram_id, zone)
        reminder_map = context.user_data.get('reminder_index_map', {})

        # Check if edit_query is a number (index from /my_reminders)
        if edit_query.isdigit() and edit_query in reminder_map:
            reminder_id = reminder_map[edit_query]
            reminder = db.get_reminder(reminder_id)
            if reminder and reminder['status'] not in ['cancelled', 'completed']:
                matching = [reminder]
            else:
                matching = []
        else:
            # Search by task content
            matching = []
            query_lower = edit_query.lower()
            for reminder in reminders:
                if reminder['status'] in ['cancelled', 'completed']:
                    continue
                task_lower = reminder['task'].lower()
                if query_lower in task_lower:
                    matching.append(reminder)

        if not matching:
            await update.message.reply_text(
                f"Не нашёл напоминание \"{edit_query}\". Вызови /my_reminders чтобы увидеть список.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if len(matching) > 1:
            lines = [f"Нашёл несколько напоминаний про \"{edit_query}\":\n"]
            for idx, reminder in enumerate(matching, start=1):
                lines.append(f"{idx}. {reminder['task']}")
            lines.append(f"\nКакое конкретно изменить? Напиши номер или уточни название.")
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=get_main_menu_keyboard(),
            )
            return

        # Exactly one match - edit it
        reminder = matching[0]
        try:
            normalized = normalize_datetime(new_datetime, zone)
            db.update_reminder_time(reminder["id"], normalized.storage_iso, new_datetime)

            # Reset escalation when time is changed
            db.update_escalation_level(reminder["id"], 0, datetime.now().isoformat())
            db.set_user_offended(telegram_id, offended=False)

            await update.message.reply_text(
                f"Изменил время для \"{reminder['task']}\" на {normalized.human}. Не забудь сделать!",
                reply_markup=get_main_menu_keyboard(),
            )
        except Exception as exc:
            logger.error(f"Failed to update reminder time: {exc}")
            await update.message.reply_text(
                "Не смог изменить время. Проверь формат даты и попробуй ещё раз.",
                reply_markup=get_main_menu_keyboard(),
            )

handlers = BotHandlers()
