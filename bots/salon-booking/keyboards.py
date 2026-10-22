from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from config import SERVICES, MASTERS
from typing import List


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main menu keyboard"""
    keyboard = [
        ["📅 Записаться"],
        ["📋 Мои записи", "ℹ️ Помощь"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancel keyboard"""
    keyboard = [
        ["❌ Отменить"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_services_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard with services"""
    keyboard = []

    for service in SERVICES:
        keyboard.append([InlineKeyboardButton(
            f"{service['name']} - {service['price']}₽",
            callback_data=f"service:{service['id']}"
        )])

    return InlineKeyboardMarkup(keyboard)


def get_masters_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard with masters"""
    keyboard = []

    for master in MASTERS:
        keyboard.append([InlineKeyboardButton(
            master['name'],
            callback_data=f"master:{master['id']}"
        )])

    # Add "any master" option
    keyboard.append([InlineKeyboardButton(
        "Любой свободный мастер",
        callback_data="master:any"
    )])

    return InlineKeyboardMarkup(keyboard)


def get_date_inline_keyboard(dates: List[str]) -> InlineKeyboardMarkup:
    """Inline keyboard with dates"""
    keyboard = []

    # Add dates in rows of 2
    for i in range(0, len(dates), 2):
        row = []
        row.append(InlineKeyboardButton(dates[i], callback_data=f"date:{dates[i]}"))
        if i + 1 < len(dates):
            row.append(InlineKeyboardButton(dates[i + 1], callback_data=f"date:{dates[i + 1]}"))
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def get_time_slots_inline_keyboard(slots: List[str]) -> InlineKeyboardMarkup:
    """Inline keyboard with time slots"""
    keyboard = []

    # Add slots in rows of 3
    for i in range(0, len(slots), 3):
        row = []
        for j in range(3):
            if i + j < len(slots):
                row.append(InlineKeyboardButton(slots[i + j], callback_data=f"time:{slots[i + j]}"))
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm:yes"),
            InlineKeyboardButton("✏️ Изменить", callback_data="confirm:edit")
        ],
        [
            InlineKeyboardButton("❌ Отменить", callback_data="confirm:cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def remove_keyboard() -> ReplyKeyboardRemove:
    """Remove keyboard"""
    return ReplyKeyboardRemove()
