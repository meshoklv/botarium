"""
Utility functions and keyboard builders
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from modes import MODE_CATALOG, ModeType
from config import ASPECT_RATIOS, ADMIN_CONTACT_USERNAME
from typing import Optional


def create_main_keyboard(current_mode: ModeType, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Create main reply keyboard with mode selection"""
    buttons = []

    # Add mode buttons
    for mode_config in MODE_CATALOG.values():
        label = mode_config.button_label
        if mode_config.code == current_mode:
            label = f"✓ {label}"  # Mark current mode
        buttons.append([KeyboardButton(mode_config.button_label)])

    # Add settings button
    buttons.append([KeyboardButton("⚙️ Настройки")])

    # Admin panel entry
    if is_admin:
        buttons.append([KeyboardButton("🛠️ Админ панель")])

    # Add subscription purchase button for all users
    buttons.append([KeyboardButton("💳 Купить подписку")])

    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def create_mode_keyboard() -> ReplyKeyboardMarkup:
    """Create keyboard for mode selection"""
    buttons = [[KeyboardButton(cfg.button_label)] for cfg in MODE_CATALOG.values()]
    buttons.append([KeyboardButton("◀ Назад")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def create_image_role_inline_keyboard(image_index: int) -> InlineKeyboardMarkup:
    """Create inline keyboard for marking image role (source/reference)"""
    buttons = [
        [
            InlineKeyboardButton("🖼️ Источник (основное)", callback_data=f"role:{image_index}:source"),
            InlineKeyboardButton("🎨 Референс (стиль)", callback_data=f"role:{image_index}:reference"),
        ],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_image:{image_index}")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_aspect_ratio_inline_keyboard(current_ratio: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for aspect ratio selection"""
    buttons = []
    row = []

    for ratio_code, ratio_label in ASPECT_RATIOS.items():
        # Mark current selection
        label = f"✓ {ratio_code}" if ratio_code == current_ratio else ratio_code
        row.append(InlineKeyboardButton(label, callback_data=f"aspect:{ratio_code}"))

        # 3 buttons per row
        if len(row) == 3:
            buttons.append(row)
            row = []

    # Add remaining buttons
    if row:
        buttons.append(row)

    # Add close button
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="aspect:done")])

    return InlineKeyboardMarkup(buttons)


def create_format_inline_keyboard(current_format: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for output format selection"""
    buttons = [
        [
            InlineKeyboardButton(
                "✓ PNG" if current_format == "png" else "PNG",
                callback_data="format:png"
            ),
            InlineKeyboardButton(
                "✓ JPEG" if current_format == "jpeg" else "JPEG",
                callback_data="format:jpeg"
            ),
        ],
        [InlineKeyboardButton("✅ Готово", callback_data="format:done")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_generation_inline_keyboard(image_index: int = 0) -> InlineKeyboardMarkup:
    """Create inline keyboard shown after generation"""
    buttons = [
        [InlineKeyboardButton("📥 Полное качество", callback_data=f"full_quality:{image_index}")],
        [InlineKeyboardButton("🔄 Ещё раз", callback_data="regenerate")],
        [InlineKeyboardButton("⚙️ Изменить настройки", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_confirm_generation_inline_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard for confirming generation"""
    buttons = [
        [
            InlineKeyboardButton("✅ Сгенерировать", callback_data="confirm:generate"),
            InlineKeyboardButton("❌ Отменить", callback_data="confirm:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def create_broadcast_confirm_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🧪 Тест", callback_data="broadcast:test")],
        [InlineKeyboardButton("📤 Отправить", callback_data="broadcast:send"), InlineKeyboardButton("❌ Отменить", callback_data="broadcast:cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_admin_panel_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton("🔎 Поиск пользователя", callback_data="admin:search")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton("🔙 Закрыть", callback_data="admin:close")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_broadcast_menu_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("👥 Всем", callback_data="broadcast:audience:all"), InlineKeyboardButton("🧪 Тестовым", callback_data="broadcast:audience:test")],
        [InlineKeyboardButton("🧹 Сброс", callback_data="broadcast:reset")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin:close")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_admin_user_actions_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"admin:u:del:{target_user_id}")],
        [InlineKeyboardButton("⛔️ Отменить подписку", callback_data=f"admin:u:cc:{target_user_id}")],
        [InlineKeyboardButton("➕ Добавить дней", callback_data=f"admin:u:add:{target_user_id}")],
        [InlineKeyboardButton("🔁 Сменить тип подписки", callback_data=f"admin:u:set:{target_user_id}")],
        [InlineKeyboardButton("🔄 Обновить карточку", callback_data=f"admin:u:refresh:{target_user_id}")],
        [InlineKeyboardButton("🏠 В панель", callback_data="admin:panel")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_admin_set_type_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("banana+", callback_data=f"admin:u:st:{target_user_id}:p"),
            InlineKeyboardButton("banana.ultra", callback_data=f"admin:u:st:{target_user_id}:u"),
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"admin:u:back:{target_user_id}")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_broadcast_photo_step_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📸 Добавить фото", callback_data="broadcast:add_photo")],
        [InlineKeyboardButton("❌ Нет, без фото", callback_data="broadcast:skip_photo")],
        [InlineKeyboardButton("➡️ Далее к превью", callback_data="broadcast:preview")],
    ]
    return InlineKeyboardMarkup(buttons)


# Removed CTA actions keyboard to keep broadcast flow minimal for banana


def format_image_list(images: list, show_roles: bool = True) -> str:
    """Format list of images for display"""
    if not images:
        return "Нет загруженных изображений"

    lines = []
    for idx, img in enumerate(images, 1):
        role_text = ""
        if show_roles and img.role:
            role_emoji = "🖼️" if img.role == "source" else "🎨"
            role_name = "Источник" if img.role == "source" else "Референс"
            role_text = f" [{role_emoji} {role_name}]"

        lines.append(f"{idx}. Изображение{role_text}")

    return "\n".join(lines)


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def create_subscription_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("купить banana+", callback_data="subscribe:plus"),
            InlineKeyboardButton("купить banana.ultra", callback_data="subscribe:ultra"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def create_subscription_contact_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("оформить подписку", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")]]
    return InlineKeyboardMarkup(buttons)


def create_admin_subscription_request_keyboard(user_id: int, tier: str, request_id: str, username: Optional[str]) -> InlineKeyboardMarkup:
    """Create inline keyboard for admin to confirm payment or contact user"""
    # Prefer username link if available, otherwise deep link by user_id
    if username:
        contact_url = f"https://t.me/{username}"
    else:
        contact_url = f"tg://user?id={user_id}"

    # Use short callback to fit Telegram's 64 byte limit
    short_tier = "u" if tier == "ultra" else "p"
    buttons = [
        [
            InlineKeyboardButton("✅ подтвердить оплату", callback_data=f"admin:sc:{user_id}:{short_tier}"),
            InlineKeyboardButton("✉️ написать пользователю", url=contact_url),
        ]
    ]
    return InlineKeyboardMarkup(buttons)
