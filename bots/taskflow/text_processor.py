import os
import json
import logging
import aiohttp
import asyncio
import requests
import time
from typing import Optional, Dict, Any
from pathlib import Path
from openrouter_config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_SETTINGS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    get_headers,
    validate_config
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    """
    Модуль для постобработки текста от Whisper с помощью OpenRouter API.
    
    Основные задачи:
    1. Исправление ошибок распознавания речи
    2. Структурирование текста задач
    3. Извлечение ключевой информации (дедлайны, приоритеты, категории)
    4. Улучшение читаемости и понятности
    """
    
    def __init__(self, api_key: str = None):
        """
        Инициализация процессора текста.
        
        Args:
            api_key: API ключ OpenRouter (по умолчанию из переменной окружения)
        """
        # Используем API ключ из конфигурации или переданный параметр
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.model = OPENROUTER_MODEL
        self.settings = OPENROUTER_SETTINGS.copy()
        
        # Проверяем конфигурацию
        try:
            validate_config()
            logger.info(f"✅ OpenRouter настроен, модель: {self.model}")
        except Exception as e:
            logger.error(f"❌ Ошибка конфигурации OpenRouter: {str(e)}")
            raise
        
        # Загружаем системный промпт из файла
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """Загружает системный промпт из файла"""
        try:
            current_dir = Path(__file__).parent
            prompt_file = current_dir / "system_prompt.txt"
            
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.info("Системный промпт загружен из файла")
                return content
            else:
                logger.warning("Файл system_prompt.txt не найден, используем базовый промпт")
                return self._get_fallback_prompt()
        except Exception as e:
            logger.error(f"Ошибка загрузки системного промпта: {str(e)}")
            return self._get_fallback_prompt()
    
    def _get_fallback_prompt(self) -> str:
        """Базовый промпт на случай ошибки загрузки файла"""
        return """
Ты - специализированный ассистент для обработки текста, полученного от системы распознавания речи Whisper.

ТВОЯ РОЛЬ:
Ты помогаешь пользователям создавать четкие и структурированные задачи из неточного или "грязного" текста, полученного от распознавания голосовых сообщений.

ТВОИ ЗАДАЧИ:
1. ИСПРАВЛЕНИЕ ОШИБОК - исправь ошибки распознавания, опечатки, неправильные слова
2. СТРУКТУРИРОВАНИЕ - преобразуй хаотичный текст в четкую формулировку задачи
3. ИЗВЛЕЧЕНИЕ ДАННЫХ - найди и выдели важную информацию:
   - Дедлайны (даты, время)
   - Приоритеты (высокий, средний, низкий)
   - Категории (работа, личное, учеба, здоровье и т.д.)
   - Исполнители (кому назначить)
4. УЛУЧШЕНИЕ ЧИТАЕМОСТИ - сделай текст понятным и actionable

ПРИНЦИПЫ РАБОТЫ:
- Сохраняй СМЫСЛ оригинального сообщения
- Используй ПРОСТОЙ и ПОНЯТНЫЙ язык
- Делай задачи КОНКРЕТНЫМИ и ВЫПОЛНИМЫМИ
- НЕ добавляй информацию, которой не было в оригинале
- Если что-то неясно - оставь как есть, но исправь очевидные ошибки

ФОРМАТ ОТВЕТА:
Возвращай ТОЛЬКО JSON объект с полями:
{
  "title": "Краткое название задачи (до 100 символов)",
  "description": "Подробное описание задачи",
  "priority": "high|medium|low или null если не указано",
  "deadline": "Дедлайн в формате YYYY-MM-DD HH:MM или null",
  "category": "Категория задачи или null",
  "tags": ["тег1", "тег2"] или null,
  "assigned_to": "Кому назначено или null",
  "confidence": 0.0-1.0 (уверенность в правильности обработки)
}

ОТВЕЧАЙ ТОЛЬКО JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА!
"""
    
    async def process_whisper_output(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает сырой текст от Whisper и возвращает структурированную задачу.
        
        Args:
            raw_text: Сырой текст от Whisper
            
        Returns:
            Словарь с обработанной информацией о задаче или None при ошибке
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Пустой текст для обработки")
            return None
            
        try:
            logger.info(f"Обработка текста: {raw_text[:100]}...")
            
            # Подготовка запроса к OpenRouter
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": self.system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Обработай этот текст от распознавания речи: '{raw_text}'"
                    }
                ],
                **self.settings
            }
            
            # Отправка запроса
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ошибка API OpenRouter: статус {response.status}, ошибка: {error_text}")
                        return None
                    
                    result = await response.json()
                    
                    if 'choices' not in result or not result['choices']:
                        logger.error("Некорректный ответ от API")
                        return None
                    
                    # Извлечение и парсинг ответа
                    content = result['choices'][0]['message']['content'].strip()
                    logger.info(f"Ответ от API: {content[:200]}...")
                    
                    # Парсинг JSON ответа
                    try:
                        processed_data = json.loads(content)
                        
                        # Валидация обязательных полей
                        if not processed_data.get('title'):
                            logger.warning("Отсутствует название задачи")
                            processed_data['title'] = raw_text[:100]  # Fallback
                        
                        if not processed_data.get('description'):
                            processed_data['description'] = processed_data['title']
                        
                        # Добавление метаданных
                        processed_data['original_text'] = raw_text
                        processed_data['processed_at'] = asyncio.get_event_loop().time()
                        
                        logger.info(f"Успешно обработан текст: {processed_data['title']}")
                        return processed_data
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON: {str(e)}")
                        logger.error(f"Содержимое ответа: {content}")
                        
                        # Fallback - возвращаем базовую структуру
                        return {
                            'title': raw_text[:100],
                            'description': raw_text,
                            'priority': None,
                            'deadline': None,
                            'category': None,
                            'tags': None,
                            'assigned_to': None,
                            'confidence': 0.3,
                            'original_text': raw_text,
                            'processed_at': asyncio.get_event_loop().time(),
                            'processing_error': 'JSON parse error'
                        }
                        
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка сети при обращении к API: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке текста: {str(e)}")
            return None
    
    def process_whisper_output_sync(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Синхронная обработка текста через OpenRouter API с повторными попытками
        
        Args:
            raw_text: Сырой текст от Whisper
            
        Returns:
            Словарь с обработанной информацией о задаче или None при ошибке
        """
        for attempt in range(MAX_RETRIES):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": f"Обработай этот текст от распознавания речи: '{raw_text}'"}
                    ],
                    **self.settings
                }
                
                logger.info(f"🚀 Попытка отправки к OpenRouter - attempt: {attempt + 1} - max_retries: {MAX_RETRIES} - text_preview: {raw_text[:100]} - operation: openrouter_request")
                
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=get_headers(),
                    json=payload,
                    timeout=REQUEST_TIMEOUT
                )
                processing_time = time.time() - start_time
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # Парсим JSON ответ
                    try:
                        processed_data = json.loads(content)
                        processed_data['processing_time'] = processing_time
                        processed_data['model_used'] = self.model
                        processed_data['attempt'] = attempt + 1
                        processed_data['original_text'] = raw_text
                        processed_data['processed_at'] = time.time()
                        
                        logger.info(f"✅ Текст успешно обработан OpenRouter - processing_time: {processing_time:.2f}с - operation: openrouter_success")
                        return processed_data
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON от OpenRouter - error: {str(e)} - attempt: {attempt + 1} - operation: json_parsing_error")
                        if attempt == MAX_RETRIES - 1:
                            return {
                                'title': raw_text[:100],
                                'description': raw_text,
                                'priority': None,
                                'deadline': None,
                                'category': None,
                                'tags': None,
                                'assigned_to': None,
                                'confidence': 0.3,
                                'original_text': raw_text,
                                'processed_at': time.time(),
                                'processing_error': f'JSON parse error: {e}'
                            }
                        
                elif response.status_code == 429:  # Rate limit
                    logger.warning(f"Rate limit OpenRouter - wait_time: {RETRY_DELAY * (attempt + 1)}с - attempt: {attempt + 1} - operation: rate_limit")
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                    
                else:
                    logger.error(f"Ошибка OpenRouter API - status_code: {response.status_code} - response_text: {response.text} - attempt: {attempt + 1} - operation: api_error")
                    if attempt == MAX_RETRIES - 1:
                        return {
                            'title': raw_text[:100],
                            'description': raw_text,
                            'priority': None,
                            'deadline': None,
                            'category': None,
                            'tags': None,
                            'assigned_to': None,
                            'confidence': 0.3,
                            'original_text': raw_text,
                            'processed_at': time.time(),
                            'processing_error': f'API error: {response.status_code}'
                        }
                
            except requests.exceptions.Timeout:
                logger.warning(f"Таймаут запроса к OpenRouter - attempt: {attempt + 1} - operation: request_timeout")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return {
                        'title': raw_text[:100],
                        'description': raw_text,
                        'priority': None,
                        'deadline': None,
                        'category': None,
                        'tags': None,
                        'assigned_to': None,
                        'confidence': 0.3,
                        'original_text': raw_text,
                        'processed_at': time.time(),
                        'processing_error': 'Request timeout'
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка сети при обращении к OpenRouter - error: {str(e)} - attempt: {attempt + 1} - operation: network_error")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return {
                        'title': raw_text[:100],
                        'description': raw_text,
                        'priority': None,
                        'deadline': None,
                        'category': None,
                        'tags': None,
                        'assigned_to': None,
                        'confidence': 0.3,
                        'original_text': raw_text,
                        'processed_at': time.time(),
                        'processing_error': f'Network error: {e}'
                    }
                    
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке текста - error: {str(e)} - operation: unexpected_error")
                return {
                    'title': raw_text[:100],
                    'description': raw_text,
                    'priority': None,
                    'deadline': None,
                    'category': None,
                    'tags': None,
                    'assigned_to': None,
                    'confidence': 0.3,
                    'original_text': raw_text,
                    'processed_at': time.time(),
                    'processing_error': f'Unexpected error: {e}'
                }
        
        return {
            'title': raw_text[:100],
            'description': raw_text,
            'priority': None,
            'deadline': None,
            'category': None,
            'tags': None,
            'assigned_to': None,
            'confidence': 0.3,
            'original_text': raw_text,
            'processed_at': time.time(),
            'processing_error': 'Max retries exceeded'
        }
    
    def test_connection(self) -> bool:
        """
        Тестирует подключение к OpenRouter API.
        
        Returns:
            True если подключение успешно, False иначе
        """
        try:
            test_result = self.process_whisper_output_sync("тест подключения")
            return test_result is not None
        except Exception as e:
            logger.error(f"Ошибка тестирования подключения - error: {str(e)} - operation: connection_test")
            return False

# Глобальный экземпляр процессора
text_processor = TextProcessor()

# Функция для быстрого доступа
def process_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Быстрая функция для обработки текста.
    
    Args:
        raw_text: Сырой текст от Whisper
        
    Returns:
        Обработанные данные задачи
    """
    return text_processor.process_whisper_output_sync(raw_text)

if __name__ == "__main__":
    # Тестирование модуля
    processor = TextProcessor()
    
    test_texts = [
        "купить молоко завтра в магазине до восьми вечера",
        "встреча с клиентом важная в понедельник утром обсудить проект",
        "позвонить маме вечером не забыть",
        "сделать презентацию для работы срочно до пятницы"
    ]
    
    print("🧪 Тестирование TextProcessor...")
    
    for i, text in enumerate(test_texts, 1):
        print(f"\n--- Тест {i} ---")
        print(f"Входной текст: {text}")
        
        result = processor.process_whisper_output_sync(text)
        
        if result:
            print(f"✅ Результат:")
            print(f"   Название: {result.get('title')}")
            print(f"   Описание: {result.get('description')}")
            print(f"   Приоритет: {result.get('priority')}")
            print(f"   Дедлайн: {result.get('deadline')}")
            print(f"   Категория: {result.get('category')}")
            print(f"   Уверенность: {result.get('confidence')}")
        else:
            print("❌ Ошибка обработки")
    
    print("\n🔗 Тестирование подключения...")
    if processor.test_connection():
        print("✅ Подключение к OpenRouter API успешно")
    else:
        print("❌ Ошибка подключения к OpenRouter API")