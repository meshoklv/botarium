import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from config import logger

class Database:
    def __init__(self, db_path: str = "salon.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """Create database connection"""
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Clients table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Bookings table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            service TEXT NOT NULL,
            master TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
        ''')

        # Conversation history table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
        ''')

        # Temporary booking data (for collecting booking info during conversation)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS temp_booking_data (
            telegram_id INTEGER PRIMARY KEY,
            service TEXT,
            master TEXT,
            date TEXT,
            time TEXT,
            client_name TEXT,
            phone TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    # Client methods
    def get_or_create_client(self, telegram_id: int, first_name: str = None,
                            last_name: str = None, username: str = None) -> int:
        """Get existing client or create new one"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM clients WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()

        if result:
            client_id = result[0]
        else:
            cursor.execute('''
            INSERT INTO clients (telegram_id, first_name, last_name, username)
            VALUES (?, ?, ?, ?)
            ''', (telegram_id, first_name, last_name, username))
            client_id = cursor.lastrowid
            conn.commit()

        conn.close()
        return client_id

    def update_client_phone(self, telegram_id: int, phone: str):
        """Update client phone number"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE clients SET phone = ? WHERE telegram_id = ?', (phone, telegram_id))
        conn.commit()
        conn.close()

    def get_client(self, telegram_id: int) -> Optional[Dict]:
        """Get client by telegram_id"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM clients WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'id': result[0],
                'telegram_id': result[1],
                'first_name': result[2],
                'last_name': result[3],
                'username': result[4],
                'phone': result[5],
                'created_at': result[6]
            }
        return None

    # Conversation history methods
    def add_message(self, telegram_id: int, role: str, message: str):
        """Add message to conversation history"""
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO conversation_history (client_id, role, message)
        VALUES (?, ?, ?)
        ''', (client_id, role, message))
        conn.commit()
        conn.close()

    def get_conversation_history(self, telegram_id: int, limit: int = 10) -> List[Dict]:
        """Get recent conversation history"""
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT role, message, timestamp
        FROM conversation_history
        WHERE client_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (client_id, limit))
        results = cursor.fetchall()
        conn.close()

        history = []
        for row in reversed(results):
            history.append({
                'role': row[0],
                'message': row[1],
                'timestamp': row[2]
            })
        return history

    def clear_conversation_history(self, telegram_id: int):
        """Clear conversation history for user"""
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM conversation_history WHERE client_id = ?', (client_id,))
        conn.commit()
        conn.close()

    # Temporary booking data methods
    def save_temp_booking(self, telegram_id: int, data: Dict):
        """Save temporary booking data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM temp_booking_data WHERE telegram_id = ?', (telegram_id,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute('''
            UPDATE temp_booking_data
            SET service = ?, master = ?, date = ?, time = ?, client_name = ?, phone = ?, updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            ''', (data.get('service'), data.get('master'), data.get('date'),
                  data.get('time'), data.get('client_name'), data.get('phone'), telegram_id))
        else:
            cursor.execute('''
            INSERT INTO temp_booking_data (telegram_id, service, master, date, time, client_name, phone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (telegram_id, data.get('service'), data.get('master'), data.get('date'),
                  data.get('time'), data.get('client_name'), data.get('phone')))

        conn.commit()
        conn.close()

    def get_temp_booking(self, telegram_id: int) -> Optional[Dict]:
        """Get temporary booking data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM temp_booking_data WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'service': result[1],
                'master': result[2],
                'date': result[3],
                'time': result[4],
                'client_name': result[5],
                'phone': result[6]
            }
        return None

    def clear_temp_booking(self, telegram_id: int):
        """Clear temporary booking data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM temp_booking_data WHERE telegram_id = ?', (telegram_id,))
        conn.commit()
        conn.close()

    # Booking methods
    def create_booking(self, telegram_id: int, service: str, master: str,
                      date: str, time: str, client_name: str, phone: str, notes: str = None) -> int:
        """Create a new booking"""
        client_id = self.get_or_create_client(telegram_id)

        # Update client name and phone if provided
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
        UPDATE clients
        SET first_name = ?, phone = ?
        WHERE telegram_id = ?
        ''', (client_name, phone, telegram_id))

        cursor.execute('''
        INSERT INTO bookings (client_id, service, master, date, time, status, notes)
        VALUES (?, ?, ?, ?, ?, 'confirmed', ?)
        ''', (client_id, service, master, date, time, notes))

        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Booking created: ID={booking_id}, Client={telegram_id}")
        return booking_id

    def get_client_bookings(self, telegram_id: int) -> List[Dict]:
        """Get all bookings for a client"""
        client_id = self.get_or_create_client(telegram_id)
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
        SELECT id, service, master, date, time, status, notes, created_at
        FROM bookings
        WHERE client_id = ?
        ORDER BY date DESC, time DESC
        ''', (client_id,))

        results = cursor.fetchall()
        conn.close()

        bookings = []
        for row in results:
            bookings.append({
                'id': row[0],
                'service': row[1],
                'master': row[2],
                'date': row[3],
                'time': row[4],
                'status': row[5],
                'notes': row[6],
                'created_at': row[7]
            })
        return bookings

    def cancel_booking(self, booking_id: int):
        """Cancel a booking"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        conn.commit()
        conn.close()


# Global database instance
db = Database()
