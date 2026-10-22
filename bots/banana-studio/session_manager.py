"""
Session manager for tracking user state
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from modes import ModeType
from datetime import date
from db import db


@dataclass
class ImageData:
    """Data about uploaded image"""
    file_id: str  # Telegram file ID
    file_url: str  # Downloaded URL from Telegram
    role: Optional[str] = None  # "source" or "reference"
    description: Optional[str] = None  # Optional user description


@dataclass
class UserSession:
    """User session data (temporary, in-memory only)"""
    user_id: int
    current_mode: ModeType = ModeType.GENERATE
    images: List[ImageData] = field(default_factory=list)
    pending_prompt: Optional[str] = None
    aspect_ratio: str = "auto"
    output_format: str = "png"
    last_result_urls: List[str] = field(default_factory=list)  # Store last generation results for full quality download
    last_prompt: Optional[str] = None  # Store last used prompt for regeneration
    last_mode: Optional[ModeType] = None  # Store last mode used for generation
    last_images: List[ImageData] = field(default_factory=list)  # Store last images used for regeneration
    awaiting_broadcast_text: bool = False
    awaiting_broadcast_photo: bool = False
    pending_broadcast_text: Optional[str] = None
    pending_broadcast_photo_file_id: Optional[str] = None
    pending_broadcast_caption: Optional[str] = None
    broadcast_mode: Optional[str] = None
    broadcast_audience: Optional[str] = None
    broadcast_parse_mode: str = "HTML"
    broadcast_buttons: list = field(default_factory=list)
    admin_awaiting_user_id_input: bool = False
    admin_awaiting_add_days_input: bool = False
    admin_add_days_target_user_id: Optional[int] = None
    # Note: authentication, premium, and photo counts are now stored in database


class SessionManager:
    """Manager for user sessions"""

    def __init__(self):
        self._sessions: Dict[int, UserSession] = {}

    def get_session(self, user_id: int) -> UserSession:
        """Get or create user session"""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id=user_id)
        return self._sessions[user_id]

    def set_mode(self, user_id: int, mode: ModeType):
        """Set current mode for user"""
        session = self.get_session(user_id)
        session.current_mode = mode

    def get_mode(self, user_id: int) -> ModeType:
        """Get current mode for user"""
        session = self.get_session(user_id)
        return session.current_mode

    def add_image(
        self,
        user_id: int,
        file_id: str,
        file_url: str,
        role: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Add image to user session"""
        session = self.get_session(user_id)
        image_data = ImageData(
            file_id=file_id,
            file_url=file_url,
            role=role,
            description=description,
        )
        session.images.append(image_data)

    def get_images(self, user_id: int) -> List[ImageData]:
        """Get all images for user"""
        session = self.get_session(user_id)
        return session.images

    def clear_images(self, user_id: int):
        """Clear all images for user"""
        session = self.get_session(user_id)
        session.images = []

    def set_image_role(self, user_id: int, image_index: int, role: str):
        """Set role for specific image (source/reference)"""
        session = self.get_session(user_id)
        if 0 <= image_index < len(session.images):
            session.images[image_index].role = role

    def get_images_by_role(self, user_id: int, role: str) -> List[ImageData]:
        """Get images filtered by role"""
        session = self.get_session(user_id)
        return [img for img in session.images if img.role == role]

    def set_pending_prompt(self, user_id: int, prompt: Optional[str]):
        """Set pending prompt for user"""
        session = self.get_session(user_id)
        session.pending_prompt = prompt

    def get_pending_prompt(self, user_id: int) -> Optional[str]:
        """Get pending prompt for user"""
        session = self.get_session(user_id)
        return session.pending_prompt

    def set_aspect_ratio(self, user_id: int, aspect_ratio: str):
        """Set aspect ratio preference"""
        session = self.get_session(user_id)
        session.aspect_ratio = aspect_ratio

    def get_aspect_ratio(self, user_id: int) -> str:
        """Get aspect ratio preference"""
        session = self.get_session(user_id)
        return session.aspect_ratio

    def set_output_format(self, user_id: int, output_format: str):
        """Set output format preference (png/jpeg)"""
        session = self.get_session(user_id)
        session.output_format = output_format

    def get_output_format(self, user_id: int) -> str:
        """Get output format preference"""
        session = self.get_session(user_id)
        return session.output_format

    def reset_session(self, user_id: int):
        """Reset user session to default state (preserves auth and limits)"""
        session = self.get_session(user_id)
        session.images = []
        session.pending_prompt = None
        session.aspect_ratio = "auto"
        session.output_format = "png"
        # Note: authentication, premium status, and photo counts are preserved

    def set_broadcast_awaiting(self, user_id: int, awaiting: bool):
        session = self.get_session(user_id)
        session.awaiting_broadcast_text = awaiting

    def is_broadcast_awaiting(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        return session.awaiting_broadcast_text

    def set_broadcast_photo_awaiting(self, user_id: int, awaiting: bool):
        session = self.get_session(user_id)
        session.awaiting_broadcast_photo = awaiting

    def is_broadcast_photo_awaiting(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        return session.awaiting_broadcast_photo

    def set_pending_broadcast_text(self, user_id: int, text: Optional[str]):
        session = self.get_session(user_id)
        session.pending_broadcast_text = text

    def get_pending_broadcast_text(self, user_id: int) -> Optional[str]:
        session = self.get_session(user_id)
        return session.pending_broadcast_text

    def set_pending_broadcast_photo(self, user_id: int, file_id: Optional[str], caption: Optional[str]):
        session = self.get_session(user_id)
        session.pending_broadcast_photo_file_id = file_id
        session.pending_broadcast_caption = caption

    def get_pending_broadcast_photo(self, user_id: int):
        session = self.get_session(user_id)
        return session.pending_broadcast_photo_file_id, session.pending_broadcast_caption

    def set_broadcast_mode(self, user_id: int, mode: Optional[str]):
        session = self.get_session(user_id)
        session.broadcast_mode = mode

    def get_broadcast_mode(self, user_id: int) -> Optional[str]:
        session = self.get_session(user_id)
        return session.broadcast_mode

    def set_broadcast_audience(self, user_id: int, audience: Optional[str]):
        session = self.get_session(user_id)
        session.broadcast_audience = audience

    def get_broadcast_audience(self, user_id: int) -> Optional[str]:
        session = self.get_session(user_id)
        return session.broadcast_audience

    def set_broadcast_parse_mode(self, user_id: int, mode: str):
        session = self.get_session(user_id)
        session.broadcast_parse_mode = mode

    def get_broadcast_parse_mode(self, user_id: int) -> str:
        session = self.get_session(user_id)
        return session.broadcast_parse_mode

    def toggle_broadcast_button(self, user_id: int, code: str):
        session = self.get_session(user_id)
        if code in session.broadcast_buttons:
            session.broadcast_buttons.remove(code)
        else:
            session.broadcast_buttons.append(code)

    def clear_broadcast_buttons(self, user_id: int):
        session = self.get_session(user_id)
        session.broadcast_buttons = []

    def get_broadcast_buttons(self, user_id: int):
        session = self.get_session(user_id)
        return list(session.broadcast_buttons)

    def get_image_count(self, user_id: int) -> int:
        """Get number of uploaded images"""
        session = self.get_session(user_id)
        return len(session.images)

    def set_admin_awaiting_user_id_input(self, user_id: int, awaiting: bool):
        session = self.get_session(user_id)
        session.admin_awaiting_user_id_input = awaiting

    def is_admin_awaiting_user_id_input(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        return session.admin_awaiting_user_id_input

    def set_admin_awaiting_add_days_input(self, user_id: int, awaiting: bool):
        session = self.get_session(user_id)
        session.admin_awaiting_add_days_input = awaiting

    def is_admin_awaiting_add_days_input(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        return session.admin_awaiting_add_days_input

    def set_admin_add_days_target_user_id(self, user_id: int, target_user_id: Optional[int]):
        session = self.get_session(user_id)
        session.admin_add_days_target_user_id = target_user_id

    def get_admin_add_days_target_user_id(self, user_id: int) -> Optional[int]:
        session = self.get_session(user_id)
        return session.admin_add_days_target_user_id

    def set_last_result_urls(self, user_id: int, urls: List[str]):
        """Store last generation result URLs"""
        session = self.get_session(user_id)
        session.last_result_urls = urls

    def get_last_result_urls(self, user_id: int) -> List[str]:
        """Get last generation result URLs"""
        session = self.get_session(user_id)
        return session.last_result_urls

    def set_last_prompt(self, user_id: int, prompt: str):
        """Store last used prompt for regeneration"""
        session = self.get_session(user_id)
        session.last_prompt = prompt

    def get_last_prompt(self, user_id: int) -> Optional[str]:
        """Get last used prompt"""
        session = self.get_session(user_id)
        return session.last_prompt

    def save_generation_state(self, user_id: int, prompt: str, mode: ModeType, images: List[ImageData]):
        """Save complete generation state for regeneration"""
        session = self.get_session(user_id)
        session.last_prompt = prompt
        session.last_mode = mode
        # Deep copy images to preserve them
        import copy
        session.last_images = copy.deepcopy(images)

    def restore_generation_state(self, user_id: int):
        """Restore images and mode from last generation"""
        session = self.get_session(user_id)
        if session.last_mode and session.last_images:
            # Restore images
            import copy
            session.images = copy.deepcopy(session.last_images)

    def get_last_mode(self, user_id: int) -> Optional[ModeType]:
        """Get last mode used for generation"""
        session = self.get_session(user_id)
        return session.last_mode

    # Authentication methods (delegated to database)
    def set_authenticated(self, user_id: int, authenticated: bool):
        """Set authentication status"""
        db.set_authenticated(user_id, authenticated)

    def is_authenticated(self, user_id: int) -> bool:
        """Check if user is authenticated"""
        return db.is_authenticated(user_id)

    def set_premium(self, user_id: int, premium: bool):
        """Set premium status"""
        db.set_premium(user_id, premium)

    def is_premium(self, user_id: int) -> bool:
        """Check if user has premium access"""
        return db.is_premium(user_id)

    # Photo limits methods (delegated to database)
    def increment_photos_count(self, user_id: int):
        """Increment photos generated today counter"""
        db.increment_photos_count(user_id)

    def get_photos_count(self, user_id: int) -> int:
        """Get number of photos generated today"""
        return db.get_photos_count(user_id)

    def get_daily_limit(self, user_id: int) -> int:
        """Get daily photo limit for user"""
        return db.get_daily_limit(user_id)

    def can_generate(self, user_id: int) -> bool:
        """Check if user can generate more photos today"""
        return db.can_generate(user_id)


# Global session manager instance
session_manager = SessionManager()
