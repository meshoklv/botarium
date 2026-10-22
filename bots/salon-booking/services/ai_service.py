import json
import requests
from datetime import datetime
from typing import Dict, Optional
from config import (
    OUTER_API_KEY,
    AI_MODEL,
    OPENROUTER_API_URL,
    AI_SYSTEM_PROMPT,
    logger
)
from services.database import db


class AIService:
    """Service for AI-powered conversation and intent understanding"""

    @staticmethod
    async def process_message(telegram_id: int, user_message: str, is_voice: bool = False) -> Dict:
        """
        Process user message with AI and extract booking intent

        Returns:
        {
            'response_text': str,
            'action': str,
            'collected_data': dict,
            'missing_fields': list,
            'needs_confirmation': bool
        }
        """
        try:
            # Get conversation history
            history = db.get_conversation_history(telegram_id, limit=10)

            # Get current temp booking data
            temp_data = db.get_temp_booking(telegram_id)

            # Build conversation context
            conversation_context = ""
            for msg in history:
                role_name = "Клиент" if msg['role'] == 'user' else "Ассистент"
                conversation_context += f"{role_name}: {msg['message']}\n"

            # Current datetime
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Prepare system prompt with context
            system_prompt = AI_SYSTEM_PROMPT.format(current_datetime=current_datetime)
            system_prompt += f"\n\nТекущая дата и время: {current_datetime}"
            system_prompt += f"\n\nИстория диалога:\n{conversation_context}"

            if temp_data:
                system_prompt += f"\n\nУже собранные данные о записи:\n{json.dumps(temp_data, ensure_ascii=False, indent=2)}"

            # Prepare API request
            headers = {
                "Authorization": f"Bearer {OUTER_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }

            logger.info(f"Sending request to AI API for user {telegram_id}")

            # Make API request
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"AI API error: {response.status_code} - {response.text}")
                return {
                    'response_text': "Извините, произошла ошибка. Попробуйте еще раз.",
                    'action': 'continue_dialog',
                    'collected_data': temp_data or {},
                    'missing_fields': [],
                    'needs_confirmation': False
                }

            # Parse response
            response_data = response.json()
            ai_response = response_data['choices'][0]['message']['content']

            logger.info(f"AI response: {ai_response[:200]}...")

            # Parse JSON response
            try:
                result = json.loads(ai_response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI JSON response: {e}")
                logger.error(f"Raw response: {ai_response}")
                return {
                    'response_text': "Извините, произошла ошибка. Попробуйте еще раз.",
                    'action': 'continue_dialog',
                    'collected_data': temp_data or {},
                    'missing_fields': [],
                    'needs_confirmation': False
                }

            # Save conversation to history
            db.add_message(telegram_id, 'user', user_message)
            db.add_message(telegram_id, 'assistant', result.get('response_text', ''))

            # Update temp booking data with collected info
            collected = result.get('collected_data', {})
            if any(collected.values()):
                # Merge with existing temp data
                existing = temp_data or {}
                for key, value in collected.items():
                    if value is not None:
                        existing[key] = value

                db.save_temp_booking(telegram_id, existing)
                result['collected_data'] = existing

            return result

        except Exception as e:
            logger.error(f"AI service error: {str(e)}")
            return {
                'response_text': "Извините, произошла ошибка. Попробуйте еще раз.",
                'action': 'continue_dialog',
                'collected_data': temp_data or {},
                'missing_fields': [],
                'needs_confirmation': False
            }

    @staticmethod
    def validate_booking_data(data: Dict) -> tuple[bool, list]:
        """
        Validate if all required booking fields are present

        Returns: (is_complete, missing_fields)
        """
        required_fields = ['service', 'master', 'date', 'time', 'client_name', 'phone']
        missing = []

        for field in required_fields:
            if not data.get(field):
                missing.append(field)

        return len(missing) == 0, missing


# Global service instance
ai_service = AIService()
