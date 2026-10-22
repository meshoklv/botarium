from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

def create_main_keyboard():
    """Create the main keyboard with start session button"""
    keyboard = [
        [KeyboardButton("🎤 Начать новую историю")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def create_session_keyboard():
    """Create the session keyboard with end session button"""
    keyboard = [
        [KeyboardButton("✅ Закончить историю")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def create_summary_keyboard():
    """Create the summary keyboard with short summary and new session buttons"""
    keyboard = [
        [KeyboardButton("📄 Сделать еще короче")],
        [KeyboardButton("🎤 Начать новую историю")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def remove_keyboard():
    """Remove the keyboard"""
    return ReplyKeyboardRemove()

def format_session_status(message_count: int) -> str:
    """Format session status message"""
    if message_count == 0:
        return "📝 История начата! Отправляйте голосовые сообщения."
    elif message_count == 1:
        return f"📝 Получено {message_count} сообщение. Отправляйте еще или нажмите 'Закончить историю'."
    else:
        return f"📝 Получено {message_count} сообщений. Отправляйте еще или нажмите 'Закончить историю'."

def format_transcription_preview(transcription: str, max_length: int = 100) -> str:
    """Format transcription preview for user feedback"""
    if len(transcription) <= max_length:
        return transcription
    return transcription[:max_length] + "..."

def format_error_message(error_type: str) -> str:
    """Format error messages for users"""
    error_messages = {
        'transcription_failed': "❌ Не удалось транскрибировать голосовое сообщение. Попробуйте еще раз.",
        'summary_failed': "❌ Не удалось создать резюме. Попробуйте еще раз.",
        'no_active_session': "❌ У вас нет активной сессии. Нажмите 'Начать новую историю' для начала.",
        'no_voice_messages': "❌ В сессии нет голосовых сообщений для обработки.",
        'file_too_large': "❌ Файл слишком большой. Максимальный размер: 25 МБ.",
        'api_error': "❌ Ошибка API. Попробуйте позже.",
        'general_error': "❌ Произошла ошибка. Попробуйте еще раз."
    }
    return error_messages.get(error_type, error_messages['general_error'])
