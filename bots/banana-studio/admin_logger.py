"""
Admin logging system - sends user activity logs to admin
"""

import logging
from typing import Optional
from pathlib import Path
import json
from datetime import datetime
from config import ADMIN_USER_ID

_logger = logging.getLogger(__name__)


class AdminLogger:
    """Silent logger for admin monitoring"""

    def __init__(self):
        self.admin_id = ADMIN_USER_ID
        self.bot = None

    def set_bot(self, bot):
        """Set bot instance for sending messages"""
        self.bot = bot

    async def log_user_action(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        action: str,
        details: str = ""
    ):
        """Log user action to admin"""
        if not self.bot or user_id == self.admin_id:
            return  # Don't log admin's own actions

        try:
            # Format user info
            user_info = f"#{user_id}"
            if username:
                user_info += f" @{username}"
            elif first_name:
                user_info += f" {first_name}"

            # Build log message
            message = f"🔔 <b>{action}</b>\n"
            message += f"👤 {user_info}\n"
            if details:
                message += f"📝 {details}"

            await self.bot.send_message(
                chat_id=self.admin_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            _logger.error(f"Failed to send admin log: {e}")

    async def log_authentication(self, user_id: int, username: Optional[str], first_name: Optional[str], success: bool):
        """Log authentication attempt"""
        action = "✅ Вход выполнен" if success else "❌ Неверный пароль"
        await self.log_user_action(user_id, username, first_name, action)

    async def log_premium_upgrade(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        """Log premium upgrade"""
        await self.log_user_action(user_id, username, first_name, "💎 Премиум активирован")

    async def log_generation(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        mode: str,
        prompt: str,
        photos_count: int,
        daily_limit: int
    ):
        """Log image generation"""
        # Show full prompt (no truncation)
        details = f"<b>Режим:</b> {mode}\n<b>Промпт:</b>\n<code>{prompt}</code>\n<b>Лимит:</b> {photos_count}/{daily_limit}"
        await self.log_user_action(user_id, username, first_name, "🎨 Генерация", details)

    async def log_limit_reached(self, user_id: int, username: Optional[str], first_name: Optional[str], is_premium: bool):
        """Log when user reaches daily limit"""
        status = "премиум" if is_premium else "бесплатный"
        details = f"Тип: {status}"
        await self.log_user_action(user_id, username, first_name, "⚠️ Лимит исчерпан", details)

    async def send_user_photo(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        photo_file_id: str,
        mode: str,
        image_number: int
    ):
        """Send user uploaded photo to admin"""
        if not self.bot or user_id == self.admin_id:
            return

        try:
            # Format user info
            user_info = f"#{user_id}"
            if username:
                user_info += f" @{username}"
            elif first_name:
                user_info += f" {first_name}"

            caption = f"📸 <b>Загружено фото</b>\n"
            caption += f"👤 {user_info}\n"
            caption += f"📝 Режим: {mode}\n"
            caption += f"🔢 Изображение: {image_number}"

            await self.bot.send_photo(
                chat_id=self.admin_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode="HTML"
            )
        except Exception as e:
            _logger.error(f"Failed to send photo to admin: {e}")

    async def send_generation_result(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        result_url: str,
        mode: str,
        prompt: str
    ):
        """Send generation result to admin"""
        if not self.bot or user_id == self.admin_id:
            return

        try:
            # Format user info
            user_info = f"#{user_id}"
            if username:
                user_info += f" @{username}"
            elif first_name:
                user_info += f" {first_name}"

            caption = f"✅ <b>Результат генерации</b>\n"
            caption += f"👤 {user_info}\n"
            caption += f"📝 Режим: {mode}\n"
            caption += f"💬 Промпт:\n<code>{prompt}</code>"

            await self.bot.send_photo(
                chat_id=self.admin_id,
                photo=result_url,
                caption=caption,
                parse_mode="HTML"
            )
        except Exception as e:
            _logger.error(f"Failed to send result to admin: {e}")


    def store_subscription_request(
        self,
        user_id: int,
        tier: str,
        cost: str,
        request_id: str,
        username: Optional[str],
        first_name: Optional[str],
    ):
        try:
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now().isoformat(),
                "user_id": user_id,
                "username": username or None,
                "first_name": first_name or None,
                "tier": tier,
                "cost": cost,
                "request_id": request_id,
            }
            with (log_dir / "subscription_requests.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            _logger.error(f"Failed to store subscription request: {e}")

# Global admin logger instance
admin_logger = AdminLogger()
