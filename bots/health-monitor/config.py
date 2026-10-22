import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Telegram. CHAT_ID is the only chat the bot talks to (your own numeric Telegram id).
BOT_TOKEN = os.getenv("HEALTH_BOT_TOKEN", os.getenv("BOT_TOKEN", ""))
CHAT_ID = int(os.getenv("CHAT_ID", "0") or 0)

# Phone over SSH (Termux reverse tunnel). PHONE_SSH_HOST is an alias from ~/.ssh/config.
PHONE_SSH_HOST = os.getenv("PHONE_SSH_HOST", "phone")
PHONE_HOST = os.getenv("PHONE_HOST", "localhost")
PHONE_PORT = int(os.getenv("PHONE_PORT", "8022"))
PHONE_USER = os.getenv("PHONE_USER", "u0_a")  # Termux default user

# Gadgetbridge DB path on phone
GB_DB_PATH = os.getenv("GB_DB_PATH", "/data/data/nodomain.freeyourgadget.gadgetbridge/databases/Gadgetbridge")

# Local paths. Drop an exported Gadgetbridge.db at LOCAL_DB_PATH to run without a phone.
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", os.path.join(DATA_DIR, "gadgetbridge.db"))

# Analysis backend: "cli" (local `claude` CLI) or "api" (Anthropic API, needs ANTHROPIC_API_KEY)
ANALYZER = os.getenv("ANALYZER", "cli").lower()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")  # alias used by the CLI
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")  # id used by the API

# Who the report is about. Free text, shown to the model; norms are adapted to it.
USER_PROFILE = os.getenv("USER_PROFILE", "Adult, 30 years old, 175 cm, 70 kg.")
