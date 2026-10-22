import sqlite3
import shutil
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import logger, REMINDERS_DB_NAME


class Database:
    """Low-level database helper for reminder bot."""

    def __init__(self, db_path: str = REMINDERS_DB_NAME):
        self.db_path = db_path
        self.backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        self._ensure_backup_dir()
        self.init_db()

    def _ensure_backup_dir(self):
        """Create backups directory if it doesn't exist."""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
            logger.info(f"Created backup directory: {self.backup_dir}")

    def create_backup(self, reason: str = "manual") -> str:
        """Create a backup of the database before migrations."""
        if not os.path.exists(self.db_path):
            logger.warning("Database file doesn't exist, skipping backup")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"reminders_backup_{timestamp}_{reason}.db"
        backup_path = os.path.join(self.backup_dir, backup_name)

        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backed up to: {backup_path}")

            # Keep only last 10 backups
            self._cleanup_old_backups(keep_last=10)
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return ""

    def _cleanup_old_backups(self, keep_last: int = 10):
        """Remove old backups, keeping only the most recent ones."""
        try:
            backups = sorted([
                f for f in os.listdir(self.backup_dir)
                if f.startswith("reminders_backup_") and f.endswith(".db")
            ])

            if len(backups) > keep_last:
                for old_backup in backups[:-keep_last]:
                    old_path = os.path.join(self.backup_dir, old_backup)
                    os.remove(old_path)
                    logger.info(f"Removed old backup: {old_backup}")
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        # Create backup before any schema changes
        if os.path.exists(self.db_path):
            self.create_backup("schema_migration")

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                timezone TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Backward compatibility: add timezone column if missing
        try:
            cursor.execute("ALTER TABLE clients ADD COLUMN timezone TEXT")
            logger.info("Added timezone column to clients table")
        except sqlite3.OperationalError:
            pass

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                original_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                escalation_level INTEGER DEFAULT 0,
                last_escalation_at TEXT,
                spam_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES clients (id)
            )
            """
        )

        # Add escalation columns if they don't exist
        try:
            cursor.execute("ALTER TABLE reminders ADD COLUMN escalation_level INTEGER DEFAULT 0")
            logger.info("Added escalation_level column to reminders table")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE reminders ADD COLUMN last_escalation_at TEXT")
            logger.info("Added last_escalation_at column to reminders table")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE reminders ADD COLUMN spam_count INTEGER DEFAULT 0")
            logger.info("Added spam_count column to reminders table")
        except sqlite3.OperationalError:
            pass

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                aggression_level INTEGER NOT NULL,
                FOREIGN KEY (reminder_id) REFERENCES reminders (id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_reminder_data (
                telegram_id INTEGER PRIMARY KEY,
                task TEXT,
                datetime TEXT,
                datetime_human TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_state (
                telegram_id INTEGER PRIMARY KEY,
                is_offended INTEGER DEFAULT 0,
                offended_at TEXT,
                offended_reminder_id INTEGER
            )
            """
        )

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def get_or_create_client(
        self,
        telegram_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
    ) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clients WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        if row:
            client_id = row["id"]
        else:
            cursor.execute(
                """
                INSERT INTO clients (telegram_id, first_name, last_name, username)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, first_name, last_name, username),
            )
            client_id = cursor.lastrowid
            conn.commit()
        conn.close()
        return client_id

    def add_message(self, telegram_id: int, role: str, message: str) -> None:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversation_history (client_id, role, message)
            VALUES (?, ?, ?)
            """,
            (client_id, role, message),
        )
        conn.commit()
        conn.close()

    def get_conversation_history(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, message, timestamp
            FROM conversation_history
            WHERE client_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (client_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {"role": row["role"], "message": row["message"], "timestamp": row["timestamp"]}
            for row in reversed(rows)
        ]

    def clear_conversation_history(self, telegram_id: int) -> None:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE client_id = ?", (client_id,))
        conn.commit()
        conn.close()

    def cleanup_old_conversation_history(self, telegram_id: int, keep_last_n: int = 20) -> None:
        """Keep only the last N messages in conversation history."""
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM conversation_history
            WHERE client_id = ?
            AND id NOT IN (
                SELECT id FROM conversation_history
                WHERE client_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )
            """,
            (client_id, client_id, keep_last_n),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info("Cleaned up %s old messages for user %s", deleted, telegram_id)

    def save_temp_reminder(self, telegram_id: int, data: Dict[str, Any]) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT telegram_id FROM temp_reminder_data WHERE telegram_id = ?",
            (telegram_id,),
        )
        exists = cursor.fetchone()

        if exists:
            cursor.execute(
                """
                UPDATE temp_reminder_data
                SET task = ?, datetime = ?, datetime_human = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (
                    data.get("task"),
                    data.get("datetime"),
                    data.get("datetime_human"),
                    telegram_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO temp_reminder_data (telegram_id, task, datetime, datetime_human)
                VALUES (?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    data.get("task"),
                    data.get("datetime"),
                    data.get("datetime_human"),
                ),
            )

        conn.commit()
        conn.close()

    def get_temp_reminder(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT task, datetime, datetime_human
            FROM temp_reminder_data
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "task": row["task"],
            "datetime": row["datetime"],
            "datetime_human": row["datetime_human"],
        }

    def clear_temp_reminder(self, telegram_id: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM temp_reminder_data WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        conn.close()

    def update_client_timezone(self, telegram_id: int, timezone: Optional[str]) -> None:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE clients
            SET timezone = ?
            WHERE id = ?
            """,
            (timezone, client_id),
        )
        conn.commit()
        conn.close()

    def get_client_timezone(self, telegram_id: int) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timezone FROM clients WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
        return None

    def create_reminder(self, telegram_id: int, task: str, scheduled_time: str, original_time: str) -> int:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reminders (user_id, task, scheduled_time, original_time)
            VALUES (?, ?, ?, ?)
            """,
            (client_id, task, scheduled_time, original_time),
        )
        reminder_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info("Reminder created: ID=%s for user=%s", reminder_id, telegram_id)
        return reminder_id

    def get_reminder(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.*, c.telegram_id
            FROM reminders r
            JOIN clients c ON c.id = r.user_id
            WHERE r.id = ?
            """,
            (reminder_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user_reminders(self, telegram_id: int) -> List[Dict[str, Any]]:
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM reminders
            WHERE user_id = ?
            ORDER BY scheduled_time ASC
            """,
            (client_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_reminder_status(self, reminder_id: int, status: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reminders
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, reminder_id),
        )
        conn.commit()
        conn.close()

    def update_reminder_time(self, reminder_id: int, new_time: str, original_time: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reminders
            SET scheduled_time = ?, original_time = ?, status = 'pending', attempts = 0, last_attempt_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_time, original_time, reminder_id),
        )
        conn.commit()
        conn.close()

    def delete_reminder(self, reminder_id: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        cursor.execute("DELETE FROM reminder_attempts WHERE reminder_id = ?", (reminder_id,))
        conn.commit()
        conn.close()

    def record_attempt(self, reminder_id: int, attempt_number: int, sent_at: str, aggression_level: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reminder_attempts (reminder_id, attempt_number, sent_at, aggression_level)
            VALUES (?, ?, ?, ?)
            """,
            (reminder_id, attempt_number, sent_at, aggression_level),
        )
        conn.commit()
        conn.close()

    def bump_attempt(self, reminder_id: int, attempts: int, sent_at: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reminders
            SET attempts = ?, last_attempt_at = ?, updated_at = CURRENT_TIMESTAMP,
                status = CASE WHEN ? < 3 THEN 'awaiting_confirmation' ELSE status END
            WHERE id = ?
            """,
            (attempts, sent_at, attempts, reminder_id),
        )
        conn.commit()
        conn.close()

    def get_pending_and_waiting_reminders(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.*, c.telegram_id
            FROM reminders r
            JOIN clients c ON c.id = r.user_id
            WHERE r.status IN ('pending', 'awaiting_confirmation', 'sent')
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_escalation_level(self, reminder_id: int, level: int, timestamp: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reminders
            SET escalation_level = ?, last_escalation_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (level, timestamp, reminder_id),
        )
        conn.commit()
        conn.close()

    def increment_spam_count(self, reminder_id: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reminders
            SET spam_count = spam_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (reminder_id,),
        )
        conn.commit()
        conn.close()

    def set_user_offended(self, telegram_id: int, offended: bool = True, reminder_id: Optional[int] = None) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        if offended:
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_state (telegram_id, is_offended, offended_at, offended_reminder_id)
                VALUES (?, 1, ?, ?)
                """,
                (telegram_id, datetime.now().isoformat(), reminder_id),
            )
        else:
            cursor.execute(
                """
                UPDATE user_state
                SET is_offended = 0, offended_at = NULL, offended_reminder_id = NULL
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
        conn.commit()
        conn.close()

    def is_user_offended(self, telegram_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_offended FROM user_state WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return bool(row and row[0] == 1)

    def get_offended_time(self, telegram_id: int) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT offended_at FROM user_state WHERE telegram_id = ? AND is_offended = 1",
            (telegram_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


# Global database instance
db = Database()
