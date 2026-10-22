import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_BOT_TOKEN, logger
from handlers import handlers


def main():
    """Main bot function"""
    try:
        logger.info("Starting salon-booking bot...")

        # Create application
        app = (
            Application.builder()
                .token(TELEGRAM_BOT_TOKEN)
                .connect_timeout(10)
                .read_timeout(30)
                .write_timeout(30)
                .pool_timeout(10)
                .build()
        )

        # Command handlers
        app.add_handler(CommandHandler('start', handlers.start_command))
        app.add_handler(CommandHandler('help', handlers.help_command))
        app.add_handler(CommandHandler('my_bookings', handlers.my_bookings_command))
        app.add_handler(CommandHandler('cancel', handlers.cancel_command))

        # Message handlers
        app.add_handler(MessageHandler(filters.VOICE, handlers.voice_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_handler))

        # Callback query handler (for inline buttons)
        app.add_handler(CallbackQueryHandler(handlers.callback_handler))

        logger.info("Bot started successfully! Ready to accept bookings...")

        # Run the bot
        app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Bot startup failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()
