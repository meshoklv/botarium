from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import SERVICES, MASTERS, WORKING_HOURS_START, WORKING_HOURS_END, logger
from services.database import db


class BookingService:
    """Service for managing bookings and availability"""

    @staticmethod
    def get_available_time_slots(date_str: str, master: str = None, duration: int = 60) -> List[str]:
        """
        Get available time slots for a given date and master

        Args:
            date_str: Date in YYYY-MM-DD format
            master: Master name (optional)
            duration: Service duration in minutes

        Returns:
            List of available time slots in HH:MM format
        """
        try:
            # Generate all possible slots
            all_slots = []
            current_hour = WORKING_HOURS_START

            while current_hour < WORKING_HOURS_END:
                all_slots.append(f"{current_hour:02d}:00")
                current_hour += 1

            # TODO: Filter out booked slots from database
            # For demo purposes, return all slots
            return all_slots

        except Exception as e:
            logger.error(f"Error getting available slots: {e}")
            return []

    @staticmethod
    def find_service_by_name(service_name: str) -> Optional[Dict]:
        """Find service by name (fuzzy match)"""
        service_name_lower = service_name.lower()

        for service in SERVICES:
            if service_name_lower in service['name'].lower():
                return service

        return None

    @staticmethod
    def find_master_by_name(master_name: str) -> Optional[Dict]:
        """Find master by name (fuzzy match)"""
        master_name_lower = master_name.lower()

        for master in MASTERS:
            if master_name_lower in master['name'].lower():
                return master

        return None

    @staticmethod
    def format_booking_confirmation(booking_data: Dict) -> str:
        """Format beautiful booking confirmation message"""
        service_info = BookingService.find_service_by_name(booking_data.get('service', ''))
        price = service_info['price'] if service_info else "уточняется"

        # Parse date
        try:
            date_obj = datetime.strptime(booking_data['date'], '%Y-%m-%d')
            date_formatted = date_obj.strftime('%d %B %Y')

            # Russian month names
            months_ru = {
                'January': 'января', 'February': 'февраля', 'March': 'марта',
                'April': 'апреля', 'May': 'мая', 'June': 'июня',
                'July': 'июля', 'August': 'августа', 'September': 'сентября',
                'October': 'октября', 'November': 'ноября', 'December': 'декабря'
            }
            for eng, ru in months_ru.items():
                date_formatted = date_formatted.replace(eng, ru)

        except:
            date_formatted = booking_data['date']

        # Handle master field - if None or empty, show "Любой свободный мастер"
        master_display = booking_data.get('master') or 'Любой свободный мастер'

        message = f"<b>Запись создана!</b>\n\n"
        message += f"<b>Услуга:</b> {booking_data.get('service', 'Не указано')}\n"
        message += f"<b>Мастер:</b> {master_display}\n"
        message += f"<b>Дата:</b> {date_formatted}\n"
        message += f"<b>Время:</b> {booking_data.get('time', 'Не указано')}\n"
        message += f"<b>Имя:</b> {booking_data.get('client_name', 'Не указано')}\n"
        message += f"<b>Телефон:</b> {booking_data.get('phone', 'Не указано')}\n"

        if isinstance(price, int):
            message += f"<b>Стоимость:</b> {price}₽\n"

        return message

    @staticmethod
    def create_booking(telegram_id: int, booking_data: Dict) -> int:
        """Create booking in database"""
        booking_id = db.create_booking(
            telegram_id=telegram_id,
            service=booking_data['service'],
            master=booking_data['master'],
            date=booking_data['date'],
            time=booking_data['time'],
            client_name=booking_data['client_name'],
            phone=booking_data['phone']
        )
        return booking_id

    @staticmethod
    def get_upcoming_bookings(telegram_id: int) -> List[Dict]:
        """Get upcoming bookings for a client"""
        all_bookings = db.get_client_bookings(telegram_id)

        # Filter only confirmed bookings
        upcoming = [b for b in all_bookings if b['status'] == 'confirmed']

        return upcoming


# Global service instance
booking_service = BookingService()
