"""
Mode definitions for banana-studio bot
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ModeType(Enum):
    """Available generation modes"""
    GENERATE = "generate"
    EDIT = "edit"
    REFERENCE = "reference"


@dataclass
class ModeConfig:
    """Configuration for a generation mode"""
    code: ModeType
    title: str
    button_label: str
    description: str
    emoji: str
    requires_images: bool  # True if mode needs image input
    max_images: int  # Maximum images for this mode


# Mode catalog
MODE_CATALOG = {
    ModeType.GENERATE: ModeConfig(
        code=ModeType.GENERATE,
        title="Генерация",
        button_label="🎨 Генерация",
        description="Создание изображения из текстового описания (text-to-image)",
        emoji="🎨",
        requires_images=False,
        max_images=0,
    ),
    ModeType.EDIT: ModeConfig(
        code=ModeType.EDIT,
        title="Редактирование",
        button_label="✏️ Редактирование",
        description="Изменение существующего изображения по инструкциям",
        emoji="✏️",
        requires_images=True,
        max_images=1,
    ),
    ModeType.REFERENCE: ModeConfig(
        code=ModeType.REFERENCE,
        title="Референс",
        button_label="📸 Референс",
        description="Применение стиля из референсного изображения к основному",
        emoji="📸",
        requires_images=True,
        max_images=10,  # API supports up to 10 images
    ),
}


def get_mode_by_code(code: str) -> Optional[ModeConfig]:
    """Get mode config by code string"""
    try:
        mode_type = ModeType(code)
        return MODE_CATALOG.get(mode_type)
    except ValueError:
        return None
