from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, ConversationHandler
import asyncio
from services import TranscriptionService, SummaryService, session_manager
from utils import (
    create_main_keyboard,
    create_session_keyboard,
    create_summary_keyboard,
    remove_keyboard,
    format_session_status,
    format_transcription_preview,
    format_error_message
)
from config import logger

# Conversation states
WAITING_FOR_NAME = 1

class BotHandlers:
    """Handles all bot interactions"""

    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """🎤 Добро пожаловать в бот транскрипции голосовых сообщений!

Этот бот:
• Переводит голосовые сообщения в текст
• Создает краткие резюме из голосовых

Для начала нажмите кнопку ниже:"""

        await update.message.reply_text(
            welcome_message,
            reply_markup=create_main_keyboard()
        )

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
🔧 Инструкция по использованию:

1️⃣ Нажмите кнопку "Начать новую историю"
2️⃣ Введите имя человека, чьи голосовые вы будете отправлять
3️⃣ Отправляйте голосовые сообщения
4️⃣ Нажмите кнопку "Закончить историю" для создания резюме

⚠️ Важно:
• Максимальный размер файла: 25 МБ
• Поддерживаются голосовые сообщения Telegram
• Резюме создается на основе всех голосовых сообщений

🤖 Команды:
/start - Начать работу с ботом
/help - Показать эту справку
/cancel - Отменить текущую сессию
        """

        await update.message.reply_text(help_message)

    @staticmethod
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        user_id = update.effective_user.id

        # Clear any context data
        if 'waiting_for_name' in context.user_data:
            del context.user_data['waiting_for_name']

        if session_manager.has_active_session(user_id):
            session_manager.end_session(user_id)
            await update.message.reply_text(
                "❌ Сессия отменена.",
                reply_markup=create_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Нет активной сессии для отмены.",
                reply_markup=create_main_keyboard()
            )

    @staticmethod
    async def _handle_start_session(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Handle start session button press - ask for name"""
        context.user_data['waiting_for_name'] = True

        await update.message.reply_text(
            "📝 Введите имя человека, чьи голосовые сообщения вы будете отправлять:",
            reply_markup=remove_keyboard()
        )

    @staticmethod
    async def _handle_short_summary(update: Update, user_id: int):
        """Handle short summary generation"""
        # Get the last summary
        last_data = session_manager.get_last_summary(user_id)

        if not last_data:
            await update.message.reply_text(
                "❌ Нет предыдущего резюме для сокращения. Сначала создайте резюме из голосовых сообщений.",
                reply_markup=create_main_keyboard()
            )
            return

        last_summary, speaker_name = last_data

        # Show processing message
        processing_msg = await update.message.reply_text("🔄 Создаю короткое резюме...")

        try:
            # Generate short summary
            short_summary = await SummaryService.generate_short_summary(last_summary, speaker_name)

            if short_summary:
                # Send short summary
                await processing_msg.edit_text(
                    f"📄 Короткое резюме:\n\n{short_summary}"
                )

                # Send new session option
                await update.message.reply_text(
                    "✅ Короткое резюме готово!",
                    reply_markup=create_main_keyboard()
                )
            else:
                await processing_msg.edit_text(format_error_message('summary_failed'))
                await update.message.reply_text(
                    "Попробуйте еще раз:",
                    reply_markup=create_summary_keyboard()
                )
        except Exception as e:
            logger.error(f"Error generating short summary: {str(e)}")
            await processing_msg.edit_text(format_error_message('summary_failed'))
            await update.message.reply_text(
                "Попробуйте еще раз:",
                reply_markup=create_summary_keyboard()
            )

    @staticmethod
    async def _handle_end_session(update: Update, user_id: int):
        """Handle end session button press"""
        if not session_manager.has_active_session(user_id):
            await update.message.reply_text(
                format_error_message('no_active_session'),
                reply_markup=create_main_keyboard()
            )
            return

        transcriptions = session_manager.get_session_transcriptions(user_id)
        speaker_name = session_manager.get_speaker_name(user_id)

        if not transcriptions:
            await update.message.reply_text(
                format_error_message('no_voice_messages'),
                reply_markup=create_main_keyboard()
            )
            return

        # Show processing message
        processing_msg = await update.message.reply_text("🔄 Создаю резюме...")

        try:
            # Generate summary
            summary = await SummaryService.generate_summary(transcriptions, speaker_name)

            if summary:
                # Save summary for short summary generation
                session_manager.save_last_summary(user_id, summary, speaker_name)

                # End session
                session_manager.end_session(user_id)

                # Send summary
                await processing_msg.edit_text(
                    f"📋 Резюме истории:\n\n{summary}"
                )

                # Send summary options
                await update.message.reply_text(
                    "✅ История завершена!",
                    reply_markup=create_summary_keyboard()
                )
            else:
                await processing_msg.edit_text(format_error_message('summary_failed'))
                await update.message.reply_text(
                    "Попробуйте еще раз:",
                    reply_markup=create_session_keyboard()
                )
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            await processing_msg.edit_text(format_error_message('summary_failed'))
            await update.message.reply_text(
                "Попробуйте еще раз:",
                reply_markup=create_session_keyboard()
            )

    @staticmethod
    async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        user_id = update.effective_user.id

        # Check if there's an active session
        has_session = session_manager.has_active_session(user_id)

        # Show processing message
        processing_message = await update.message.reply_text("🔄 Транскрибирую...")

        try:
            # Get voice file
            voice_file = await update.message.voice.get_file()

            # Check file size (25MB limit)
            if voice_file.file_size > 25 * 1024 * 1024:
                await processing_message.edit_text(format_error_message('file_too_large'))
                return

            # Transcribe voice message
            transcription = await TranscriptionService.transcribe_voice(voice_file)

            if not transcription:
                await processing_message.edit_text(format_error_message('transcription_failed'))
                return

            # INSTANT PROCESSING: If no active session, process as personal voice
            if not has_session:
                await processing_message.edit_text("🔄 Создаю структурированную выжимку...")

                # Generate personal summary (impersonal format)
                summary = await SummaryService.generate_personal_summary(transcription)

                if summary:
                    await processing_message.edit_text(
                        f"📋 Выжимка:\n\n{summary}"
                    )
                    await update.message.reply_text(
                        "✅ Готово! Отправьте еще голосовое или /start",
                        reply_markup=create_main_keyboard()
                    )
                else:
                    await processing_message.edit_text(format_error_message('summary_failed'))
                    await update.message.reply_text(
                        "Попробуйте еще раз",
                        reply_markup=create_main_keyboard()
                    )
                return

            # SESSION MODE: Add to active session
            session_manager.add_voice_message(user_id, voice_file, transcription)

            # Get current session count
            message_count = session_manager.get_session_count(user_id)

            # Send simple confirmation
            await processing_message.edit_text(f"✅ Сообщение #{message_count} добавлено")

            # Only show status if this is the first message
            if message_count == 1:
                await update.message.reply_text(
                    format_session_status(message_count),
                    reply_markup=create_session_keyboard()
                )

        except Exception as e:
            logger.error(f"Error handling voice message: {str(e)}")
            await processing_message.edit_text(format_error_message('general_error'))

    @staticmethod
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages and keyboard buttons"""
        user_id = update.effective_user.id
        text = update.message.text

        # Check if waiting for speaker name
        if context.user_data.get('waiting_for_name', False):
            speaker_name = text.strip()

            if not speaker_name:
                await update.message.reply_text(
                    "❌ Пожалуйста, введите корректное имя:",
                    reply_markup=remove_keyboard()
                )
                return

            # Start session with speaker name
            session_manager.start_session(user_id, speaker_name)
            del context.user_data['waiting_for_name']

            await update.message.reply_text(
                f"📝 История начата для {speaker_name}! Отправляйте голосовые сообщения.",
                reply_markup=create_session_keyboard()
            )
            return

        # Handle keyboard buttons
        if text == "🎤 Начать новую историю":
            await BotHandlers._handle_start_session(update, context, user_id)
        elif text == "✅ Закончить историю":
            await BotHandlers._handle_end_session(update, user_id)
        elif text == "📄 Сделать еще короче":
            await BotHandlers._handle_short_summary(update, user_id)
        elif session_manager.has_active_session(user_id):
            await update.message.reply_text(
                "📝 Отправляйте голосовые сообщения или нажмите 'Закончить историю'"
            )
        else:
            await update.message.reply_text(
                "👋 Привет! Для начала работы нажмите кнопку ниже:",
                reply_markup=create_main_keyboard()
            )

# Export handlers for easy import
handlers = BotHandlers()