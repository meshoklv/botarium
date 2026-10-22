"""
Database manager for persistent storage
"""

import sqlite3
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path
from zoneinfo import ZoneInfo
from config import ADMIN_USER_ID, DAILY_LIMIT_FREE, DAILY_LIMIT_PLUS, DAILY_LIMIT_ULTRA, TIMEZONE

_logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for user data persistence"""

    def __init__(self, db_path: str = "banana_studio.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Users table - stores authentication and limits
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    authenticated INTEGER DEFAULT 0,
                    premium INTEGER DEFAULT 0,
                    photos_generated_today INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    subscription TEXT DEFAULT 'free',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Generation stats table - per generation event (for daily stats)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS generation_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    created_at TEXT
                )
            """)

            conn.commit()
            _logger.info("Database initialized successfully")

            # Migrations: add missing columns
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            if "subscription" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN subscription TEXT DEFAULT 'free'")
                conn.commit()
            if "subscription_expires_at" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN subscription_expires_at TEXT")
                conn.commit()

    def get_user(self, user_id: int) -> Optional[dict]:
        """Get user data from database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: int):
        """Create new user record"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,)
            )
            conn.commit()

    def set_authenticated(self, user_id: int, authenticated: bool):
        """Set user authentication status"""
        self.create_user(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET authenticated = ? WHERE user_id = ?",
                (1 if authenticated else 0, user_id)
            )
            conn.commit()

    def is_authenticated(self, user_id: int) -> bool:
        """Check if user is authenticated"""
        user = self.get_user(user_id)
        return bool(user and user['authenticated']) if user else False

    def set_premium(self, user_id: int, premium: bool):
        """Set user premium status"""
        self.create_user(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET premium = ? WHERE user_id = ?",
                (1 if premium else 0, user_id)
            )
            conn.commit()

    def is_premium(self, user_id: int) -> bool:
        """Check if user has premium access"""
        user = self.get_user(user_id)
        return bool(user and user['premium']) if user else False

    def increment_photos_count(self, user_id: int):
        """Increment photos generated today counter"""
        self.create_user(user_id)
        today = self._today_moscow()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get current data
            user = self.get_user(user_id)

            if not user or user['last_reset_date'] != today:
                # Reset counter for new day
                cursor.execute(
                    "UPDATE users SET photos_generated_today = 1, last_reset_date = ? WHERE user_id = ?",
                    (today, user_id)
                )
            else:
                # Increment counter
                cursor.execute(
                    "UPDATE users SET photos_generated_today = photos_generated_today + 1 WHERE user_id = ?",
                    (user_id,)
                )

            # Record generation event for stats
            cursor.execute(
                "INSERT INTO generation_stats (user_id, created_at) VALUES (?, ?)",
                (user_id, today)
            )

            conn.commit()

    def get_photos_count(self, user_id: int) -> int:
        """Get number of photos generated today"""
        today = self._today_moscow()
        user = self.get_user(user_id)

        if not user:
            return 0

        # Reset if it's a new day
        if user['last_reset_date'] != today:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET photos_generated_today = 0, last_reset_date = ? WHERE user_id = ?",
                    (today, user_id)
                )
                conn.commit()
            return 0

        return user['photos_generated_today']

    def get_daily_limit(self, user_id: int) -> int:
        """Get daily photo limit for user"""
        if self.is_admin(user_id):
            return 1_000_000_000
        today = self._today_moscow()
        sub = self.get_subscription(user_id)
        exp = self.get_subscription_expires_at(user_id)
        if exp and exp < today and sub != 'free':
            self.cancel_subscription(user_id)
            sub = 'free'
        if sub == 'ultra':
            return DAILY_LIMIT_ULTRA
        if sub == 'plus':
            return DAILY_LIMIT_PLUS
        return DAILY_LIMIT_FREE

    def can_generate(self, user_id: int) -> bool:
        """Check if user can generate more photos today"""
        if self.is_admin(user_id):
            return True
        photos_count = self.get_photos_count(user_id)
        limit = self.get_daily_limit(user_id)
        return photos_count < limit

    def set_subscription(self, user_id: int, subscription: str):
        self.create_user(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET subscription = ? WHERE user_id = ?",
                (subscription, user_id)
            )
            conn.commit()

    def cancel_subscription(self, user_id: int):
        self.create_user(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET subscription = 'free', subscription_expires_at = NULL WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()

    def get_subscription(self, user_id: int) -> str:
        user = self.get_user(user_id)
        return (user.get('subscription') if user else 'free') or 'free'

    def get_subscription_expires_at(self, user_id: int) -> Optional[str]:
        user = self.get_user(user_id)
        return user.get('subscription_expires_at') if user else None

    def set_subscription_expires_at(self, user_id: int, expires_at: Optional[str]):
        self.create_user(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET subscription_expires_at = ? WHERE user_id = ?",
                (expires_at, user_id)
            )
            conn.commit()

    def add_subscription_days(self, user_id: int, days: int) -> Optional[str]:
        self.create_user(user_id)
        today = self._today_moscow()
        current = self.get_subscription_expires_at(user_id)
        base = current if current and current >= today else today
        tz = ZoneInfo(TIMEZONE)
        d = datetime.fromisoformat(base).date()
        new_d = d + timedelta(days=days)
        new_str = new_d.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET subscription_expires_at = ? WHERE user_id = ?",
                (new_str, user_id)
            )
            conn.commit()
        return new_str

    def get_total_users(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def delete_user(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM generation_stats WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_all_user_ids(self) -> List[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            rows = cursor.fetchall()
            return [int(r[0]) for r in rows]

    def get_user_ids_premium(self) -> List[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE premium = 1")
            rows = cursor.fetchall()
            return [int(r[0]) for r in rows]

    def get_user_ids_subscriptions(self) -> List[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE subscription IN ('plus','ultra')")
            rows = cursor.fetchall()
            return [int(r[0]) for r in rows]

    def get_total_photos_today(self) -> int:
        today = self._today_moscow()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM generation_stats WHERE created_at = ?", (today,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_daily_stats(self, days: int = 7) -> List[Tuple[str, int]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT created_at, COUNT(*) FROM generation_stats GROUP BY created_at ORDER BY created_at DESC LIMIT ?",
                (days,)
            )
            rows = cursor.fetchall()
            return [(r[0], int(r[1])) for r in rows]

    def is_admin(self, user_id: int) -> bool:
        return user_id == ADMIN_USER_ID

    def _today_moscow(self) -> str:
        tz = ZoneInfo(TIMEZONE)
        return datetime.now(tz).date().isoformat()


# Global database instance
db = Database()
