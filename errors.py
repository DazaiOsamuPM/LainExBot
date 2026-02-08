"""
Error formatting and logging utilities.
"""

import html
import logging
from typing import Optional


def setup_logging(
    level: str = "INFO",
    format_string: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> logging.Logger:
    """Configure root logging once and return module logger."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(format_string))
    root_logger.addHandler(console_handler)
    return logging.getLogger(__name__)


class ErrorManager:
    """Convert internal exceptions to compact user-facing messages."""

    def to_user_message(self, error: Exception, url: Optional[str] = None) -> str:
        msg = str(error).lower()

        if "drm protected" in msg:
            return (
                "🔒 <b>Видео защищено DRM.</b>\n"
                "Такой контент нельзя скачать через обычные инструменты (включая yt-dlp)."
            )

        if "unsupported" in msg:
            return (
                "❌ <b>Ссылка не поддерживается.</b>\n"
                "Отправьте прямую ссылку на пост или видео."
            )

        if "too large" in msg or "размер" in msg or "max_filesize" in msg:
            return (
                "❌ <b>Файл слишком большой для Telegram.</b>\n"
                "Выберите аудио или другой ролик."
            )

        if "timeout" in msg or "timed out" in msg:
            return (
                "⏱️ <b>Превышено время ожидания.</b>\n"
                "Попробуйте снова чуть позже."
            )

        if "disk" in msg or "space" in msg:
            return (
                "💾 <b>Недостаточно места на диске.</b>\n"
                "Повторите попытку позже."
            )

        if "unable to extract webpage video data" in msg:
            return (
                "❌ <b>TikTok сейчас не отдаёт данные видео.</b>\n"
                "Попробуйте позже, другую ссылку или обновите yt-dlp до последней версии."
            )

        if "video not available" in msg or "private" in msg:
            return (
                "❌ <b>Видео недоступно.</b>\n"
                "Возможно ролик удалён, приватный или ограничен по региону/возрасту."
            )

        safe_details = html.escape(str(error))[:350]
        return (
            "⚠️ <b>Не удалось скачать медиа.</b>\n"
            f"<code>{safe_details}</code>"
        )


error_manager = ErrorManager()
