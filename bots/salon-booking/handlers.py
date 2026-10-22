from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from datetime import datetime, timedelta
from config import logger, SALON_NAME, SALON_ADDRESS
from keyboards import (
    get_main_menu_keyboard,
    get_services_inline_keyboard,
    get_masters_inline_keyboard,
    get_time_slots_inline_keyboard,
    get_confirmation_keyboard,
    get_cancel_keyboard
)
from services.database import db
from services.ai_service import ai_service
from services.transcription import transcription_service
from services.booking_service import booking_service


class BotHandlers:
    """Main handlers for the bot"""

    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        telegram_id = user.id

        # Create or get client
        db.get_or_create_client(telegram_id, user.first_name, user.last_name, user.username)

        welcome_message = f"""Добро пожаловать в <b>{SALON_NAME}</b>!

Я помогу вам записаться на услуги.

Вы можете:
• Написать что вы хотите
• Отправить голосовое сообщение
• Использовать кнопки

<i>Например: "Хочу записаться на маникюр завтра в 14:00"</i>"""

        await update.message.reply_text(
            welcome_message,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = f"""<b>Как записаться:</b>

<b>Способ 1: Быстрая запись</b>
Напишите всё сразу:
<i>"Хочу к Марии на маникюр завтра в 15:00, меня зовут Анна, телефон 89991234567"</i>

<b>Способ 2: Голосовое сообщение</b>
Надиктуйте свою запись голосом

<b>Способ 3: Диалог</b>
Я спрошу у вас всё что нужно шаг за шагом

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/my_bookings - Мои записи
/cancel - Отменить текущую запись

<b>Наши услуги:</b>
• Маникюр - 2000₽
• Педикюр - 3000₽
• Маникюр + педикюр - 4500₽
• Наращивание - 3500₽
• Дизайн - 500₽

Адрес: {SALON_ADDRESS}
Режим работы: 10:00 - 20:00 (ежедневно)"""

        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard()
        )

    @staticmethod
    async def my_bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_bookings command"""
        telegram_id = update.effective_user.id
        bookings = booking_service.get_upcoming_bookings(telegram_id)

        if not bookings:
            await update.message.reply_text(
                "У вас пока нет записей.\n\nНажмите 'Записаться' чтобы создать новую!",
                reply_markup=get_main_menu_keyboard()
            )
            return

        message = "<b>Ваши записи:</b>\n\n"

        status_map = {
            'confirmed': 'подтверждена',
            'pending': 'ожидает',
            'cancelled': 'отменена'
        }

        for booking in bookings:
            status_ru = status_map.get(booking['status'], booking['status'])
            message += f"• <b>{booking['service']}</b>\n"
            message += f"  Мастер: {booking['master']}\n"
            message += f"  Дата: {booking['date']} в {booking['time']}\n"
            message += f"  Статус: {status_ru}\n\n"

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard()
        )

    @staticmethod
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        telegram_id = update.effective_user.id

        # Clear temp booking data
        db.clear_temp_booking(telegram_id)

        # Clear conversation history
        db.clear_conversation_history(telegram_id)

        await update.message.reply_text(
            "Текущая запись отменена.\n\nЧем еще могу помочь?",
            reply_markup=get_main_menu_keyboard()
        )

    @staticmethod
    async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        telegram_id = update.effective_user.id

        try:
            # Get voice file
            voice_file = await update.message.voice.get_file()

            # Transcribe
            transcription = await transcription_service.transcribe_voice(voice_file)

            if not transcription:
                await update.message.reply_text("Не удалось распознать голосовое. Попробуйте еще раз.")
                return

            logger.info(f"Voice transcribed: {transcription}")

            # Process with AI
            result = await ai_service.process_message(telegram_id, transcription, is_voice=True)

            # Send AI response
            await update.message.reply_text(result['response_text'], parse_mode=ParseMode.HTML)

            # Check if ready to book
            if result.get('action') == 'ready_to_book' and result.get('needs_confirmation'):
                await BotHandlers._handle_booking_confirmation(update, telegram_id)

        except Exception as e:
            logger.error(f"Voice handler error: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

    @staticmethod
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        telegram_id = update.effective_user.id
        text = update.message.text

        # Handle button presses
        if text == "📅 Записаться":
            await update.message.reply_text(
                "Отлично! Расскажите что вы хотите:\n\n"
                "Например: <i>'Хочу на маникюр завтра в 14:00'</i>\n\n"
                "Или отправьте голосовое сообщение",
                parse_mode=ParseMode.HTML,
                reply_markup=get_cancel_keyboard()
            )
            return

        elif text == "📋 Мои записи":
            await BotHandlers.my_bookings_command(update, context)
            return

        elif text == "ℹ️ Помощь":
            await BotHandlers.help_command(update, context)
            return

        elif text == "❌ Отменить":
            await BotHandlers.cancel_command(update, context)
            return

        # Process message with AI
        try:
            result = await ai_service.process_message(telegram_id, text)

            # Send AI response
            await update.message.reply_text(result['response_text'], parse_mode=ParseMode.HTML)

            # Check if ready to book
            if result.get('action') == 'ready_to_book' and result.get('needs_confirmation'):
                await BotHandlers._handle_booking_confirmation(update, telegram_id)

        except Exception as e:
            logger.error(f"Text handler error: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

    @staticmethod
    async def _handle_booking_confirmation(update: Update, telegram_id: int):
        """Show booking confirmation card"""
        temp_data = db.get_temp_booking(telegram_id)

        if not temp_data:
            return

        # Format confirmation message
        confirmation_msg = booking_service.format_booking_confirmation(temp_data)
        confirmation_msg += "\n\n<b>Все верно?</b>"

        await update.message.reply_text(
            confirmation_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_confirmation_keyboard()
        )

    @staticmethod
    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()

        telegram_id = update.effective_user.id
        data = query.data

        if data.startswith("confirm:"):
            action = data.split(":")[1]

            if action == "yes":
                # Create booking
                temp_data = db.get_temp_booking(telegram_id)

                if temp_data:
                    booking_id = booking_service.create_booking(telegram_id, temp_data)

                    # Clear temp data
                    db.clear_temp_booking(telegram_id)
                    db.clear_conversation_history(telegram_id)

                    success_msg = f"""<b>Отлично! Запись подтверждена!</b>

Ждем вас <b>{temp_data['date']}</b> в <b>{temp_data['time']}</b>

Адрес: {SALON_ADDRESS}

Если возникнут вопросы - пишите в любое время!"""

                    await query.edit_message_text(success_msg, parse_mode=ParseMode.HTML)
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=".",
                        reply_markup=get_main_menu_keyboard()
                    )

            elif action == "edit":
                await query.edit_message_text(
                    "Хорошо, давайте изменим запись.\n\nНапишите что вы хотите изменить:",
                    parse_mode=ParseMode.HTML
                )

            elif action == "cancel":
                db.clear_temp_booking(telegram_id)
                db.clear_conversation_history(telegram_id)

                await query.edit_message_text(
                    "Запись отменена.",
                    parse_mode=ParseMode.HTML
                )
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=".",
                    reply_markup=get_main_menu_keyboard()
                )


# Export handlers
handlers = BotHandlers()
