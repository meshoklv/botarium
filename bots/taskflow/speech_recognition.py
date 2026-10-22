import os
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import aiofiles
import aiohttp
from telegram import File
from text_processor import process_text

logger = logging.getLogger(__name__)

class SpeechRecognizer:
    """
    Класс для распознавания речи с использованием Whisper.cpp
    Оптимизирован для серверов с ограниченной памятью (2GB RAM)
    """
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path or os.getenv("WHISPER_MODEL_PATH", "./models/ggml-base.bin")
        self.whisper_cpp_path = os.getenv("WHISPER_CLI_PATH", "./whisper.cpp/build/bin/whisper-cli")  # Путь к исполняемому файлу whisper.cpp
        self.temp_dir = Path(tempfile.gettempdir()) / "voice_recognition"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Проверка наличия модели и whisper.cpp
        self._check_dependencies()
    
    def _check_dependencies(self) -> None:
        """Проверить наличие необходимых зависимостей"""
        if not Path(self.model_path).exists():
            logger.warning(f"Модель Whisper не найдена - model_path: {self.model_path} - operation: dependency_check")
            logger.info(f"Для установки модели выполните: make download-model - operation: dependency_help")
        
        if not Path(self.whisper_cpp_path).exists():
            logger.warning(f"Whisper.cpp не найден - whisper_path: {self.whisper_cpp_path} - operation: dependency_check")
            logger.info(f"Для установки whisper.cpp выполните: make install-whisper - operation: dependency_help")
    
    async def download_voice_file(self, voice_file: File, file_id: str) -> Optional[str]:
        """
        Скачать голосовой файл из Telegram
        
        Args:
            voice_file: Объект файла из Telegram
            file_id: ID файла
            
        Returns:
            Путь к скачанному файлу или None при ошибке
        """
        try:
            # Создаем временный файл
            temp_file_path = self.temp_dir / f"voice_{file_id}.ogg"
            
            # Скачиваем файл
            await voice_file.download_to_drive(str(temp_file_path))
            
            logger.info(f"Голосовой файл скачан - file_path: {str(temp_file_path)} - file_id: {file_id} - operation: voice_download")
            return str(temp_file_path)
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании голосового файла - error: {str(e)} - file_id: {file_id} - operation: voice_download_error")
            return None
    
    async def convert_to_wav(self, input_path: str) -> Optional[str]:
        """
        Конвертировать аудиофайл в WAV формат для whisper.cpp
        
        Args:
            input_path: Путь к входному файлу
            
        Returns:
            Путь к WAV файлу или None при ошибке
        """
        try:
            output_path = input_path.replace('.ogg', '.wav')
            
            # Используем ffmpeg для конвертации
            cmd = [
                'ffmpeg', '-i', input_path,
                '-ar', '16000',  # 16kHz sample rate для whisper
                '-ac', '1',      # моно
                '-c:a', 'pcm_s16le',  # 16-bit PCM
                '-y',            # перезаписать файл
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Файл конвертирован в WAV - output_path: {output_path} - operation: wav_conversion")
                return output_path
            else:
                logger.error(f"Ошибка конвертации - error: {stderr.decode()} - operation: wav_conversion_error")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации в WAV - error: {str(e)} - operation: wav_conversion_error")
            return None
    
    async def transcribe_audio(self, wav_path: str) -> Optional[str]:
        """
        Распознать речь из WAV файла с помощью Whisper.cpp
        
        Args:
            wav_path: Путь к WAV файлу
            
        Returns:
            Распознанный текст или None при ошибке
        """
        try:
            if not Path(self.whisper_cpp_path).exists():
                logger.error(f"Whisper.cpp не установлен - whisper_path: {self.whisper_cpp_path}, operation: transcription_check")
                return None
            
            if not Path(self.model_path).exists():
                logger.error(f"Модель Whisper не найдена - model_path: {self.model_path}, operation: transcription_check")
                return None
            
            # Команда для whisper.cpp с оптимизацией для низкого потребления памяти
            cmd = [
                self.whisper_cpp_path,
                '-m', self.model_path,
                '-f', wav_path,
                '--language', 'auto',  # автоопределение языка
                '--threads', '2',      # ограничиваем количество потоков
                '--no-timestamps',     # убираем временные метки для экономии памяти
                '--output-txt'         # вывод только текста
            ]
            
            logger.info(f"Запуск распознавания речи - command: {' '.join(cmd)} - wav_path: {wav_path} - operation: transcription_start")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Whisper.cpp выводит результат в stdout
                transcribed_text = stdout.decode('utf-8').strip()
                
                # Очищаем текст от служебной информации whisper
                lines = transcribed_text.split('\n')
                clean_text = ''
                for line in lines:
                    # Пропускаем строки с временными метками и служебной информацией
                    if not line.startswith('[') and not line.startswith('whisper_') and line.strip():
                        clean_text += line.strip() + ' '
                
                result = clean_text.strip()
                logger.info(f"Распознанный текст - text: {result} - wav_path: {wav_path} - operation: transcription_success")
                return result if result else None
            else:
                logger.error(f"Ошибка распознавания речи - error: {stderr.decode()} - wav_path: {wav_path} - operation: transcription_error")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при распознавании речи - error: {str(e)} - wav_path: {wav_path} - operation: transcription_error")
            return None
    
    async def cleanup_temp_files(self, *file_paths: str) -> None:
        """
        Удалить временные файлы
        
        Args:
            *file_paths: Пути к файлам для удаления
        """
        for file_path in file_paths:
            try:
                if file_path and Path(file_path).exists():
                    Path(file_path).unlink()
                    logger.debug(f"Удален временный файл - file_path: {file_path} - operation: cleanup")
            except Exception as e:
                logger.warning(f"Не удалось удалить файл - file_path: {file_path} - error: {str(e)} - operation: cleanup_error")
    
    async def recognize_voice_message(self, voice_file: File, file_id: str) -> Tuple[Optional[str], bool, Optional[Dict[str, Any]]]:
        """
        Полный цикл распознавания голосового сообщения с постобработкой
        
        Args:
            voice_file: Объект голосового файла из Telegram
            file_id: ID файла
            
        Returns:
            Tuple[сырой_текст, успешность_операции, обработанные_данные]
        """
        ogg_path = None
        wav_path = None
        
        try:
            # Скачиваем файл
            ogg_path = await self.download_voice_file(voice_file, file_id)
            if not ogg_path:
                return None, False, None
            
            # Конвертируем в WAV
            wav_path = await self.convert_to_wav(ogg_path)
            if not wav_path:
                return None, False, None
            
            # Распознаем речь
            raw_text = await self.transcribe_audio(wav_path)
            
            if not raw_text:
                return None, False, None
            
            logger.info(f"Сырой текст от Whisper - raw_text: {raw_text} - file_id: {file_id} - operation: whisper_result")
            
            # Постобработка текста с помощью OpenRouter
            try:
                processed_data = process_text(raw_text)
                if processed_data:
                    logger.info(f"Обработанная задача - title: {processed_data.get('title', 'Без названия')} - file_id: {file_id} - operation: text_processing_success")
                    return raw_text, True, processed_data
                else:
                    logger.warning(f"Не удалось обработать текст, используем сырой - file_id: {file_id} - operation: text_processing_fallback")
                    # Возвращаем базовую структуру если обработка не удалась
                    fallback_data = {
                        'title': raw_text[:100],
                        'description': raw_text,
                        'priority': None,
                        'deadline': None,
                        'category': None,
                        'tags': None,
                        'assigned_to': None,
                        'confidence': 0.5,
                        'original_text': raw_text,
                        'processing_error': 'API processing failed'
                    }
                    return raw_text, True, fallback_data
            except Exception as e:
                logger.error(f"Ошибка постобработки текста - error: {str(e)} - file_id: {file_id} - operation: text_processing_error")
                # Fallback - возвращаем сырой текст
                fallback_data = {
                    'title': raw_text[:100],
                    'description': raw_text,
                    'priority': None,
                    'deadline': None,
                    'category': None,
                    'tags': None,
                    'assigned_to': None,
                    'confidence': 0.3,
                    'original_text': raw_text,
                    'processing_error': str(e)
                }
                return raw_text, True, fallback_data
                
        except Exception as e:
            logger.error(f"Ошибка в процессе распознавания - error: {str(e)} - file_id: {file_id} - operation: recognition_error")
            return None, False, None
            
        finally:
            # Очищаем временные файлы
            await self.cleanup_temp_files(ogg_path, wav_path)
    
    def get_system_requirements_info(self) -> dict:
        """
        Получить информацию о системных требованиях
        
        Returns:
            Словарь с информацией о требованиях
        """
        return {
            "recommended_ram": "2GB+",
            "model_size": "~140MB (base model)",
            "runtime_memory": "~300-500MB",
            "cpu_requirements": "2+ cores recommended",
            "supported_formats": ["ogg", "wav", "mp3", "m4a"],
            "languages": "99+ languages (auto-detection)",
            "offline": True,
            "privacy": "Полностью локальная обработка"
        }

# Глобальный экземпляр для использования в боте
speech_recognizer = SpeechRecognizer()