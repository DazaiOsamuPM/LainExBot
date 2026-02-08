"""
Minimal Telegram handlers for a download-only bot.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from managers import DownloadManager
from models import Platform
from utils import (
    detect_platform,
    find_first_url,
    is_supported_url,
    sanitize_user_input,
    validate_url_input,
)

logger = logging.getLogger(__name__)


class BotHandlers:
    """Registers bot commands and URL-driven download flow."""

    def __init__(self, dp: Dispatcher, download_manager: DownloadManager):
        self.dp = dp
        self.download_manager = download_manager
        self.pending_links: Dict[str, Dict[str, Any]] = {}
        self.pending_link_ttl_seconds = 3600
        self._last_pending_cleanup = 0.0
        self._pending_cleanup_interval_seconds = 60
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.handle_start, Command(commands=["start"]))
        self.dp.message.register(self.handle_help, Command(commands=["help"]))
        self.dp.message.register(self.handle_url_message)
        self.dp.callback_query.register(
            self.handle_download_callback,
            lambda callback: (callback.data or "").startswith("download:"),
        )

    async def handle_start(self, message: Message) -> None:
        username = message.from_user.username or "друг"
        text = (
            f"👋 Привет, {username}!\n\n"
            "Я скачиваю видео и аудио по ссылке.\n\n"
            "Поддерживаются:\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Instagram\n"
            "• X (Twitter)\n"
            "• VK\n"
            "• Reddit\n"
            "• Pinterest\n"
            "• Dailymotion\n"
            "• Vimeo\n"
            "• SoundCloud\n\n"
            "Просто отправь ссылку, затем выбери формат."
        )
        await message.answer(text)

    async def handle_help(self, message: Message) -> None:
        text = (
            "📖 <b>Как пользоваться</b>\n\n"
            "1. Отправьте ссылку на пост или видео.\n"
            "2. Нажмите кнопку <b>Скачать видео</b> или <b>Скачать аудио</b>.\n"
            "3. Дождитесь загрузки файла.\n\n"
            "Ограничение Telegram: до 2 ГБ на файл."
        )
        await message.answer(text, parse_mode="HTML")

    async def handle_url_message(self, message: Message) -> None:
        text = sanitize_user_input(message.text or "")
        if not text or text.startswith("/"):
            return

        url = find_first_url(text)
        if not url:
            await message.answer("❌ Не нашёл ссылку в сообщении. Отправьте URL напрямую.")
            return

        valid, error = validate_url_input(url)
        if not valid:
            await message.answer(f"❌ {error}")
            return

        if not is_supported_url(url):
            await message.answer("❌ Ссылка не поддерживается. Отправьте ссылку на поддерживаемый сервис.")
            return

        platform = detect_platform(url)
        token = self._create_pending_link(message.from_user.id, url)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🎬 Скачать видео", callback_data=f"download:video:{token}"),
                    InlineKeyboardButton(text="🎵 Скачать аудио", callback_data=f"download:audio:{token}"),
                ]
            ]
        )

        await message.answer(
            f"{self._get_platform_emoji(platform)} <b>{platform.value}</b>\n\nВыберите формат загрузки:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    async def handle_download_callback(self, callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":", 2)
        if len(parts) != 3:
            await callback.answer("Некорректные данные кнопки.", show_alert=True)
            return

        _, format_type, token = parts
        user_id = callback.from_user.id
        url = self._resolve_pending_link(token, user_id)
        if not url:
            await callback.answer("Ссылка устарела. Отправьте её заново.", show_alert=True)
            return

        active_count = self.download_manager.get_user_active_downloads(user_id)
        if active_count >= self.download_manager.max_concurrent:
            await callback.answer(
                f"У вас уже {active_count} активных задач. Подождите завершения.",
                show_alert=True,
            )
            return

        queued = await self.download_manager.add_download(callback, url, format_type)
        if not queued:
            await callback.answer("Не удалось поставить задачу в очередь.", show_alert=True)
            return

        queue_position = max(1, self.download_manager.get_queue_size())
        await callback.answer("✅ Добавлено в очередь")
        if callback.message:
            try:
                await callback.message.edit_text(
                    f"⏳ Задача добавлена в очередь\nФормат: {format_type}\nПозиция: #{queue_position}"
                )
            except Exception:
                logger.debug("Callback message edit failed", exc_info=True)

    def _create_pending_link(self, user_id: int, url: str) -> str:
        self._cleanup_pending_links()
        token = uuid.uuid4().hex[:12]
        self.pending_links[token] = {
            "user_id": user_id,
            "url": url,
            "created_at": datetime.now().timestamp(),
        }
        return token

    def _resolve_pending_link(self, token: str, user_id: int) -> Optional[str]:
        self._cleanup_pending_links()
        payload = self.pending_links.get(token)
        if not payload:
            return None
        if payload["user_id"] != user_id:
            return None
        return payload["url"]

    def _cleanup_pending_links(self) -> None:
        now = datetime.now().timestamp()
        if now - self._last_pending_cleanup < self._pending_cleanup_interval_seconds:
            return
        self._last_pending_cleanup = now

        expired_tokens = [
            token
            for token, payload in self.pending_links.items()
            if now - payload["created_at"] > self.pending_link_ttl_seconds
        ]
        for token in expired_tokens:
            self.pending_links.pop(token, None)

    @staticmethod
    def _get_platform_emoji(platform: Platform) -> str:
        emoji_map = {
            Platform.YOUTUBE: "📺",
            Platform.TIKTOK: "🎵",
            Platform.INSTAGRAM: "📸",
            Platform.FACEBOOK: "📘",
            Platform.TWITTER: "🐦",
            Platform.VK: "📹",
            Platform.REDDIT: "👽",
            Platform.PINTEREST: "📌",
            Platform.DAILYMOTION: "🎬",
            Platform.VIMEO: "🎞️",
            Platform.SOUNDCLOUD: "🎧",
            Platform.DIRECT: "📁",
            Platform.UNKNOWN: "❓",
        }
        return emoji_map.get(platform, "❓")
