"""Модуль для форматирования текста в сообщениях Telegram бота"""

from typing import Optional
from enum import Enum

class FormattingStyle(Enum):
    """Стили форматирования текста"""
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    STRIKETHROUGH = "strikethrough"
    SPOILER = "spoiler"
    CODE = "code"
    PRE = "pre"
    BLOCKQUOTE = "blockquote"

class TextFormatter:
    """Класс для форматирования текста в различных стилях"""
    
    @staticmethod
    def bold(text: str) -> str:
        """Сделать текст жирным"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def italic(text: str) -> str:
        """Сделать текст курсивом"""
        return f"<i>{text}</i>"
    
    @staticmethod
    def underline(text: str) -> str:
        """Сделать текст подчеркнутым"""
        return f"<u>{text}</u>"
    
    @staticmethod
    def strikethrough(text: str) -> str:
        """Сделать текст зачеркнутым"""
        return f"<s>{text}</s>"
    
    @staticmethod
    def spoiler(text: str) -> str:
        """Сделать текст спойлером"""
        return f"<tg-spoiler>{text}</tg-spoiler>"
    
    @staticmethod
    def code(text: str) -> str:
        """Сделать текст моноширинным (inline code)"""
        return f"<code>{text}</code>"
    
    @staticmethod
    def pre(text: str, language: Optional[str] = None) -> str:
        """Сделать текст блоком кода"""
        if language:
            return f'<pre><code class="language-{language}">{text}</code></pre>'
        return f"<pre>{text}</pre>"
    
    @staticmethod
    def blockquote(text: str) -> str:
        """Сделать текст цитатой"""
        return f"<blockquote>{text}</blockquote>"
    
    @staticmethod
    def url(text: str, url: str) -> str:
        """Сделать текст ссылкой"""
        return f'<a href="{url}">{text}</a>'
    
    @staticmethod
    def mention(text: str, user_id: int) -> str:
        """Сделать текст упоминанием пользователя"""
        return f'<a href="tg://user?id={user_id}">{text}</a>'
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Экранировать специальные HTML символы"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    @staticmethod
    def format_text(text: str, styles: list) -> str:
        """Применить несколько стилей к тексту"""
        formatted_text = text
        # Применяем стили в обратном порядке для правильной вложенности
        for style in reversed(styles):
            if style == FormattingStyle.BOLD:
                formatted_text = TextFormatter.bold(formatted_text)
            elif style == FormattingStyle.ITALIC:
                formatted_text = TextFormatter.italic(formatted_text)
            elif style == FormattingStyle.UNDERLINE:
                formatted_text = TextFormatter.underline(formatted_text)
            elif style == FormattingStyle.STRIKETHROUGH:
                formatted_text = TextFormatter.strikethrough(formatted_text)
            elif style == FormattingStyle.SPOILER:
                formatted_text = TextFormatter.spoiler(formatted_text)
            elif style == FormattingStyle.CODE:
                formatted_text = TextFormatter.code(formatted_text)
        return formatted_text

# Глобальные функции для удобного использования
def bold(text: str) -> str:
    """Сделать текст жирным"""
    return TextFormatter.bold(text)

def italic(text: str) -> str:
    """Сделать текст курсивом"""
    return TextFormatter.italic(text)

def underline(text: str) -> str:
    """Сделать текст подчеркнутым"""
    return TextFormatter.underline(text)

def strikethrough(text: str) -> str:
    """Сделать текст зачеркнутым"""
    return TextFormatter.strikethrough(text)

def spoiler(text: str) -> str:
    """Сделать текст спойлером"""
    return TextFormatter.spoiler(text)

def code(text: str) -> str:
    """Сделать текст моноширинным (inline code)"""
    return TextFormatter.code(text)

def pre(text: str, language: Optional[str] = None) -> str:
    """Сделать текст блоком кода"""
    return TextFormatter.pre(text, language)

def blockquote(text: str) -> str:
    """Сделать текст цитатой"""
    return TextFormatter.blockquote(text)

def url(text: str, url_str: str) -> str:
    """Сделать текст ссылкой"""
    return TextFormatter.url(text, url_str)

def mention(text: str, user_id: int) -> str:
    """Сделать текст упоминанием пользователя"""
    return TextFormatter.mention(text, user_id)

def escape_html(text: str) -> str:
    """Экранировать специальные HTML символы"""
    return TextFormatter.escape_html(text)