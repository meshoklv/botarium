"""Database settings, read from the environment (see .env.example).

Set DATABASE_URL (e.g. postgresql://user:pass@host:5432/dbname) or the DB_* parts.
"""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL and os.getenv("DB_HOST"):
    DATABASE_URL = "postgresql://{user}:{password}@{host}:{port}/{name}".format(
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        name=os.getenv("DB_NAME", "postgres"),
    )
