#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Красивая система логирования для TaskFlowBot
Поддерживает цветовую подсветку и структурированные сообщения на русском языке
"""

import logging
import sys
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветовой подсветкой для терминала"""
    
    # ANSI цветовые коды
    COLORS = {
        'DEBUG': '\033[36m',      # Голубой
        'INFO': '\033[32m',       # Зеленый
        'WARNING': '\033[33m',    # Желтый
        'ERROR': '\033[31m',      # Красный
        'CRITICAL': '\033[35m',   # Фиолетовый
    }
    
    RESET = '\033[0m'  # Сброс цвета
    BOLD = '\033[1m'   # Жирный
    
    # Эмодзи для разных уровней
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '💥',
    }
    
    def format(self, record):
        # Получаем цвет для уровня логирования
        color = self.COLORS.get(record.levelname, '')
        emoji = self.EMOJIS.get(record.levelname, '📝')
        
        # Форматируем время
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Форматируем имя модуля
        module_name = record.name.split('.')[-1] if '.' in record.name else record.name
        
        # Создаем красивое сообщение
        formatted_message = (
            f"{color}{self.BOLD}[{timestamp}]{self.RESET} "
            f"{emoji} {color}{record.levelname}{self.RESET} "
            f"{self.BOLD}[{module_name}]{self.RESET} "
            f"{record.getMessage()}"
        )
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            formatted_message += f"\n{color}📋 Детали ошибки:{self.RESET}\n"
            formatted_message += self.formatException(record.exc_info)
        
        return formatted_message


class StructuredLogger:
    """Структурированный логгер с красивым выводом"""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Удаляем существующие обработчики
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Создаем консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        # Устанавливаем цветной форматтер
        formatter = ColoredFormatter()
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        
        # Предотвращаем дублирование сообщений
        self.logger.propagate = False
    
    def debug(self, message: str, **kwargs):
        """Отладочное сообщение"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Информационное сообщение"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Предупреждение"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Ошибка"""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Критическая ошибка"""
        self._log(logging.CRITICAL, message, **kwargs)

    def success(self, message: str, **kwargs):
        """Успешное выполнение операции"""
        self._log(logging.INFO, message, **kwargs)
    
    def _log(self, level: int, message: str, **kwargs):
        """Внутренний метод для логирования с дополнительными параметрами"""
        if kwargs:
            # Добавляем дополнительную информацию к сообщению
            extra_info = ' | '.join([f"{k}={v}" for k, v in kwargs.items()])
            message = f"{message} ({extra_info})"
        
        self.logger.log(level, message)
    
    # Специальные методы для разных типов событий
    def user_action(self, user_id: int, action: str, details: str = ""):
        """Логирование действий пользователя"""
        message = f"👤 Пользователь {user_id}: {action}"
        if details:
            message += f" | {details}"
        self.info(message)
    
    def database_operation(self, operation: str, table: str, duration: Optional[float] = None):
        """Логирование операций с базой данных"""
        message = f"🗄️ БД операция: {operation} в таблице '{table}'"
        if duration:
            if duration > 1.0:
                message += f" | ⏱️ {duration:.2f}с (медленно!)"
            else:
                message += f" | ⏱️ {duration:.2f}с"
        self.info(message)
    
    def api_call(self, service: str, endpoint: str, status: str, duration: Optional[float] = None):
        """Логирование API вызовов"""
        status_emoji = "✅" if status == "success" else "❌"
        message = f"🌐 API {service}: {endpoint} {status_emoji} {status}"
        if duration:
            message += f" | ⏱️ {duration:.2f}с"
        self.info(message)
    
    def task_operation(self, operation: str, task_id: Optional[int] = None, user_id: Optional[int] = None):
        """Логирование операций с задачами"""
        message = f"📋 Задача: {operation}"
        if task_id:
            message += f" | ID: {task_id}"
        if user_id:
            message += f" | Пользователь: {user_id}"
        self.info(message)
    
    def bot_event(self, event: str, details: str = ""):
        """Логирование событий бота"""
        message = f"🤖 Бот: {event}"
        if details:
            message += f" | {details}"
        self.info(message)
    
    def performance_warning(self, operation: str, duration: float, threshold: float = 1.0):
        """Предупреждение о производительности"""
        if duration > threshold:
            self.warning(f"🐌 Медленная операция: {operation} заняла {duration:.2f}с (порог: {threshold:.2f}с)")
    
    def security_event(self, event: str, user_id: Optional[int] = None, details: str = ""):
        """Логирование событий безопасности"""
        message = f"🔒 Безопасность: {event}"
        if user_id:
            message += f" | Пользователь: {user_id}"
        if details:
            message += f" | {details}"
        self.warning(message)


def setup_logging(level: int = logging.INFO) -> StructuredLogger:
    """Настройка системы логирования для всего приложения"""
    
    # Отключаем стандартное логирование
    logging.getLogger().handlers.clear()
    
    # Создаем основной логгер
    main_logger = StructuredLogger('TaskFlowBot', level)
    
    # Настраиваем логгеры для внешних библиотек
    external_loggers = [
        'telegram',
        'httpx',
        'urllib3',
        'asyncio',
        'aiohttp'
    ]
    
    for logger_name in external_loggers:
        ext_logger = logging.getLogger(logger_name)
        ext_logger.setLevel(logging.WARNING)  # Показываем только предупреждения и ошибки
    
    return main_logger


# Создаем глобальный экземпляр логгера
logger = setup_logging()


if __name__ == "__main__":
    # Тестирование системы логирования
    print("🧪 Тестирование системы логирования...\n")
    
    test_logger = StructuredLogger('test')
    
    test_logger.debug("Отладочное сообщение")
    test_logger.info("Информационное сообщение")
    test_logger.warning("Предупреждение")
    test_logger.error("Ошибка")
    test_logger.critical("Критическая ошибка")
    
    print("\n📋 Специальные методы логирования:\n")
    
    test_logger.user_action(12345, "создал задачу", "Название: Тестовая задача")
    test_logger.database_operation("SELECT", "tasks", 0.15)
    test_logger.database_operation("INSERT", "users", 2.5)  # Медленная операция
    test_logger.api_call("OpenRouter", "/chat/completions", "success", 1.2)
    test_logger.task_operation("создание", task_id=123, user_id=456)
    test_logger.bot_event("запуск", "Версия 2.0")
    test_logger.performance_warning("обработка голосового сообщения", 3.5, 2.0)
    test_logger.security_event("неудачная попытка входа", user_id=789, details="Неверный токен")
    
    print("\n✅ Тестирование завершено!")