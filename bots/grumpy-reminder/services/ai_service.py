import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional

import requests

from config import (
    OUTER_API_KEY,
    AI_MODEL,
    OPENROUTER_API_URL,
    AI_SYSTEM_PROMPT,
    logger,
    AGGRESSIVE_ALERT_PROMPT,
    AFTER_CONFIRM_PROMPT,
    IDLE_PROMPT,
    TIMEZONE_DETECT_PROMPT,
    ULTIMATE_ROAST_PROMPT,
)
from services.database import db
from services.time_service import normalize_datetime, resolve_timezone


class AIService:
    """Service that talks to LLM to extract reminder intent."""

    async def process_message(self, telegram_id: int, user_message: str, timezone_name: Optional[str]) -> Dict[str, Any]:
        temp_data = db.get_temp_reminder(telegram_id) or {}
        history = db.get_conversation_history(telegram_id, limit=6)  # Reduced from 10 to 6

        zone = resolve_timezone(timezone_name)
        zone_name = timezone_name or getattr(zone, "key", "UTC")

        conversation_context = ""
        for msg in history:
            role_name = "Пользователь" if msg["role"] == "user" else "Бот"
            conversation_context += f"{role_name}: {msg['message']}\n"

        # Get user reminders to give context to AI (only active ones)
        reminders = db.get_user_reminders(telegram_id)
        active_reminders = [r for r in reminders if r['status'] not in ['cancelled', 'completed']]
        reminders_context = ""
        if active_reminders:
            reminders_context = "\n\nТекущие напоминания пользователя:\n"
            for idx, reminder in enumerate(active_reminders[:5], start=1):  # Max 5 reminders
                reminders_context += f"{idx}. {reminder['task']} (статус: {reminder['status']})\n"

        system_prompt = AI_SYSTEM_PROMPT
        system_prompt += f"\n\nРаботаем в часовом поясе: {zone_name}."
        system_prompt += f"\nТекущая дата и время: {datetime.now(zone):%Y-%m-%d %H:%M}"

        if conversation_context.strip():
            system_prompt += f"\n\nИстория диалога:\n{conversation_context}"

        if reminders_context:
            system_prompt += reminders_context

        if temp_data:
            system_prompt += "\n\nУже известные данные о напоминании:\n"
            system_prompt += json.dumps(temp_data, ensure_ascii=False, indent=2)

        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {OUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            logger.info("Sending message to AI for user %s", telegram_id)
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.error("Failed to reach AI service: %s", exc)
            return self._error_response(temp_data)

        if response.status_code != 200:
            logger.error("AI API returned %s: %s", response.status_code, response.text)
            return self._error_response(temp_data)

        try:
            ai_message = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(ai_message)
        except (KeyError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse AI response: %s", exc)
            logger.debug("Raw AI response: %s", response.text)
            return self._error_response(temp_data)

        db.add_message(telegram_id, "user", user_message)
        db.add_message(telegram_id, "assistant", parsed.get("response_text", ""))

        # Auto-cleanup old history to prevent context bloat
        db.cleanup_old_conversation_history(telegram_id, keep_last_n=20)

        # Check if action is cancel_reminder
        action = parsed.get("action")
        if action == "cancel_reminder":
            cancel_query = parsed.get("cancel_query", "")
            return {
                "response_text": parsed.get("response_text", "Щас поищу."),
                "action": "cancel_reminder",
                "cancel_query": cancel_query,
                "reminder_data": {},
                "is_complete": False,
                "missing_fields": [],
                "suggested_followup": parsed.get("suggested_followup"),
            }

        extracted = parsed.get("extracted_data") or {}
        merged = {**temp_data}

        for key in ("task", "datetime", "datetime_human"):
            value = extracted.get(key)
            if value:
                merged[key] = value

        if "datetime" in merged and merged["datetime"]:
            try:
                normalized = normalize_datetime(merged["datetime"], zone)
                merged["datetime"] = normalized.local.isoformat()
                merged["datetime_human"] = normalized.human
            except Exception as exc:
                logger.warning("Failed to normalize datetime '%s': %s", merged["datetime"], exc)

        if merged:
            db.save_temp_reminder(telegram_id, merged)

        return {
            "response_text": parsed.get("response_text", "Принял, не тупи."),
            "action": action,
            "reminder_data": merged,
            "is_complete": bool(parsed.get("is_complete")),
            "missing_fields": parsed.get("missing_fields") or [],
            "suggested_followup": parsed.get("suggested_followup"),
        }

    @staticmethod
    def _error_response(temp_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "response_text": "У меня тут мозги дымятся, пиши понятнее и быстрее.",
            "reminder_data": temp_data,
            "is_complete": False,
            "missing_fields": [],
            "suggested_followup": None,
        }

    async def generate_reminder_alert(self, task: str, attempt: int, timezone_name: Optional[str]) -> str:
        payload = {"task": task, "attempt": attempt}
        if timezone_name:
            payload["timezone"] = timezone_name
        return await asyncio.to_thread(self._request_openrouter_message, AGGRESSIVE_ALERT_PROMPT, payload)

    async def generate_after_confirm(self) -> str:
        return await asyncio.to_thread(self._request_openrouter_message, AFTER_CONFIRM_PROMPT, {})

    async def generate_idle_prompt(self) -> str:
        return await asyncio.to_thread(self._request_openrouter_message, IDLE_PROMPT, {})

    def _request_openrouter_message(self, system_prompt: str, payload_data: Dict[str, Any]) -> str:
        user_content = "\n".join(f"{k}: {v}" for k, v in payload_data.items()) if payload_data else "Сгенерируй сообщение."
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.9,
            "max_tokens": 80,
        }

        headers = {
            "Authorization": f"Bearer {OUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]["content"].strip()
            return message
        except Exception as exc:
            logger.error("OpenRouter prompt failed: %s", exc)
            return "Хватит тупить. Делай то, что я сказал.".upper()

    async def detect_timezone(self, user_input: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._request_timezone_detection, user_input)

    def _request_timezone_detection(self, user_input: str) -> Dict[str, Any]:
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": TIMEZONE_DETECT_PROMPT},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "max_tokens": 120,
        }

        headers = {
            "Authorization": f"Bearer {OUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:
            logger.error("Timezone detection request failed: %s", exc)
            return {"timezone": None, "note": None}

    async def generate_ultimate_roast(
        self,
        task: str,
        first_name: str,
        username: str
    ) -> str:
        """Generate ultimate roast message for level 4 escalation."""
        prompt = ULTIMATE_ROAST_PROMPT.format(
            task=task,
            first_name=first_name,
            username=username
        )
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Сгенерируй максимально агрессивный роспись."},
            ],
            "temperature": 0.9,
            "max_tokens": 400,
        }

        headers = {
            "Authorization": f"Bearer {OUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = await asyncio.to_thread(
                requests.post,
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]["content"].strip()
            return message
        except Exception as exc:
            logger.error("Ultimate roast generation failed: %s", exc)
            return f"{first_name.upper()}, ДА ТЫ ВООБЩЕ ОХУЕЛ?! ПОЧЕМУ ТЫ НЕ ХОЧЕШЬ {task.upper()}?! Я ТУТ ПОЛЧАСА ОРУ, А ТЫ КАК ДЕБИЛ ИГНОРИРУЕШЬ МЕНЯ! ВСТАВАЙ И ИДИ ДЕЛАТЬ УЖЕ, СУКА!"


ai_service = AIService()
