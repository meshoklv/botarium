"""
Message and command handlers for banana-studio bot
"""

import logging
import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modes import MODE_CATALOG, ModeType, get_mode_by_code
from session_manager import session_manager
from db import db
from services import nano_banana_client, NanoBananaAPIError
from admin_logger import admin_logger
from utils import (
    create_main_keyboard,
    create_mode_keyboard,
    create_image_role_inline_keyboard,
    create_aspect_ratio_inline_keyboard,
    create_format_inline_keyboard,
    create_generation_inline_keyboard,
    create_confirm_generation_inline_keyboard,
    create_broadcast_confirm_inline_keyboard,
    create_admin_panel_inline_keyboard,
    create_broadcast_menu_inline_keyboard,
    create_broadcast_photo_step_keyboard,
    format_image_list,
    escape_html,
    create_subscription_inline_keyboard,
    create_admin_subscription_request_keyboard,
    create_subscription_contact_inline_keyboard,
)
from config import ADMIN_CONTACT_USERNAME, TIMEZONE

_logger = logging.getLogger(__name__)


def _format_user_card_text(target_id: int) -> str:
    sub = db.get_subscription(target_id)
    exp = db.get_subscription_expires_at(target_id)
    limit = db.get_daily_limit(target_id)
    photos_today = db.get_photos_count(target_id)
    today = db._today_moscow()
    status = "free"
    if sub == "ultra":
        status = "активна"
        if exp and exp < today:
            status = "истёкла"
        if not exp:
            status = "без срока"
    elif sub == "plus":
        status = "активна"
        if exp and exp < today:
            status = "истёкла"
        if not exp:
            status = "без срока"
    sub_text = ("banana.ultra" if sub == "ultra" else ("banana+" if sub == "plus" else "free"))
    info = (
        f"<b>👤 Пользователь:</b> <code>{target_id}</code>\n\n"
        + f"<b>💳 Подписка:</b> {sub_text} ({status})\n"
        + f"<b>📅 Оплачено до:</b> {exp if exp else '—'}\n"
        + f"<b>📸 Лимит/Сегодня:</b> {limit} / {photos_today}"
    )
    return info

async def upload_to_own_server(file_bytes: bytes) -> str:
    """
    Upload image to own FastAPI server and return public URL.

    Args:
        file_bytes: Image content as bytes

    Returns:
        Public URL of uploaded image

    Raises:
        Exception: If upload fails
    """
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('file', file_bytes, filename='image.jpg', content_type='image/jpeg')

            upload_url = 'http://localhost:8000/api/bot/upload-image'
            async with session.post(upload_url, data=form) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success') and result.get('url'):
                        return result['url']
                    else:
                        raise Exception(f"Upload failed: {result}")
                else:
                    text = await response.text()
                    raise Exception(f"Server returned status {response.status}: {text}")
    except Exception as e:
        _logger.error(f"Failed to upload to server: {e}")
        raise


def create_progress_bar(state: str, attempt: int, max_attempts: int) -> str:
    """
    Create animated progress bar based on task state.

    Args:
        state: Task state (waiting, queuing, generating, success, fail)
        attempt: Current attempt number
        max_attempts: Maximum attempts

    Returns:
        Formatted progress bar string
    """
    # Animated emoji cycles for visual feedback
    emoji_animations = {
        "waiting": ["⏳", "⌛"],
        "queuing": ["🔄", "🔃"],
        "generating": ["✨", "💫", "⭐", "🌟"],
        "success": ["✅"],
        "fail": ["❌"],
    }

    # Progress stage text
    stage_text = {
        "waiting": "Подготовка",
        "queuing": "В очереди",
        "generating": "Генерация",
        "success": "Готово",
        "fail": "Ошибка",
    }

    # Get animated emoji
    emoji_list = emoji_animations.get(state, emoji_animations["waiting"])
    emoji_index = (attempt - 1) % len(emoji_list)
    emoji = emoji_list[emoji_index]
    text = stage_text.get(state, "Подготовка")

    # Calculate progress percentage - fast growth in first 30 seconds, then slow
    # Most generations complete in 15-25 seconds, so we need to reach 80-90% by then
    if state == "success":
        percentage = 100
    elif state == "fail":
        percentage = 0
    else:
        # Logarithmic curve - rapid growth early, then slows down
        # attempt 5 -> 50%, attempt 10 -> 70%, attempt 20 -> 85%, attempt 40 -> 92%
        import math

        # Use logarithmic scale for fast initial growth
        if attempt <= 1:
            percentage = 15
        else:
            # log base 1.15 gives good curve: fast start, gradual slowdown
            log_progress = math.log(attempt) / math.log(1.15)
            percentage = int(min(95, 15 + log_progress * 3.5))

        percentage = max(15, min(95, percentage))

    # Create visual progress bar
    filled = int(percentage / 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty

    # Format message
    return (
        f"{emoji} <b>{text}</b>\n\n"
        f"[{bar}] {percentage}%"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    db.create_user(user_id)

    from config import ADMIN_USER_ID
    is_admin = user_id == ADMIN_USER_ID

    # Reset session
    session_manager.reset_session(user_id)
    current_mode = session_manager.get_mode(user_id)

    photos_count = session_manager.get_photos_count(user_id)
    daily_limit = session_manager.get_daily_limit(user_id)
    limit_info = "\n\n📊 <b>Лимиты:</b> безлимит" if is_admin else f"\n\n📊 <b>Лимиты:</b> {photos_count}/{daily_limit} фото сегодня"

    welcome_message = """🎨 <b>Привет! Я помогу создать изображения через Nano Banana.</b>

<b>Что я умею:</b>
• Генерировать изображения из текста (text-to-image)
• Редактировать существующие изображения
• Применять стиль из референса к вашему изображению

<b>Три режима работы:</b>

<blockquote><b>🎨 Генерация</b>
Напиши что хочешь увидеть — получишь изображение
Просто отправь текстовое описание

<b>✏️ Редактирование</b>
Отправь изображение — опиши что изменить — получишь результат

<b>📸 Референс</b>
Отправь 2 изображения — отметь какое Источник, какое Референс — Nano Banana применит стиль</blockquote>

Выбери режим ниже или просто начни отправлять промпт/изображения!"""

    await update.message.reply_text(
        welcome_message + limit_info,
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_keyboard(current_mode, is_admin=is_admin),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    user_id = update.effective_user.id

    help_text = """<b>Помощь по боту</b>

<b>Команды:</b>
/start - Начать работу сботом
/help - Показать эту справку
/reset - Сбросить текущую сессию
/settings - Настройки (формат, соотношение сторон)

<b>Режимы работы:</b>

🎨 <b>Генерация</b> - text-to-image
Просто отправь текстовое описание

✏️ <b>Редактирование</b> - image-to-image
1. Отправь изображение
2. Опиши что нужно изменить
3. Получи результат

📸 <b>Референс</b> - применение стиля
1. Отправь несколько изображений
2. Отметь какое Источник, какое Референс
3. Опиши дополнительные инструкции (опционально)
4. Получи результат

<b>Настройки:</b>
📄 Формат: PNG или JPEG
📐 Соотношение сторон: 1:1, 16:9, 9:16 и другие

<b>Вопросы?</b> Пиши @{contact}"""

    await update.message.reply_text(
        help_text.format(contact=ADMIN_CONTACT_USERNAME),
        parse_mode=ParseMode.HTML,
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reset command"""
    user_id = update.effective_user.id
    session_manager.reset_session(user_id)
    current_mode = session_manager.get_mode(user_id)

    from config import ADMIN_USER_ID
    is_admin = user_id == ADMIN_USER_ID
    await update.message.reply_text(
        "✅ Сессия сброшена. Все загруженные изображения удалены.",
        reply_markup=create_main_keyboard(current_mode, is_admin=is_admin),
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command"""
    user_id = update.effective_user.id

    current_format = session_manager.get_output_format(user_id)
    current_ratio = session_manager.get_aspect_ratio(user_id)

    settings_text = f"""⚙️ <b>Настройки</b>

<b>Текущие параметры:</b>
📄 Формат: {current_format.upper()}
📐 Соотношение сторон: {current_ratio}

Выберите что хотите изменить:"""

    buttons = [
        [
            {"text": "📐 Соотношение сторон", "callback_data": "settings:aspect"},
            {"text": "📄 Формат файла", "callback_data": "settings:format"},
        ],
    ]

    # Convert to InlineKeyboardMarkup
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]) for btn in row]
        for row in buttons
    ])

    await update.message.reply_text(
        settings_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo upload"""
    user_id = update.effective_user.id
    db.create_user(user_id)

    from config import ADMIN_USER_ID
    if session_manager.is_broadcast_photo_awaiting(user_id) and user_id == ADMIN_USER_ID:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        caption = update.message.caption or ""
        session_manager.set_broadcast_photo_awaiting(user_id, False)
        # Combine pending text with photo caption for preview and final send
        pending_text = session_manager.get_pending_broadcast_text(user_id) or ""
        combined = None
        if pending_text and caption:
            combined = f"{pending_text}\n\n{caption}"
        elif pending_text and not caption:
            combined = pending_text
        elif caption:
            combined = caption
        else:
            combined = ""
        session_manager.set_pending_broadcast_photo(user_id, file_id, combined)
        await update.message.reply_text(
            "📸 Фото добавлено. Нажмите ‘Далее к превью’.",
            parse_mode=ParseMode.HTML,
            reply_markup=create_broadcast_photo_step_keyboard(),
        )
        return

    current_mode = session_manager.get_mode(user_id)
    mode_config = MODE_CATALOG[current_mode]

    _logger.info(f"handle_photo: user={user_id}, current_mode={current_mode}")

    # Check if mode requires images
    if not mode_config.requires_images:
        await update.message.reply_text(
            f"В режиме <b>{mode_config.title}</b> не требует изображений.\n\n"
            f"Просто отправьте текстовое описание, или переключитесь в режим Редактирование/Референс.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Check image limit
    current_count = session_manager.get_image_count(user_id)
    if current_count >= mode_config.max_images:
        await update.message.reply_text(
            f"Для режима <b>{mode_config.title}</b> можно загрузить максимум {mode_config.max_images} изображений.\n\n"
            f"Используйте /reset для сброса.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Get largest photo
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # Download file from Telegram
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()

    # Upload to own server for public URL
    try:
        public_url = await upload_to_own_server(bytes(file_bytes))
        _logger.info(f"Uploaded image to server: {public_url}")
    except Exception as e:
        _logger.error(f"Failed to upload image: {e}")
        await update.message.reply_text(
            f"⚠️ Не удалось загрузить изображение на хостинг.\n\n<code>{escape_html(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Add image to session
    session_manager.add_image(user_id, file_id, public_url)
    image_index = current_count  # 0-indexed

    # Send photo to admin
    await admin_logger.send_user_photo(
        user_id,
        update.effective_user.username,
        update.effective_user.first_name,
        file_id,
        mode_config.title,
        image_index + 1
    )

    # Ask user to mark role (for reference mode)
    if current_mode == ModeType.REFERENCE:
        await update.message.reply_photo(
            photo=file_id,
            caption=f"🖼️ Изображение {image_index + 1} загружено.\n\nЭто Источник (основное) или Референс (стиль)?",
            reply_markup=create_image_role_inline_keyboard(image_index),
        )
    elif current_mode == ModeType.EDIT:
        # For edit mode, directly mark as source
        session_manager.set_image_role(user_id, image_index, "source")

        await update.message.reply_text(
            f"✅ Изображение загружено.\n\nТеперь опишите что нужно изменить:",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "✅ Изображение загружено.",
            parse_mode=ParseMode.HTML,
        )


# Password logic removed


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (prompts or commands)"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    db.create_user(user_id)

    _logger.info(f"handle_text_message: user={user_id}, text={text[:50]}")

    # Admin quick search fallback by plain numeric input
    from config import ADMIN_USER_ID
    if user_id == ADMIN_USER_ID and text.isdigit() and not session_manager.is_admin_awaiting_add_days_input(user_id):
        target_id = int(text)
        target_user = db.get_user(target_id)
        if not target_user:
            await update.message.reply_text("❌ Пользователь не найден", parse_mode=ParseMode.HTML)
        else:
            info = _format_user_card_text(target_id)
            from utils import create_admin_user_actions_keyboard
            await update.message.reply_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_id))
        return

    # Open access, no authentication required

    # Check if user hit limit and show subscription info
    if not session_manager.can_generate(user_id):
        photos_count = session_manager.get_photos_count(user_id)
        daily_limit = session_manager.get_daily_limit(user_id)
        subscribe_text = (
            f"❌ <b>Лимит исчерпан</b>\n\n"
            f"Сегодня вы сгенерировали {photos_count}/{daily_limit} фото.\n\n"
            f"💳 <b>Подписки</b>\n\n"
            f"<blockquote>• <b>banana+</b> — 15 фото/день (150 ₽/мес)\n"
            f"• <b>banana.ultra</b> — 40 фото/день (300 ₽/мес)</blockquote>"
        )
        await update.message.reply_text(
            subscribe_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_subscription_inline_keyboard(),
        )
        return

    # Check if it's a mode button (with or without checkmark)
    for mode_config in MODE_CATALOG.values():
        # Check exact match with button label
        if text == mode_config.button_label:
            _logger.info(f"Switching to mode: {mode_config.code}")
            await switch_mode(update, context, mode_config.code)
            return
        # Check if it's the same button with checkmark
        if text.startswith("✓ ") and text[2:] == mode_config.button_label:
            _logger.info(f"Switching to mode (with checkmark): {mode_config.code}")
            await switch_mode(update, context, mode_config.code)
            return

    # Check if it's a settings button
    if text == "⚙️ Настройки" or text == "✓ ⚙️ Настройки":
        await settings_command(update, context)
        return

    from config import ADMIN_USER_ID
    if text == "🛠️ Админ панель" or ("Админ панель" in text):
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("⚠️ Эта функция доступна только администратору", parse_mode=ParseMode.HTML)
            return
        await update.message.reply_text(
            "🛠️ Админ панель",
            parse_mode=ParseMode.HTML,
            reply_markup=create_admin_panel_inline_keyboard(),
        )
        return

    if user_id == ADMIN_USER_ID and session_manager.is_admin_awaiting_user_id_input(user_id):
        try:
            target_id = int(text.strip())
        except Exception:
            await update.message.reply_text("⚠️ Введите корректный числовой TG ID", parse_mode=ParseMode.HTML)
            return
        session_manager.set_admin_awaiting_user_id_input(user_id, False)
        target_user = db.get_user(target_id)
        if not target_user:
            await update.message.reply_text("❌ Пользователь не найден", parse_mode=ParseMode.HTML)
            return
        info = _format_user_card_text(target_id)
        from utils import create_admin_user_actions_keyboard
        await update.message.reply_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_id))
        return

    if user_id == ADMIN_USER_ID and session_manager.is_admin_awaiting_add_days_input(user_id):
        if text.strip().lower() in ("отмена", "cancel"):
            session_manager.set_admin_awaiting_add_days_input(user_id, False)
            target_id = session_manager.get_admin_add_days_target_user_id(user_id)
            session_manager.set_admin_add_days_target_user_id(user_id, None)
            if target_id:
                info = _format_user_card_text(target_id)
                from utils import create_admin_user_actions_keyboard
                await update.message.reply_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_id))
            else:
                await update.message.reply_text("❌ Действие отменено", parse_mode=ParseMode.HTML)
            return
        try:
            days = int(text.strip())
        except Exception:
            await update.message.reply_text("⚠️ Введите корректное число дней", parse_mode=ParseMode.HTML)
            return
        if days <= 0:
            await update.message.reply_text("⚠️ Число дней должно быть больше 0", parse_mode=ParseMode.HTML)
            return
        target_id = session_manager.get_admin_add_days_target_user_id(user_id)
        if not target_id:
            session_manager.set_admin_awaiting_add_days_input(user_id, False)
            await update.message.reply_text("❌ Не выбран пользователь", parse_mode=ParseMode.HTML)
            return
        sub = db.get_subscription(target_id)
        if sub == "free":
            from utils import create_admin_set_type_keyboard
            await update.message.reply_text("🔁 Сначала установите тип подписки", parse_mode=ParseMode.HTML, reply_markup=create_admin_set_type_keyboard(target_id))
            return
        new_exp = db.add_subscription_days(target_id, days)
        session_manager.set_admin_awaiting_add_days_input(user_id, False)
        session_manager.set_admin_add_days_target_user_id(user_id, None)
        info = _format_user_card_text(target_id)
        from utils import create_admin_user_actions_keyboard
        await update.message.reply_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_id))
        return

    # Admin stats
    from config import ADMIN_USER_ID, USE_FAKE_STATS, TIMEZONE
    if (text == "📊 Статистика" or text == "Статистика" or ("Статистика" in text)):
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text(
                "⚠️ Эта функция доступна только администратору",
                parse_mode=ParseMode.HTML,
            )
            return
        if USE_FAKE_STATS:
            total_users = 120
            photos_today = 78
            tz = ZoneInfo(TIMEZONE)
            from datetime import datetime as _dt
            today = _dt.now(tz).date()
            counts = [78, 64, 71, 83, 59, 90, 76]
            stats_pairs = [((today - timedelta(days=i)).isoformat(), counts[i]) for i in range(len(counts))]
            lines = [f"{d}: {c}" for d, c in stats_pairs]
        else:
            total_users = db.get_total_users()
            photos_today = db.get_total_photos_today()
            stats = db.get_daily_stats(7)
            lines = [f"{d}: {c}" for d, c in stats]
        stats_text = (
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"📸 Фото сегодня: {photos_today}\n\n"
            f"За последние 7 дней:\n" + ("\n".join(lines) if lines else "Нет данных")
        )
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
        return

    if (text == "📣 Рассылка" or ("Рассылка" in text)):
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("⚠️ Эта функция доступна только администратору", parse_mode=ParseMode.HTML)
            return
        await update.message.reply_text(
            "📣 Режим рассылки",
            parse_mode=ParseMode.HTML,
            reply_markup=create_broadcast_menu_inline_keyboard(),
        )
        return

    if session_manager.is_broadcast_awaiting(user_id):
        from config import ADMIN_USER_ID
        if user_id == ADMIN_USER_ID:
            session_manager.set_broadcast_awaiting(user_id, False)
            session_manager.set_pending_broadcast_text(user_id, text)
            await update.message.reply_text(
                "📸 Добавить фото? Если нет — нажмите ‘Нет’. Затем ‘Далее к превью’.",
                parse_mode=ParseMode.HTML,
                reply_markup=create_broadcast_photo_step_keyboard(),
            )
            return

    # Buy subscription button
    if text == "💳 Купить подписку" or ("Купить подписку" in text):
        subscribe_text = (
            "💳 <b>Подписки</b>\n\n"
            "<blockquote>• <b>banana+</b> — 15 фото/день (150 ₽/мес)\n"
            "• <b>banana.ultra</b> — 40 фото/день (300 ₽/мес)</blockquote>"
        )
        await update.message.reply_text(
            subscribe_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_subscription_inline_keyboard(),
        )
        return

    # Otherwise, treat as prompt
    current_mode = session_manager.get_mode(user_id)
    mode_config = MODE_CATALOG[current_mode]
    _logger.info(f"Processing as prompt: user={user_id}, current_mode={current_mode}, images_count={session_manager.get_image_count(user_id)}")

    # For generate mode, save prompt and show confirmation
    if current_mode == ModeType.GENERATE:
        session_manager.set_pending_prompt(user_id, text)
        await show_generation_preview(update, context)
        return

    # For edit/reference modes, check if images uploaded
    images = session_manager.get_images(user_id)

    if not images:
        await update.message.reply_text(
            f"⚠️ Сначала загрузите изображение для режима <b>{mode_config.title}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Check if all images have roles (for reference mode)
    if current_mode == ModeType.REFERENCE:
        # Check unmarked images
        unmarked = [img for img in images if not img.role]
        if unmarked:
            await update.message.reply_text(
                f"✏️ Отметьте роль для всех изображений (Источник/Референс).\n\n<i>Незамаркированных: {len(unmarked)}</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # Check minimum 2 images
        if len(images) < 2:
            await update.message.reply_text(
                "📸 Загрузите ещё одно изображение.\n\n<i>Для режима Референс нужно минимум 2 изображения</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # Check we have both roles
        source_images = [img for img in images if img.role == "source"]
        reference_images = [img for img in images if img.role == "reference"]

        if not source_images:
            await update.message.reply_text(
                "🖼️ Отметьте хотя бы одно изображение как <b>Источник</b> (основное).",
                parse_mode=ParseMode.HTML,
            )
            return

        if not reference_images:
            await update.message.reply_text(
                "🎨 Отметьте хотя бы одно изображение как <b>Референс</b> (стиль).",
                parse_mode=ParseMode.HTML,
            )
            return

    # Save prompt and confirm
    session_manager.set_pending_prompt(user_id, text)
    await show_generation_preview(update, context)


async def switch_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: ModeType):
    """Switch to different mode"""
    user_id = update.effective_user.id
    mode_config = MODE_CATALOG[mode]

    # Reset session when switching modes
    session_manager.reset_session(user_id)
    session_manager.set_mode(user_id, mode)

    mode_instructions = {
        ModeType.GENERATE: "Опишите что хотите увидеть на изображении:",
        ModeType.EDIT: "Загрузите изображение которое нужно отредактировать:",
        ModeType.REFERENCE: "Загрузите изображения (Источник и Референс):",
    }

    from config import ADMIN_USER_ID
    is_admin = update.effective_user.id == ADMIN_USER_ID
    await update.message.reply_text(
        f"{mode_config.emoji} <b>Режим: {mode_config.title}</b>\n\n"
        f"{mode_config.description}\n\n"
        f"{mode_instructions.get(mode, '')}",
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_keyboard(mode, is_admin=is_admin),
    )


async def show_generation_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show preview before generation and ask for confirmation"""
    user_id = update.effective_user.id
    current_mode = session_manager.get_mode(user_id)
    mode_config = MODE_CATALOG[current_mode]
    images = session_manager.get_images(user_id)
    prompt = session_manager.get_pending_prompt(user_id)
    aspect_ratio = session_manager.get_aspect_ratio(user_id)
    output_format = session_manager.get_output_format(user_id)

    preview_text = f"<b>Предпросмотр генерации</b>\n\n"
    preview_text += f"<b>Режим:</b> {mode_config.emoji} {mode_config.title}\n"

    if images:
        preview_text += f"<b>Изображения:</b>\n{format_image_list(images)}\n\n"

    if prompt:
        preview_text += f"<b>Промпт:</b>\n<blockquote>{escape_html(prompt)}</blockquote>\n\n"

    preview_text += f"<b>Настройки:</b>\n"
    preview_text += f"📄 Формат: {output_format.upper()}\n"
    preview_text += f"📐 Соотношение: {aspect_ratio}\n\n"
    preview_text += "Всё верно?"

    await update.message.reply_text(
        preview_text,
        parse_mode=ParseMode.HTML,
        reply_markup=create_confirm_generation_inline_keyboard(),
    )


async def process_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    """Process image generation request"""
    user_id = update.effective_user.id
    current_mode = session_manager.get_mode(user_id)
    aspect_ratio = session_manager.get_aspect_ratio(user_id)
    output_format = session_manager.get_output_format(user_id)

    _logger.info(f"process_generation: user={user_id}, mode={current_mode}, prompt={prompt[:50]}")

    # Send initial progress message
    initial_text = create_progress_bar("waiting", 1, 40)
    processing_msg = await update.message.reply_text(
        initial_text,
        parse_mode=ParseMode.HTML,
    )

    # Create progress callback with state tracking
    last_progress_text = initial_text
    async def update_progress(state: str, attempt: int, max_attempts: int):
        """Update progress message with current state"""
        nonlocal last_progress_text
        try:
            new_text = create_progress_bar(state, attempt, max_attempts)
            _logger.info(f"Progress update: state={state}, attempt={attempt}/{max_attempts}, changed={new_text != last_progress_text}")
            # Only update if text changed
            if new_text != last_progress_text:
                await processing_msg.edit_text(new_text, parse_mode=ParseMode.HTML)
                last_progress_text = new_text
        except Exception as e:
            _logger.warning(f"Failed to update progress: {e}")

    try:
        if current_mode == ModeType.GENERATE:
            # Text-to-image generation
            result_urls = await nano_banana_client.generate_image(
                prompt=prompt,
                output_format=output_format,
                image_size=aspect_ratio,
                progress_callback=update_progress,
            )

        elif current_mode == ModeType.EDIT:
            # Image editing
            images = session_manager.get_images(user_id)
            if not images:
                await processing_msg.edit_text("Нет загруженных изображений для редактирования.")
                return

            image_urls = [img.file_url for img in images]
            _logger.info(f"EDIT mode: user={user_id}, images_count={len(images)}, urls={image_urls}")
            result_urls = await nano_banana_client.edit_image(
                prompt=prompt,
                image_urls=image_urls,
                output_format=output_format,
                image_size=aspect_ratio,
                progress_callback=update_progress,
            )

        elif current_mode == ModeType.REFERENCE:
            # Style transfer from reference
            images = session_manager.get_images(user_id)
            source_images = session_manager.get_images_by_role(user_id, "source")
            reference_images = session_manager.get_images_by_role(user_id, "reference")

            if not source_images or not reference_images:
                await processing_msg.edit_text(
                    "Нужно хотя бы одно Источник изображение и одно Референс изображение."
                )
                return

            # Build structured prompt
            structured_prompt = (
                f"[SOURCE_IMAGE]: The main image to transform\n"
                f"[REFERENCE_IMAGE]: Apply the style, color palette, and mood from this image\n\n"
                f"{prompt if prompt else 'Apply the style from reference to source image.'}"
            )

            # Combine all image URLs (source first, then reference)
            all_image_urls = [img.file_url for img in source_images] + [img.file_url for img in reference_images]

            result_urls = await nano_banana_client.edit_image(
                prompt=structured_prompt,
                image_urls=all_image_urls,
                output_format=output_format,
                image_size=aspect_ratio,
                progress_callback=update_progress,
            )

        else:
            await processing_msg.edit_text("Неизвестный режим.")
            return

        # Send result
        if result_urls:
            await processing_msg.delete()

            # Store result URLs for full quality download
            session_manager.set_last_result_urls(user_id, result_urls)
            # Store complete generation state for regeneration (before clearing images)
            current_images = session_manager.get_images(user_id)
            session_manager.save_generation_state(user_id, prompt, current_mode, current_images)
            # Increment photo counter
            session_manager.increment_photos_count(user_id)

            # Log generation to admin
            mode_config = MODE_CATALOG[current_mode]
            photos_count = session_manager.get_photos_count(user_id)
            daily_limit = session_manager.get_daily_limit(user_id)
            await admin_logger.log_generation(
                user_id,
                update.effective_user.username,
                update.effective_user.first_name,
                mode_config.title,
                prompt,
                photos_count,
                daily_limit
            )

            for idx, url in enumerate(result_urls):
                # Send to user with copyable prompt
                await update.message.reply_photo(
                    photo=url,
                    caption=f"✅ Готово!\n\n<b>Промпт:</b>\n<code>{escape_html(prompt)}</code>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=create_generation_inline_keyboard(image_index=idx),
                )

                # Send result to admin
                await admin_logger.send_generation_result(
                    user_id,
                    update.effective_user.username,
                    update.effective_user.first_name,
                    url,
                    mode_config.title,
                    prompt
                )

            # Reset images after successful generation
            session_manager.clear_images(user_id)
            session_manager.set_pending_prompt(user_id, None)

        else:
            await processing_msg.edit_text("⚠️ Не удалось получить результат от API.")

    except NanoBananaAPIError as error:
        _logger.error(f"Generation failed for user {user_id}: {error}")
        await processing_msg.edit_text(
            f"Ошибка генерации:\n\n<code>{escape_html(str(error))}</code>\n\n"
            f"Попробуйте еще раз или обратитесь к @{ADMIN_CONTACT_USERNAME}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as error:
        _logger.error(f"Unexpected error during generation for user {user_id}: {error}", exc_info=True)
        await processing_msg.edit_text(
            f"⚠️ Произошла неожиданная ошибка.\n\nОбратитесь к @{ADMIN_CONTACT_USERNAME}",
            parse_mode=ParseMode.HTML,
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Image role selection
    if data.startswith("role:"):
        parts = data.split(":")
        image_index = int(parts[1])
        role = parts[2]  # "source" or "reference"

        session_manager.set_image_role(user_id, image_index, role)

        role_emoji = "🖼️" if role == "source" else "🎨"
        role_name = "Источник" if role == "source" else "Референс"

        await query.edit_message_caption(
            caption=f"{role_emoji} Изображение отмечено как <b>{role_name}</b>",
            parse_mode=ParseMode.HTML,
        )

        # Check if we can proceed
        images = session_manager.get_images(user_id)
        unmarked = [img for img in images if not img.role]

        if not unmarked:
            current_mode = session_manager.get_mode(user_id)
            if current_mode == ModeType.REFERENCE:
                # Check we have at least 2 images and both roles
                source_images = [img for img in images if img.role == "source"]
                reference_images = [img for img in images if img.role == "reference"]

                if len(images) < 2:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="📸 Загрузите ещё одно изображение.\n\n<i>Для режима Референс нужно минимум 2 изображения (Источник и Референс)</i>",
                        parse_mode=ParseMode.HTML,
                    )
                elif not source_images:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🖼️ Отметьте хотя бы одно изображение как <b>Источник</b> (основное).",
                        parse_mode=ParseMode.HTML,
                    )
                elif not reference_images:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎨 Отметьте хотя бы одно изображение как <b>Референс</b> (стиль).",
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    # All good, can proceed - set empty prompt to allow direct generation
                    session_manager.set_pending_prompt(user_id, "Apply style from reference to source image")

                    await context.bot.send_message(
                        chat_id=user_id,
                        text="✅ Всё готово к генерации!\n\n<i>Можете сразу запустить или добавить дополнительные инструкции:</i>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=create_confirm_generation_inline_keyboard(),
                    )

    # Delete image
    elif data.startswith("delete_image:"):
        image_index = int(data.split(":")[1])
        images = session_manager.get_images(user_id)

        if 0 <= image_index < len(images):
            images.pop(image_index)
            await query.edit_message_caption(
                caption="❌ Изображение удалено",
                parse_mode=ParseMode.HTML,
            )

    # Settings: aspect ratio
    elif data.startswith("settings:aspect"):
        current_ratio = session_manager.get_aspect_ratio(user_id)
        await query.edit_message_text(
            "📐 Выберите соотношение сторон:",
            reply_markup=create_aspect_ratio_inline_keyboard(current_ratio),
        )

    # Settings: format
    elif data.startswith("settings:format"):
        current_format = session_manager.get_output_format(user_id)
        await query.edit_message_text(
            "📄 Выберите формат файла:",
            reply_markup=create_format_inline_keyboard(current_format),
        )

    # Aspect ratio selection
    elif data.startswith("aspect:"):
        ratio = data.split(":")[1]

        if ratio == "done":
            current_ratio = session_manager.get_aspect_ratio(user_id)
            await query.edit_message_text(
                f"✅ Соотношение сторон: {current_ratio}",
                parse_mode=ParseMode.HTML,
            )
        else:
            session_manager.set_aspect_ratio(user_id, ratio)
            await query.edit_message_reply_markup(
                reply_markup=create_aspect_ratio_inline_keyboard(ratio)
            )

    # Format selection
    elif data.startswith("format:"):
        fmt = data.split(":")[1]

        if fmt == "done":
            current_format = session_manager.get_output_format(user_id)
            await query.edit_message_text(
                f"✅ Формат файла: {current_format.upper()}",
                parse_mode=ParseMode.HTML,
            )
        else:
            session_manager.set_output_format(user_id, fmt)
            await query.edit_message_reply_markup(
                reply_markup=create_format_inline_keyboard(fmt)
            )

    # Confirm generation
    elif data.startswith("confirm:"):
        action = data.split(":")[1]

        if action == "generate":
            # Check if user can generate (has quota left)
            if not session_manager.can_generate(user_id):
                photos_count = session_manager.get_photos_count(user_id)
                daily_limit = session_manager.get_daily_limit(user_id)

                await admin_logger.log_limit_reached(
                    user_id,
                    query.from_user.username,
                    query.from_user.first_name,
                    False
                )

                from config import ADMIN_CONTACT_USERNAME
                contact = ADMIN_CONTACT_USERNAME
                await query.edit_message_text(
                    f"❌ <b>Лимит исчерпан</b>\n\n"
                    f"Сегодня вы сгенерировали {photos_count}/{daily_limit} фото.\n\n"
                    f"💳 <b>Подписки</b>\n\n"
                    f"<blockquote>• <b>banana+</b> — 15 фото/день (150 ₽/мес)\n"
                    f"• <b>banana.ultra</b> — 40 фото/день (300 ₽/мес)</blockquote>\n\n"
                    f"Чтобы оформить, напишите @{contact}.",
                    parse_mode=ParseMode.HTML,
                )
                await query.edit_message_reply_markup(create_subscription_inline_keyboard())
                return

            prompt = session_manager.get_pending_prompt(user_id)
            if prompt:
                await query.edit_message_text("🚀 Запускаю генерацию...")
                # Call generation directly without creating fake update
                # user_id is already correct from query.from_user.id
                current_mode = session_manager.get_mode(user_id)
                aspect_ratio = session_manager.get_aspect_ratio(user_id)
                output_format = session_manager.get_output_format(user_id)

                _logger.info(f"confirm:generate: user={user_id}, mode={current_mode}, prompt={prompt[:50]}")

                # Send initial progress message
                initial_text = create_progress_bar("waiting", 1, 40)
                processing_msg = await query.message.reply_text(
                    initial_text,
                    parse_mode=ParseMode.HTML,
                )

                # Create progress callback with state tracking
                last_progress_text = initial_text
                async def update_progress(state: str, attempt: int, max_attempts: int):
                    """Update progress message with current state"""
                    nonlocal last_progress_text
                    try:
                        new_text = create_progress_bar(state, attempt, max_attempts)
                        _logger.info(f"Progress update: state={state}, attempt={attempt}/{max_attempts}, changed={new_text != last_progress_text}")
                        # Only update if text changed
                        if new_text != last_progress_text:
                            await processing_msg.edit_text(new_text, parse_mode=ParseMode.HTML)
                            last_progress_text = new_text
                    except Exception as e:
                        _logger.warning(f"Failed to update progress: {e}")

                try:
                    if current_mode == ModeType.GENERATE:
                        # Text-to-image generation
                        result_urls = await nano_banana_client.generate_image(
                            prompt=prompt,
                            output_format=output_format,
                            image_size=aspect_ratio,
                            progress_callback=update_progress,
                        )

                    elif current_mode == ModeType.EDIT:
                        # Image editing
                        images = session_manager.get_images(user_id)
                        if not images:
                            await processing_msg.edit_text("Нет загруженных изображений для редактирования.")
                            return

                        image_urls = [img.file_url for img in images]
                        _logger.info(f"EDIT mode: user={user_id}, images_count={len(images)}, urls={image_urls}")
                        result_urls = await nano_banana_client.edit_image(
                            prompt=prompt,
                            image_urls=image_urls,
                            output_format=output_format,
                            image_size=aspect_ratio,
                            progress_callback=update_progress,
                        )

                    elif current_mode == ModeType.REFERENCE:
                        # Style transfer from reference
                        images = session_manager.get_images(user_id)
                        source_images = session_manager.get_images_by_role(user_id, "source")
                        reference_images = session_manager.get_images_by_role(user_id, "reference")

                        if not source_images or not reference_images:
                            await processing_msg.edit_text(
                                "Нужно хотя бы одно Источник изображение и одно Референс изображение."
                            )
                            return

                        # Build structured prompt
                        structured_prompt = (
                            f"[SOURCE_IMAGE]: The main image to transform\n"
                            f"[REFERENCE_IMAGE]: Apply the style, color palette, and mood from this image\n\n"
                            f"{prompt if prompt else 'Apply the style from reference to source image.'}"
                        )

                        # Combine all image URLs (source first, then reference)
                        all_image_urls = [img.file_url for img in source_images] + [img.file_url for img in reference_images]

                        result_urls = await nano_banana_client.edit_image(
                            prompt=structured_prompt,
                            image_urls=all_image_urls,
                            output_format=output_format,
                            image_size=aspect_ratio,
                            progress_callback=update_progress,
                        )

                    else:
                        await processing_msg.edit_text("Неизвестный режим.")
                        return

                    # Send result
                    if result_urls:
                        await processing_msg.delete()

                        # Store result URLs for full quality download
                        session_manager.set_last_result_urls(user_id, result_urls)
                        # Store complete generation state for regeneration (before clearing images)
                        current_images = session_manager.get_images(user_id)
                        session_manager.save_generation_state(user_id, prompt, current_mode, current_images)
                        # Increment photo counter
                        session_manager.increment_photos_count(user_id)

                        # Log generation to admin
                        mode_config = MODE_CATALOG[current_mode]
                        photos_count = session_manager.get_photos_count(user_id)
                        daily_limit = session_manager.get_daily_limit(user_id)
                        await admin_logger.log_generation(
                            user_id,
                            query.from_user.username,
                            query.from_user.first_name,
                            mode_config.title,
                            prompt,
                            photos_count,
                            daily_limit
                        )

                        for idx, url in enumerate(result_urls):
                            # Send to user with copyable prompt
                            await query.message.reply_photo(
                                photo=url,
                                caption=f"✅ Готово!\n\n<b>Промпт:</b>\n<code>{escape_html(prompt)}</code>",
                                parse_mode=ParseMode.HTML,
                                reply_markup=create_generation_inline_keyboard(image_index=idx),
                            )

                            # Send result to admin
                            await admin_logger.send_generation_result(
                                user_id,
                                query.from_user.username,
                                query.from_user.first_name,
                                url,
                                mode_config.title,
                                prompt
                            )

                        # Reset images after successful generation
                        session_manager.clear_images(user_id)
                        session_manager.set_pending_prompt(user_id, None)

                    else:
                        await processing_msg.edit_text("⚠️ Не удалось получить результат от API.")

                except NanoBananaAPIError as error:
                    _logger.error(f"Generation failed for user {user_id}: {error}")
                    await processing_msg.edit_text(
                        f"Ошибка генерации:\n\n<code>{escape_html(str(error))}</code>\n\n"
                        f"Попробуйте еще раз или обратитесь к @{ADMIN_CONTACT_USERNAME}",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as error:
                    _logger.error(f"Unexpected error during generation for user {user_id}: {error}", exc_info=True)
                    await processing_msg.edit_text(
                        f"⚠️ Произошла неожиданная ошибка.\n\nОбратитесь к @{ADMIN_CONTACT_USERNAME}",
                        parse_mode=ParseMode.HTML,
                    )
            else:
                await query.edit_message_text("⚠️ Промпт не найден.")
        elif action == "cancel":
            session_manager.set_pending_prompt(user_id, None)
            await query.edit_message_text("❌ Генерация отменена.")

    # Full quality download
    elif data.startswith("full_quality:"):
        image_index = int(data.split(":")[1])
        result_urls = session_manager.get_last_result_urls(user_id)

        if not result_urls or image_index >= len(result_urls):
            await query.answer("⚠️ Изображение не найдено. Попробуйте сгенерировать заново.", show_alert=True)
            return

        image_url = result_urls[image_index]

        try:
            # Download image
            import aiohttp
            from datetime import datetime as dt
            import io
            from pathlib import Path

            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        await query.answer("⚠️ Не удалось загрузить изображение.", show_alert=True)
                        return

                    image_bytes = await response.read()

            # Generate unique filename: "banana {date} {number}.ext"
            date_str = dt.now().strftime("%Y-%m-%d")
            import random
            random_num = random.randint(1000, 9999)

            # Determine extension from URL or content type
            ext = "png"
            if image_url.endswith(".jpg") or image_url.endswith(".jpeg"):
                ext = "jpg"

            filename = f"banana {date_str} {random_num}.{ext}"

            # Send as document
            await query.answer("📥 Отправляю в полном качестве...")
            await query.message.reply_document(
                document=io.BytesIO(image_bytes),
                filename=filename,
                caption="📥 Изображение в полном качестве"
            )

        except Exception as e:
            _logger.error(f"Failed to send full quality image: {e}")
            await query.answer("⚠️ Ошибка при загрузке изображения.", show_alert=True)

    # Regenerate
    elif data == "regenerate":
        # Get last prompt and mode
        last_prompt = session_manager.get_last_prompt(user_id)
        last_mode = session_manager.get_last_mode(user_id)

        if not last_prompt or not last_mode:
            await query.answer("❌ Не найдена информация о последней генерации", show_alert=True)
            return

        # Restore generation state (images and mode)
        session_manager.restore_generation_state(user_id)
        session_manager.set_mode(user_id, last_mode)

        # Set as pending prompt and show confirmation
        session_manager.set_pending_prompt(user_id, last_prompt)

        # Build preview message
        mode_config = MODE_CATALOG[last_mode]
        aspect_ratio = session_manager.get_aspect_ratio(user_id)
        output_format = session_manager.get_output_format(user_id)

        # Show how many images are being used (for EDIT/REFERENCE modes)
        images_info = ""
        if last_mode in [ModeType.EDIT, ModeType.REFERENCE]:
            image_count = session_manager.get_image_count(user_id)
            images_info = f"<b>Изображений:</b> {image_count}\n"

        preview_text = f"🔄 <b>Повторная генерация</b>\n\n"
        preview_text += f"<b>Режим:</b> {mode_config.emoji} {mode_config.title}\n"
        preview_text += images_info
        preview_text += f"<b>Промпт:</b>\n<blockquote>{escape_html(last_prompt)}</blockquote>\n\n"
        preview_text += f"<b>Настройки:</b>\n"
        preview_text += f"📐 Соотношение: {aspect_ratio}\n"
        preview_text += f"📄 Формат: {output_format.upper()}\n\n"
        preview_text += "⚠️ Подтвердите повторную генерацию:"

        await query.message.reply_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_confirm_generation_inline_keyboard(),
        )

    # Settings (from result)
    elif data == "settings":
        await settings_command_from_callback(query, context)

    # Subscription purchase
    elif data.startswith("subscribe:"):
        tier = data.split(":")[1]
        import uuid
        request_id = uuid.uuid4().hex
        cost = "150 ₽" if tier == "plus" else "300 ₽"
        from config import ADMIN_USER_ID
        username = query.from_user.username
        first_name = query.from_user.first_name
        _logger.info(f"subscribe: user={user_id}, tier={tier}, request_id={request_id}")
        tier_text = "banana.ultra" if tier == "ultra" else "banana+"
        admin_text = (
            f"💳 Заявка на подписку {tier_text}\n\n"
            f"Пользователь: {first_name or '.'}\n"
            + (f"Username: @{username}\n" if username else "Username: —\n")
            + f"Telegram ID: {user_id}\n"
            + f"Стоимость: {cost}"
        )
        try:
            admin_logger.store_subscription_request(
                user_id,
                tier,
                cost,
                request_id,
                username,
                first_name,
            )
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_text,
                parse_mode=ParseMode.HTML,
                reply_markup=create_admin_subscription_request_keyboard(user_id, tier, request_id, username),
            )
            _logger.info(f"subscribe: admin_notified user={user_id} tier={tier}")
        except Exception as e:
            _logger.error(f"subscribe: failed_to_notify_admin user={user_id} tier={tier} error={e}")
        from config import ADMIN_CONTACT_USERNAME
        contact = ADMIN_CONTACT_USERNAME
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ Запрос отправлен администратору. После оплаты он подтвердит и активирует подписку.\n\n"
                    f"Чтобы оформить, напишите @{contact}"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=create_subscription_contact_inline_keyboard(),
            )
            _logger.info(f"subscribe: user_notified user={user_id} tier={tier}")
        except Exception as e:
            _logger.error(f"subscribe: failed_to_notify_user user={user_id} tier={tier} error={e}")

    elif data.startswith("admin:"):
        from config import ADMIN_USER_ID, USE_FAKE_STATS, TIMEZONE
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("⚠️ Доступ запрещён", parse_mode=ParseMode.HTML)
            return
        action = data.split(":")[1]
        if action == "sub_confirm" or action == "sc":
            parts = data.split(":")
            if len(parts) >= 4:
                target_user_id = int(parts[2])
                tier_code = parts[3]
                tier = "ultra" if tier_code in ("ultra", "u") else "plus"
                current_sub = db.get_subscription(target_user_id)
                if current_sub == tier:
                    await query.edit_message_text(
                        "ℹ️ У пользователя уже активна эта подписка. Повторное подтверждение не требуется.",
                        parse_mode=ParseMode.HTML,
                    )
                    return
                if current_sub == "ultra" and tier == "plus":
                    await query.edit_message_text(
                        "ℹ️ У пользователя уже активна подписка выше уровня (banana.ultra). Понижение не выполняется.",
                        parse_mode=ParseMode.HTML,
                    )
                    return
                db.set_subscription(target_user_id, "ultra" if tier == "ultra" else "plus")
                new_exp = db.add_subscription_days(target_user_id, 30)
                try:
                    limit = db.get_daily_limit(target_user_id)
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=(
                            "✅ <b>Подписка активирована</b>\n\n"
                            + ("Тариф: <b>banana.ultra</b> — 40 фото/день" if tier == "ultra" else "Тариф: <b>banana+</b> — 15 фото/день")
                            + "\nОплата подтверждена администратором."
                            + (f"\nОплачено до: {new_exp}" if new_exp else "")
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                await query.edit_message_text(
                    ("✅ Оплата подтверждена. Активирован тариф banana.ultra. Пользователь уведомлен." if tier == "ultra" else "✅ Оплата подтверждена. Активирован тариф banana+. Пользователь уведомлен."),
                    parse_mode=ParseMode.HTML,
                )
                return
        if action == "stats":
            if USE_FAKE_STATS:
                total_users = 120
                photos_today = 78
                tz = ZoneInfo(TIMEZONE)
                from datetime import datetime as _dt
                today = _dt.now(tz).date()
                counts = [78, 64, 71, 83, 59, 90, 76]
                stats_pairs = [((today - timedelta(days=i)).isoformat(), counts[i]) for i in range(len(counts))]
                lines = [f"{d}: {c}" for d, c in stats_pairs]
            else:
                total_users = db.get_total_users()
                photos_today = db.get_total_photos_today()
                stats = db.get_daily_stats(7)
                lines = [f"{d}: {c}" for d, c in stats]
            stats_text = (
                f"📊 <b>Статистика</b>\n\n"
                f"👥 Пользователей: {total_users}\n"
                f"📸 Фото сегодня: {photos_today}\n\n"
                f"За последние 7 дней:\n" + ("\n".join(lines) if lines else "Нет данных")
            )
            await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML)
        elif action == "broadcast":
            session_manager.set_broadcast_mode(user_id, "real")
            session_manager.set_broadcast_audience(user_id, "all")
            session_manager.set_pending_broadcast_text(user_id, None)
            session_manager.set_pending_broadcast_photo(user_id, None, None)
            await query.edit_message_text("📣 Режим рассылки", parse_mode=ParseMode.HTML, reply_markup=create_broadcast_menu_inline_keyboard())
        elif action == "close":
            await query.edit_message_text("🔙 Закрыто", parse_mode=ParseMode.HTML)
        elif action == "panel":
            await query.edit_message_text("🛠️ Админ панель", parse_mode=ParseMode.HTML, reply_markup=create_admin_panel_inline_keyboard())
        elif action == "search":
            session_manager.set_admin_awaiting_user_id_input(user_id, True)
            await query.edit_message_text("🔎 Введите TG ID пользователя", parse_mode=ParseMode.HTML)
        elif action == "u":
            parts = data.split(":")
            if len(parts) < 4:
                await query.answer("Ошибка", show_alert=True)
                return
            code = parts[2]
            target_user_id = int(parts[3])
            if code == "del":
                db.delete_user(target_user_id)
                await query.edit_message_text("🗑 Пользователь удалён", parse_mode=ParseMode.HTML)
            elif code == "cc":
                db.cancel_subscription(target_user_id)
                await query.edit_message_text("⛔️ Подписка отменена", parse_mode=ParseMode.HTML)
            elif code == "add":
                session_manager.set_admin_awaiting_add_days_input(user_id, True)
                session_manager.set_admin_add_days_target_user_id(user_id, target_user_id)
                await query.edit_message_text("➕ Введите количество дней для продления", parse_mode=ParseMode.HTML)
            elif code == "st":
                if len(parts) < 5:
                    await query.answer("Ошибка", show_alert=True)
                    return
                tier_code = parts[4]
                tier = "ultra" if tier_code == "u" else "plus"
                db.set_subscription(target_user_id, tier)
                info = _format_user_card_text(target_user_id)
                from utils import create_admin_user_actions_keyboard
                await query.edit_message_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_user_id))
            elif code == "set":
                from utils import create_admin_set_type_keyboard
                await query.edit_message_text("🔁 Выберите тип подписки", parse_mode=ParseMode.HTML, reply_markup=create_admin_set_type_keyboard(target_user_id))
            elif code == "back":
                info = _format_user_card_text(target_user_id)
                from utils import create_admin_user_actions_keyboard
                await query.edit_message_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_user_id))
            elif code == "refresh":
                info = _format_user_card_text(target_user_id)
                from utils import create_admin_user_actions_keyboard
                await query.edit_message_text(info, parse_mode=ParseMode.HTML, reply_markup=create_admin_user_actions_keyboard(target_user_id))

    elif data.startswith("broadcast:"):
        action = data.split(":")[1]
        from config import ADMIN_USER_ID
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("⚠️ Доступ запрещён", parse_mode=ParseMode.HTML)
            return
        if action == "audience":
            audience = data.split(":")[2]
            if audience not in ("all", "test"):
                audience = "all"
            session_manager.set_broadcast_audience(user_id, audience)
            session_manager.set_broadcast_awaiting(user_id, True)
            await query.edit_message_text("✍️ Отправьте текст для рассылки", parse_mode=ParseMode.HTML)
            return
        if action == "add_photo":
            session_manager.set_broadcast_photo_awaiting(user_id, True)
            await query.edit_message_text("🖼️ Отправьте фото с подписью (опционально)", parse_mode=ParseMode.HTML)
            return
        if action == "skip_photo":
            await query.edit_message_text(
                "❌ Фото не будет добавлено. Нажмите ‘Далее к превью’.",
                parse_mode=ParseMode.HTML,
                reply_markup=create_broadcast_photo_step_keyboard(),
            )
            return
        if action == "preview":
            text = session_manager.get_pending_broadcast_text(user_id) or ""
            file_id, combined_caption = session_manager.get_pending_broadcast_photo(user_id)
            if file_id:
                preview_caption = f"📣 Предпросмотр\n\n{combined_caption}" if combined_caption else "📣 Предпросмотр"
                await query.message.reply_photo(
                    photo=file_id,
                    caption=preview_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=create_broadcast_confirm_inline_keyboard(),
                )
            else:
                preview = f"<b>Предпросмотр рассылки</b>\n\n{text}" if text else "<b>Предпросмотр рассылки</b>"
                await query.message.reply_text(
                    preview,
                    parse_mode=ParseMode.HTML,
                    reply_markup=create_broadcast_confirm_inline_keyboard(),
                )
            return
        # Simplified flow: no format selection, no CTA buttons, no advanced preview
        if action == "reset":
            session_manager.set_pending_broadcast_text(user_id, None)
            session_manager.set_pending_broadcast_photo(user_id, None, None)
            session_manager.set_broadcast_mode(user_id, None)
            await query.edit_message_text("🧹 Сброшено", parse_mode=ParseMode.HTML)
            return
        if action == "cancel":
            session_manager.set_pending_broadcast_text(user_id, None)
            session_manager.set_pending_broadcast_photo(user_id, None, None)
            await query.edit_message_text("❌ Рассылка отменена", parse_mode=ParseMode.HTML)
            return
        if action == "send":
            import asyncio
            text = session_manager.get_pending_broadcast_text(user_id)
            file_id, caption = session_manager.get_pending_broadcast_photo(user_id)
            if not text and not file_id:
                try:
                    await query.edit_message_text("⚠️ Нечего отправлять", parse_mode=ParseMode.HTML)
                except Exception:
                    await context.bot.send_message(chat_id=user_id, text="⚠️ Нечего отправлять", parse_mode=ParseMode.HTML)
                return
            try:
                if getattr(query.message, "photo", None):
                    await query.message.edit_caption("📤 Запускаю рассылку...", parse_mode=ParseMode.HTML)
                else:
                    await query.edit_message_text("📤 Запускаю рассылку...", parse_mode=ParseMode.HTML)
            except Exception:
                await context.bot.send_message(chat_id=user_id, text="📤 Запускаю рассылку...", parse_mode=ParseMode.HTML)
            audience = session_manager.get_broadcast_audience(user_id) or "all"
            if audience == "test":
                from config import TEST_USER_IDS
                user_ids = TEST_USER_IDS
            else:
                user_ids = db.get_all_user_ids()
            sent = 0
            failed = 0
            for uid in user_ids:
                if uid == ADMIN_USER_ID:
                    continue
                try:
                    if file_id:
                        # If a photo exists, send it with combined caption (pending text + photo caption)
                        final_caption = caption or ""
                        if not final_caption and text:
                            final_caption = text
                        await context.bot.send_photo(chat_id=uid, photo=file_id, caption=(final_caption or None), parse_mode=ParseMode.HTML)
                    else:
                        # No photo, send text message
                        await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.02)
            session_manager.set_pending_broadcast_text(user_id, None)
            session_manager.set_pending_broadcast_photo(user_id, None, None)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Рассылка завершена\n\nОтправлено: {sent}\nОшибок: {failed}",
                parse_mode=ParseMode.HTML,
            )
            return
        if action == "test":
            import asyncio
            from config import TEST_USER_IDS
            text = session_manager.get_pending_broadcast_text(user_id)
            file_id, caption = session_manager.get_pending_broadcast_photo(user_id)
            if not text and not file_id:
                try:
                    await query.edit_message_text("⚠️ Нечего отправлять", parse_mode=ParseMode.HTML)
                except Exception:
                    await context.bot.send_message(chat_id=user_id, text="⚠️ Нечего отправлять", parse_mode=ParseMode.HTML)
                return
            try:
                if getattr(query.message, "photo", None):
                    await query.message.edit_caption("🧪 Тестовая рассылка...", parse_mode=ParseMode.HTML)
                else:
                    await query.edit_message_text("🧪 Тестовая рассылка...", parse_mode=ParseMode.HTML)
            except Exception:
                await context.bot.send_message(chat_id=user_id, text="🧪 Тестовая рассылка...", parse_mode=ParseMode.HTML)
            sent = 0
            failed = 0
            for uid in TEST_USER_IDS:
                try:
                    if file_id:
                        final_caption = caption or ""
                        if not final_caption and text:
                            final_caption = text
                        await context.bot.send_photo(chat_id=uid, photo=file_id, caption=(final_caption or None), parse_mode=ParseMode.HTML)
                    else:
                        await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.02)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Тест завершён\n\nОтправлено: {sent}\nОшибок: {failed}",
                parse_mode=ParseMode.HTML,
            )
            return


async def settings_command_from_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings command from callback"""
    user_id = query.from_user.id
    current_format = session_manager.get_output_format(user_id)
    current_ratio = session_manager.get_aspect_ratio(user_id)

    settings_text = f"""⚙️ <b>Настройки</b>

<b>Текущие параметры:</b>
📄 Формат: {current_format.upper()}
📐 Соотношение сторон: {current_ratio}

Выберите что хотите изменить:"""

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📐 Соотношение сторон", callback_data="settings:aspect"),
            InlineKeyboardButton("📄 Формат файла", callback_data="settings:format"),
        ],
    ])

    await query.message.reply_text(
        settings_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
