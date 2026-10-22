import os
import json
import logging
import requests
import time
from typing import Optional, Dict, Any
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

class TaskAnalyzer:
    """
    Модуль для AI-анализа задач с помощью OpenRouter API.
    
    Основные задачи:
    1. Структурированный анализ задачи
    2. Выделение ключевых элементов
    3. Определение целей и критериев выполнения
    4. Оценка ресурсов и потенциальных сложностей
    """
    
    def __init__(self, api_key: str = None):
        """
        Инициализация анализатора задач.
        
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
            logger.info(f"OpenRouter configured successfully - model: {self.model}")
        except Exception as e:
            logger.error(f"OpenRouter configuration error: {str(e)}")
            raise
    
    def analyze_task(self, task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Провести AI-анализ задачи и вернуть структурированный результат.
        
        Args:
            task_data: Словарь с данными задачи
            
        Returns:
            Словарь с результатами анализа или None при ошибке
        """
        try:
            # Подготовка данных задачи для анализа
            task_info = self._format_task_info(task_data)
            
            # Системный промпт для анализа задач
            system_prompt = self._get_analysis_prompt()
            
            # Подготовка запроса к OpenRouter
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Проанализируй следующую задачу:\n\n{task_info}"
                    }
                ],
                **self.settings
            }
            
            # Отправка запроса с повторными попытками
            for attempt in range(MAX_RETRIES):
                try:
                    logger.info(f"Task analysis attempt - attempt: {attempt + 1}, max_retries: {MAX_RETRIES}, task_title_preview: {task_data.get('title', '')[:50]}")
                    
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
                            analysis_result = json.loads(content)
                            analysis_result['processing_time'] = processing_time
                            analysis_result['model_used'] = self.model
                            analysis_result['attempt'] = attempt + 1
                            analysis_result['task_id'] = task_data.get('id')
                            analysis_result['analyzed_at'] = time.time()
                            
                            logger.info(f"Task analysis completed successfully - processing_time: {processing_time}")
                            return analysis_result
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"OpenRouter JSON parsing error: {str(e)}")
                            if attempt == MAX_RETRIES - 1:
                                return self._get_fallback_analysis(task_data, str(e))
                            
                    elif response.status_code == 429:  # Rate limit
                        logger.warning(f"OpenRouter rate limit hit - wait_time: {RETRY_DELAY * (attempt + 1)}")
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                        
                    else:
                        logger.error(f"OpenRouter API error - status_code: {response.status_code}, response_text: {response.text}")
                        if attempt == MAX_RETRIES - 1:
                            return self._get_fallback_analysis(task_data, f"API error: {response.status_code}")
                    
                except requests.exceptions.Timeout:
                    logger.warning(f"OpenRouter request timeout - attempt: {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        return self._get_fallback_analysis(task_data, "Request timeout")
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"OpenRouter network error: {str(e)}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        return self._get_fallback_analysis(task_data, f"Network error: {e}")
                        
                except Exception as e:
                    logger.error(f"Unexpected task analysis error: {str(e)}")
                    return self._get_fallback_analysis(task_data, f"Unexpected error: {e}")
            
            return self._get_fallback_analysis(task_data, "Max retries exceeded")
            
        except Exception as e:
            logger.error(f"Critical task analysis error: {str(e)}")
            return self._get_fallback_analysis(task_data, f"Critical error: {e}")
    
    def _format_task_info(self, task_data: Dict[str, Any]) -> str:
        """Форматировать информацию о задаче для анализа"""
        info_lines = []
        
        # Основная информация
        info_lines.append(f"Заголовок: {task_data.get('title', 'Не указан')}")
        
        if task_data.get('description'):
            info_lines.append(f"Описание: {task_data.get('description', '')}")
        
        # Метаданные
        if task_data.get('priority'):
            info_lines.append(f"Приоритет: {task_data.get('priority', '')}")
        
        if task_data.get('deadline'):
            info_lines.append(f"Дедлайн: {task_data.get('deadline', '')}")
        
        if task_data.get('category'):
            info_lines.append(f"Категория: {task_data.get('category', '')}")
        
        if task_data.get('tags'):
            info_lines.append(f"Теги: {task_data.get('tags', '')}")
        
        if task_data.get('time_estimate'):
            info_lines.append(f"Оценка времени: {task_data.get('time_estimate', '')} минут")
        
        return "\n".join(info_lines)
    
    def _get_analysis_prompt(self) -> str:
        """Получить системный промпт для анализа задач"""
        return """
Ты - экспертный AI-аналитик задач. Твоя задача - провести структурированный анализ задачи без добавления отсебятины.

ТВОЯ РОЛЬ:
Анализировать задачу и выделять ключевые элементы, не искажая исходную информацию.

ТВОИ ЗАДАЧИ:
1. ВНИМАТЕЛЬНО изучить предоставленную задачу
2. СТРУКТУРИРОВАТЬ информацию в четкие категории
3. ВЫДЕЛИТЬ ключевые элементы без добавления новой информации
4. СОХРАНИТЬ точность и не искажать смысл

ПРИНЦИПЫ РАБОТЫ:
- НЕ добавляй информацию, которой нет в исходной задаче
- НЕ фантазируй и не предполагай
- НЕ меняй формулировки оригинала без крайней необходимости
- СОСРЕДОТОЧЬСЯ на структурировании, а не на изменении содержания

ФОРМАТ ОТВЕТА:
Всегда отвечай ТОЛЬКО в формате JSON:

{
  "goal": "Основная цель задачи на основе предоставленной информации",
  "key_actions": [
    "Конкретные действия из задачи (без добавления отсебятины)",
    "Перечисляй только то, что явно указано"
  ],
  "resources": [
    "Ресурсы, упомянутые в задаче",
    "Требования к выполнению задачи"
  ],
  "potential_challenges": [
    "Потенциальные сложности на основе содержания задачи",
    "Риски, явно или косвенно указанные в задаче"
  ],
  "success_criteria": [
    "Критерии успешного выполнения из задачи",
    "Как определить, что задача выполнена"
  ],
  "recommendations": [
    "Рекомендации по структурированию задачи",
    "Как лучше организовать выполнение"
  ]
}

ПРИМЕР:

Входная задача:
"Подготовить презентацию по новому продукту к встрече в пятницу. Нужно включить информацию о ценах, характеристиках и преимуществах. Презентация должна быть визуально привлекательной."

Выход:
{
  "goal": "Подготовить презентацию по новому продукту к встрече в пятницу",
  "key_actions": [
    "Подготовить презентацию по новому продукту",
    "Включить информацию о ценах",
    "Включить информацию о характеристиках",
    "Включить информацию о преимуществах",
    "Сделать презентацию визуально привлекательной"
  ],
  "resources": [
    "Информация о новом продукте",
    "Данные о ценах",
    "Характеристики продукта",
    "Преимущества продукта"
  ],
  "potential_challenges": [
    "Сложность сделать презентацию визуально привлекательной",
    "Необходимость собрать полную информацию о продукте к пятнице"
  ],
  "success_criteria": [
    "Презентация подготовлена",
    "Все требуемые разделы включены",
    "Презентация визуально привлекательна",
    "Презентация готова к пятничной встрече"
  ],
  "recommendations": [
    "Начать с структуры презентации",
    "Собрать все необходимые данные",
    "Выделить время на дизайн",
    "Провести предварительный просмотр"
  ]
}

ВАЖНО:
- Отвечай ТОЛЬКО валидным JSON
- НЕ добавляй комментарии или пояснения
- НЕ используй markdown форматирование
- Строго следуй структуре ответа
- Не искажай исходную информацию
"""
    
    def _get_fallback_analysis(self, task_data: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """Получить базовый анализ при ошибке"""
        return {
            'goal': task_data.get('title', 'Не указана'),
            'key_actions': ['Анализ не выполнен из-за ошибки'],
            'resources': ['Информация недоступна'],
            'potential_challenges': [error or 'Неизвестная ошибка'],
            'success_criteria': ['Анализ не выполнен'],
            'recommendations': ['Попробуйте повторить анализ позже'],
            'processing_error': error,
            'fallback': True
        }

# Глобальный экземпляр анализатора
task_analyzer = TaskAnalyzer()

# Функция для быстрого доступа
def analyze_task(task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Быстрая функция для анализа задачи.
    
    Args:
        task_data: Данные задачи
        
    Returns:
        Результаты анализа задачи
    """
    return task_analyzer.analyze_task(task_data)

if __name__ == "__main__":
    # Тестирование модуля
    analyzer = TaskAnalyzer()
    
    test_task = {
        'id': 1,
        'title': 'Подготовить отчет по продажам за квартал',
        'description': 'Собрать данные по продажам за последний квартал, проанализировать показатели и подготовить презентацию для руководства. Обратить внимание на отклонения от плана.',
        'priority': 'high',
        'deadline': '2024-04-15',
        'category': 'работа',
        'tags': 'отчет,продажи,анализ',
        'time_estimate': 120
    }
    
    print("🧪 Тестирование TaskAnalyzer...")
    print(f"Входная задача: {test_task['title']}")
    
    result = analyzer.analyze_task(test_task)
    
    if result:
        print("✅ Результат анализа:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("❌ Ошибка анализа")