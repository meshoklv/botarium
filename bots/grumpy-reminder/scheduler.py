from datetime import datetime, timedelta
from typing import Dict
import asyncio
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    logger,
    REMINDER_ATTEMPT_DELAYS_MINUTES,
    UTC,
    ESCALATION_TIMINGS,
    ESCALATION_LEVEL_1_PHRASES,
    ESCALATION_LEVEL_2_PHRASES,
    ESCALATION_LEVEL_3_SPAM,
    SPAM_LEVEL_3_COUNT,
    SPAM_LEVEL_3_DELAY,
    OFFENDED_DURATION_MINUTES,
    FORGIVENESS_PHRASES,
)
from keyboards import get_reminder_action_keyboard
from services.database import db
from services.reminder_service import reminder_service
from services.ai_service import ai_service
from services.time_service import now_utc, resolve_timezone


class ReminderScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self._tick, "interval", seconds=30)

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Reminder scheduler started")

    async def _tick(self):
        now = now_utc()
        reminders = db.get_pending_and_waiting_reminders()

        for reminder in reminders:
            try:
                await self._process_reminder(reminder, now)
            except Exception as exc:
                logger.error("Failed to process reminder %s: %s", reminder.get("id"), exc)

        # Check for forgiveness
        await self._check_forgiveness(now)

    async def _process_reminder(self, reminder: Dict, now: datetime):
        scheduled_time = datetime.fromisoformat(reminder["scheduled_time"].replace("Z", "+00:00"))
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=UTC)
        scheduled_time = scheduled_time.astimezone(UTC)
        attempts = reminder.get("attempts", 0)
        last_attempt_at = reminder.get("last_attempt_at")
        reminder_id = reminder["id"]
        telegram_id = reminder["telegram_id"]
        tz_name = db.get_client_timezone(telegram_id)
        zone = resolve_timezone(tz_name)

        if reminder["status"] == "pending" and scheduled_time <= now:
            await self._send_attempt(reminder, attempts, now, telegram_id)
            return

        # Check escalation for sent reminders
        if reminder["status"] == "sent":
            await self._check_escalation(reminder, now, scheduled_time)
            return

        if reminder["status"] == "awaiting_confirmation":
            if attempts >= len(REMINDER_ATTEMPT_DELAYS_MINUTES):
                return

            if not last_attempt_at:
                return

            last_attempt_time = datetime.fromisoformat(last_attempt_at.replace("Z", "+00:00"))
            if last_attempt_time.tzinfo is None:
                last_attempt_time = last_attempt_time.replace(tzinfo=UTC)
            delay_minutes = REMINDER_ATTEMPT_DELAYS_MINUTES[attempts]
            next_attempt_time = last_attempt_time + timedelta(minutes=delay_minutes)

            if now >= next_attempt_time:
                await self._send_attempt(reminder, attempts, now, telegram_id)

            # Also check escalation for awaiting_confirmation
            await self._check_escalation(reminder, now, scheduled_time)

    async def _send_attempt(self, reminder: Dict, attempts: int, now: datetime, telegram_id: int):
        tz_name = db.get_client_timezone(telegram_id)
        message = await ai_service.generate_reminder_alert(reminder["task"], attempts, tz_name)
        if not message:
            message = reminder_service.render_aggressive_message(reminder["task"], attempts)
        markup = get_reminder_action_keyboard(reminder["id"])

        await self.bot.send_message(
            chat_id=telegram_id,
            text=message,
            reply_markup=markup,
        )

        attempt_number = attempts + 1
        timestamp = now.isoformat(timespec="seconds")
        db.record_attempt(reminder["id"], attempt_number, timestamp, attempt_number)
        db.bump_attempt(reminder["id"], attempt_number, timestamp)

        # Set status to sent and record initial escalation time
        if reminder["status"] == "pending":
            db.update_reminder_status(reminder["id"], "sent")
            db.update_escalation_level(reminder["id"], 0, timestamp)

    async def _check_escalation(self, reminder: Dict, now: datetime, scheduled_time: datetime):
        """Check and execute escalation if needed."""
        telegram_id = reminder["telegram_id"]
        escalation_level = reminder.get("escalation_level", 0)
        last_escalation_at = reminder.get("last_escalation_at")

        # Calculate time since first send
        if not last_escalation_at:
            return

        last_esc_time = datetime.fromisoformat(last_escalation_at.replace("Z", "+00:00"))
        if last_esc_time.tzinfo is None:
            last_esc_time = last_esc_time.replace(tzinfo=UTC)

        time_since_sent = (now - last_esc_time).total_seconds() / 60  # in minutes

        # Check each escalation level
        if escalation_level == 0 and time_since_sent >= ESCALATION_TIMINGS[1]:
            await self._send_level_1(reminder, telegram_id, now)
        elif escalation_level == 1 and time_since_sent >= ESCALATION_TIMINGS[2]:
            await self._send_level_2(reminder, telegram_id, now)
        elif escalation_level == 2 and time_since_sent >= ESCALATION_TIMINGS[3]:
            await self._send_level_3_spam(reminder, telegram_id, now)
        elif escalation_level == 3 and time_since_sent >= ESCALATION_TIMINGS[4]:
            await self._send_level_4_llm_roast(reminder, telegram_id, now)
        elif escalation_level == 4 and time_since_sent >= ESCALATION_TIMINGS[5]:
            await self._send_level_5_offended(reminder, telegram_id, now)

    async def _send_level_1(self, reminder: Dict, telegram_id: int, now: datetime):
        """Level 1: Light pressure (+2 min)."""
        message = random.choice(ESCALATION_LEVEL_1_PHRASES)
        await self.bot.send_message(chat_id=telegram_id, text=message)
        db.update_escalation_level(reminder["id"], 1, now.isoformat(timespec="seconds"))
        logger.info("Escalation level 1 sent for reminder %s", reminder["id"])

    async def _send_level_2(self, reminder: Dict, telegram_id: int, now: datetime):
        """Level 2: Medium pressure (+5 min)."""
        message = random.choice(ESCALATION_LEVEL_2_PHRASES)
        await self.bot.send_message(chat_id=telegram_id, text=message)
        db.update_escalation_level(reminder["id"], 2, now.isoformat(timespec="seconds"))
        logger.info("Escalation level 2 sent for reminder %s", reminder["id"])

    async def _send_level_3_spam(self, reminder: Dict, telegram_id: int, now: datetime):
        """Level 3: Spam attack (+10 min)."""
        spam_messages = random.sample(ESCALATION_LEVEL_3_SPAM, min(SPAM_LEVEL_3_COUNT, len(ESCALATION_LEVEL_3_SPAM)))
        for msg in spam_messages:
            await self.bot.send_message(chat_id=telegram_id, text=msg)
            db.increment_spam_count(reminder["id"])
            await asyncio.sleep(SPAM_LEVEL_3_DELAY)
        db.update_escalation_level(reminder["id"], 3, now.isoformat(timespec="seconds"))
        logger.info("Escalation level 3 spam sent for reminder %s", reminder["id"])

    async def _send_level_4_llm_roast(self, reminder: Dict, telegram_id: int, now: datetime):
        """Level 4: LLM-generated roast (+30 min)."""
        # Get user info
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, username FROM clients WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        conn.close()

        first_name = row["first_name"] if row and row["first_name"] else "ДЕБИЛ"
        username = row["username"] if row and row["username"] else "ноунейм"

        roast = await ai_service.generate_ultimate_roast(
            task=reminder["task"],
            first_name=first_name,
            username=username
        )
        await self.bot.send_message(chat_id=telegram_id, text=roast)
        db.update_escalation_level(reminder["id"], 4, now.isoformat(timespec="seconds"))
        logger.info("Escalation level 4 LLM roast sent for reminder %s", reminder["id"])

    async def _send_level_5_offended(self, reminder: Dict, telegram_id: int, now: datetime):
        """Level 5: Bot gets offended (+60 min)."""
        await self.bot.send_message(chat_id=telegram_id, text="И ПОШЁЛ ТЫ НАХУЙ.")
        db.set_user_offended(telegram_id, offended=True, reminder_id=reminder["id"])
        db.update_escalation_level(reminder["id"], 5, now.isoformat(timespec="seconds"))
        logger.info("Escalation level 5 offense sent for reminder %s", reminder["id"])

    async def _check_forgiveness(self, now: datetime):
        """Check if any offended users should be forgiven."""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, offended_at FROM user_state WHERE is_offended = 1")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            telegram_id = row["telegram_id"]
            offended_at = row["offended_at"]
            if not offended_at:
                continue

            offended_time = datetime.fromisoformat(offended_at.replace("Z", "+00:00"))
            if offended_time.tzinfo is None:
                offended_time = offended_time.replace(tzinfo=UTC)

            time_since_offended = (now - offended_time).total_seconds() / 60  # in minutes

            if time_since_offended >= OFFENDED_DURATION_MINUTES:
                # Forgive
                message = random.choice(FORGIVENESS_PHRASES)
                await self.bot.send_message(chat_id=telegram_id, text=message)
                db.set_user_offended(telegram_id, offended=False)
                logger.info("User %s has been forgiven", telegram_id)
