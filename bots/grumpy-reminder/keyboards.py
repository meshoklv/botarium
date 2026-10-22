from typing import List, Tuple

from telegram import (
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

from services.reminder_service import reminder_service


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [["❌ Отменить"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm:yes"),
            InlineKeyboardButton("✏️ Изменить", callback_data="confirm:edit"),
        ],
        [InlineKeyboardButton("❌ Отменить", callback_data="confirm:cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["➕ Новое напоминание"],
        ["⏰ Мои напоминания", "ℹ️ Помощь"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_reminder_action_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✅ Сделал", callback_data=f"reminder_done:{reminder_id}"),
            InlineKeyboardButton("⏰ Отложить", callback_data=f"reminder_snooze:{reminder_id}"),
        ],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"reminder_cancel:{reminder_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_snooze_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    options: List[Tuple[str, int]] = reminder_service.get_snooze_options()
    keyboard: List[List[InlineKeyboardButton]] = []

    for label, minutes in options:
        keyboard.append(
            [InlineKeyboardButton(label, callback_data=f"snooze:{reminder_id}:{minutes}")]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"snooze_back:{reminder_id}")])
    return InlineKeyboardMarkup(keyboard)


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

