from datetime import datetime, timedelta
from random import choice
from typing import Dict, List, Tuple

from config import (
    logger,
    AGGRESSIVE_TEMPLATES,
    SNOOZE_OPTIONS_MINUTES,
    REMINDER_ATTEMPT_DELAYS_MINUTES,
)
from services.database import db
from zoneinfo import ZoneInfo

from services.time_service import normalize_datetime, storage_to_local


class ReminderService:
    """Business logic around reminders: formatting, status handling, snooze helpers."""

    def format_confirmation(self, reminder_data: Dict[str, str], tz: ZoneInfo) -> str:
        normalized = None
        dt_raw = reminder_data.get("datetime")
        dt_human = reminder_data.get("datetime_human")

        if dt_raw:
            try:
                normalized = normalize_datetime(dt_raw, tz)
            except Exception:
                normalized = None

        lines = [
            "Записал, чем тебя мучить:",
            f"• ДЕЛО: {reminder_data.get('task', 'нихрена непонятно')}",
        ]

        if normalized:
            lines.append(f"• КОГДА: {normalized.human}")
            reminder_data["datetime"] = normalized.local.isoformat()
            reminder_data["datetime_human"] = normalized.human
        elif dt_human:
            lines.append(f"• КОГДА: {dt_human}")
        else:
            lines.append("• КОГДА: скажи уже время, не тупи")

        return "\n".join(lines)

    def create_reminder(self, telegram_id: int, reminder_data: Dict[str, str], tz: ZoneInfo) -> int:
        normalized = normalize_datetime(reminder_data["datetime"], tz)
        reminder_id = db.create_reminder(
            telegram_id=telegram_id,
            task=reminder_data["task"],
            scheduled_time=normalized.storage_iso,
            original_time=normalized.local.isoformat(),
        )
        db.clear_temp_reminder(telegram_id)
        db.clear_conversation_history(telegram_id)
        return reminder_id

    def render_aggressive_message(self, task: str, attempt: int) -> str:
        template = choice(AGGRESSIVE_TEMPLATES)
        base_message = template.format(task=task.upper())

        extras = [
            "ПОКА ТЫ ЖЕВАЛ СЛЮНИ, ВРЕМЯ ТИКАЛО!",
            "ХВАТИТ ПЫЛЬ СОБИРАТЬ — ВПЕРЁД!",
            "ПОДОРВАЛСЯ И УЛЕТЕЛ ДЕЛАТЬ!",
            "НЕ ЗАБУДЬ: ЛОХИ СДАЮТСЯ, А ТЫ?",
        ]

        if attempt > 0:
            base_message = f"{base_message} {choice(extras)}"

        return base_message

    def get_snooze_options(self) -> List[Tuple[str, int]]:
        mapping = {
            5: "+5 минут",
            15: "+15 минут",
            30: "+30 минут",
            60: "+1 час",
        }
        return [(mapping[m], m) for m in SNOOZE_OPTIONS_MINUTES]

    def calculate_next_attempt_time(self, scheduled_time: datetime, attempt_index: int) -> datetime:
        if attempt_index < len(REMINDER_ATTEMPT_DELAYS_MINUTES):
            delay_minutes = REMINDER_ATTEMPT_DELAYS_MINUTES[attempt_index]
        else:
            delay_minutes = REMINDER_ATTEMPT_DELAYS_MINUTES[-1]
        return scheduled_time + timedelta(minutes=delay_minutes)

    def get_user_reminders(self, telegram_id: int, tz: ZoneInfo) -> List[Dict[str, str]]:
        reminders = db.get_user_reminders(telegram_id)
        formatted: List[Dict[str, str]] = []
        for reminder in reminders:
            local_dt = storage_to_local(reminder["scheduled_time"], tz)
            formatted.append(
                {
                    "id": str(reminder["id"]),
                    "task": reminder["task"],
                    "scheduled_time": local_dt.local.isoformat(),
                    "scheduled_time_human": local_dt.human,
                    "status": reminder["status"],
                }
            )
        return formatted

    def cancel_reminder(self, reminder_id: int) -> None:
        """Cancel a reminder by setting its status to 'cancelled'."""
        db.update_reminder_status(reminder_id, "cancelled")
        logger.info("Reminder %s cancelled", reminder_id)


reminder_service = ReminderService()
