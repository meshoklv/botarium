import asyncio
from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, CommandHandler, MessageHandler, TypeHandler, filters
from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, logger
from handlers import handlers

async def access_gate(update: Update, context):
    """Drop updates from users who are not in ALLOWED_USER_IDS (if the list is set)."""
    user = update.effective_user
    if ALLOWED_USER_IDS and (user is None or user.id not in ALLOWED_USER_IDS):
        raise ApplicationHandlerStop

def main():
    """Main bot function"""
    try:
        # Create application
        app = (
            Application.builder()
                .token(TELEGRAM_BOT_TOKEN)
                .connect_timeout(10)          # ожидание установки TCP‑соединения
                .read_timeout(30)             # ожидание ответа Telegram
                .write_timeout(30)            # отправка запросов
                .pool_timeout(10)             # ожидание свободного соединения из пула
                .build()
        )
        
        app.add_handler(TypeHandler(Update, access_gate), group=-1)

        # Add command handlers
        app.add_handler(CommandHandler('start', handlers.start_command))
        app.add_handler(CommandHandler('help', handlers.help_command))
        app.add_handler(CommandHandler('cancel', handlers.cancel_command))
        
        # Add voice message handler
        app.add_handler(MessageHandler(filters.VOICE, handlers.voice_handler))
        
        # Add text message handler (including keyboard buttons)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_handler))
        # app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^/start_mini_app$'), handlers.send_mini_app_link))
        
        logger.info("Bot started successfully!")
        
        # Run the bot
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Bot startup failed: {str(e)}")
        raise

if __name__ == '__main__':
    main()
