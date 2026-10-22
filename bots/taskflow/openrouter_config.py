"""OpenRouter settings, read from the environment (see .env.example)."""
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/meshoklv/botarium",
    "X-Title": "TaskFlow Bot",
}

REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Sampling settings passed to the model
OPENROUTER_SETTINGS = {
    "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "1000")),
    "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.3")),
    "top_p": 0.9,
}

LOG_REQUESTS = True
LOG_RESPONSES = True


def validate_config():
    """Fail early with a readable message if the key/model/base URL are missing."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set (see .env.example)")
    if not OPENROUTER_MODEL:
        raise ValueError("OPENROUTER_MODEL is not set")
    if not OPENROUTER_BASE_URL:
        raise ValueError("OPENROUTER_BASE_URL is not set")
    return True


def get_headers():
    """Request headers (copy)."""
    return OPENROUTER_HEADERS.copy()
