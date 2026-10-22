"""
Configuration for the banana-studio bot (Nano Banana image generation)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

# KIE.AI API Configuration
KIE_API_KEY = os.getenv("KIE_API_KEY")
KIE_API_URL = os.getenv("KIE_API_URL", "https://api.kie.ai")
if not KIE_API_KEY:
    raise ValueError("KIE_API_KEY not found in environment variables")

# Admin Configuration
# Telegram numeric id of the bot admin (statistics, grants, broadcasts). 0 = no admin.
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0") or 0)
# Username (without @) shown to users as the support contact
ADMIN_CONTACT_USERNAME = os.getenv("ADMIN_CONTACT_USERNAME", "your_support_username")

# Demo / Fake stats toggle
USE_FAKE_STATS = os.getenv("USE_FAKE_STATS", "false").lower() in ("1", "true", "yes", "y")

# Test broadcast recipients
TEST_USER_IDS = [
    int(x) for x in os.getenv("TEST_USER_IDS", "").replace(" ", "").split(",") if x
]

# Bot Settings
DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "1:1")
MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
GENERATION_TIMEOUT_SECONDS = int(os.getenv("GENERATION_TIMEOUT_SECONDS", "120"))

# Nano Banana Models
MODEL_GENERATE = "google/nano-banana"
MODEL_EDIT = "google/nano-banana-edit"

# Aspect Ratios
ASPECT_RATIOS = {
    "1:1": "1:1",
    "9:16": "9:16 (портрет)",
    "16:9": "16:9 (пейзаж)",
    "3:4": "3:4",
    "4:3": "4:3",
    "3:2": "3:2",
    "2:3": "2:3",
    "5:4": "5:4",
    "4:5": "4:5",
    "21:9": "21:9 (ультраширокий)",
    "auto": "auto (автоопределение)",
}

# Output Formats
OUTPUT_FORMATS = {
    "png": "PNG",
    "jpeg": "JPEG",
}

# Mode Prompts - structured prompts for different modes
MODE_PROMPTS = {
    "generate": {
        "system": """Ты помогаешь пользователю создавать изображения через AI.

Твоя задача - принять описание от пользователя и передать его в модель генерации.

Правила:
- Не изменяй промпт пользователя
- Не добавляй лишние детали
- Просто передай промпт как есть
""",
        "user_template": "{prompt}",
    },
    "edit": {
        "system": """Ты помогаешь редактировать изображения через AI.

Правила:
- Пользователь описывает, что нужно изменить
- Передай инструкции в модель редактирования
- Не изменяй промпт пользователя
""",
        "user_template": "{prompt}",
    },
    "reference": {
        "system": """Ты помогаешь применить стиль из референсного изображения к основному.

Входные данные:
- [SOURCE_IMAGE] - основное изображение, которое нужно изменить
- [REFERENCE_IMAGE] - изображение, откуда берётся стиль

Задача:
- Применить стиль, цветовую палитру и настроение из REFERENCE к SOURCE
- Сохранить основную композицию SOURCE
""",
        "user_template": """[SOURCE_IMAGE]: {source_description}
[REFERENCE_IMAGE]: {reference_description}

Apply the style, color palette, and mood from the reference image to the source image. {additional_instructions}""",
    },
}

POLLING_INTERVAL = 1
POLLING_MAX_ATTEMPTS = 90

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Subscription limits
DAILY_LIMIT_FREE = int(os.getenv("DAILY_LIMIT_FREE", "5"))
DAILY_LIMIT_PLUS = int(os.getenv("DAILY_LIMIT_PLUS", "15"))
DAILY_LIMIT_ULTRA = int(os.getenv("DAILY_LIMIT_ULTRA", "40"))
