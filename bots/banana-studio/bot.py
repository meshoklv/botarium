"""
Main entry point for banana-studio bot
"""

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import TELEGRAM_BOT_TOKEN
import handlers
from admin_logger import admin_logger

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Set higher logging level for httpx to avoid all GET/POST logs
logging.getLogger("httpx").setLevel(logging.WARNING)

_logger = logging.getLogger(__name__)


def main():
    """Start the bot"""
    _logger.info("Starting banana-studio bot...")

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Initialize admin logger with bot instance
    admin_logger.set_bot(application.bot)

    # Register command handlers
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("reset", handlers.reset_command))
    application.add_handler(CommandHandler("settings", handlers.settings_command))

    # Register photo handler
    application.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))

    # Register text message handler (for prompts and mode buttons)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text_message))

    # Register callback query handler (for inline buttons)
    application.add_handler(CallbackQueryHandler(handlers.handle_callback_query))

    # Start the bot
    _logger.info("Bot started successfully. Polling for updates...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
