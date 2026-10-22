from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, logger
from handlers import handlers
from scheduler import ReminderScheduler


def main():
    try:
        logger.info("Starting aggressive reminder bot...")

        app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .connect_timeout(10)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(10)
            .build()
        )

        app.add_handler(CommandHandler("start", handlers.start_command))
        app.add_handler(CommandHandler("help", handlers.help_command))
        app.add_handler(CommandHandler("my_reminders", handlers.my_reminders_command))
        app.add_handler(CommandHandler("cancel", handlers.cancel_command))
        app.add_handler(CommandHandler("timezone", handlers.timezone_command))
        app.add_handler(CommandHandler("cancel_reminder", handlers.cancel_reminder_command))
        app.add_handler(CommandHandler("edit_reminder", handlers.edit_reminder_command))

        app.add_handler(MessageHandler(filters.VOICE, handlers.voice_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_handler))

        app.add_handler(CallbackQueryHandler(handlers.callback_handler))

        scheduler = ReminderScheduler(app.bot)
        scheduler.start()

        logger.info("Bot started successfully! Ready to scream at users...")

        app.run_polling(drop_pending_updates=True)

    except Exception as exc:
        logger.error("Bot startup failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
