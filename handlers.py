"""
Minimal Telegram handlers for a download-only bot.
"""

import html
import logging
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, Optional

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    MAX_PENDING_LINKS_PER_USER,
    MAX_USER_TASKS,
    USER_RATE_LIMIT_MESSAGES,
    USER_RATE_LIMIT_WINDOW_SECONDS,
)
from managers import DownloadManager
from models import Platform
from utils import (
    detect_platform,
    find_first_url,
    is_supported_url,
    sanitize_user_input,
    strip_tracking_params,
    validate_url_input,
)

logger = logging.getLogger(__name__)


class BotHandlers:
    """Registers bot commands and URL-driven download flow."""

    def __init__(self, dp: Dispatcher, download_manager: DownloadManager):
        self.dp = dp
        self.download_manager = download_manager

        # token -> {user_id, url, created_at}
        self.pending_links: Dict[str, Dict[str, Any]] = {}
        # user_id -> deque[token] (oldest first) for per-user LRU cap
        self._user_tokens: Dict[int, Deque[str]] = {}
        self.pending_link_ttl_seconds = 3600
        self._last_pending_cleanup = 0.0
        self._pending_cleanup_interval_seconds = 60

        # user_id -> deque[timestamp] of recent user interactions for rate limiting
        self._user_events: Dict[int, Deque[float]] = {}

        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.handle_start, Command(commands=["start"]))
        self.dp.message.register(self.handle_help, Command(commands=["help"]))
        self.dp.message.register(self.handle_url_message, F.text)
        self.dp.callback_query.register(
            self.handle_download_callback,
            lambda callback: (callback.data or "").startswith("download:"),
        )

    async def handle_start(self, message: Message) -> None:
        raw_username = message.from_user.username if message.from_user else None
        username = html.escape(raw_username) if raw_username else "друг"
        text = (
            f"👋 Привет, {username}!\n\n"
            "Я скачиваю видео и аудио по ссылке.\n\n"
            "Поддерживаются:\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Instagram\n"
            "• Facebook\n"
            "• X (Twitter)\n"
            "• VK\n"
            "• Reddit\n"
            "• Pinterest\n"
            "• Dailymotion\n"
            "• Vimeo\n"
            "• SoundCloud\n\n"
            "Просто отправь ссылку, затем выбери формат."
        )
        await message.answer(text, parse_mode="HTML")

    async def handle_help(self, message: Message) -> None:
        text = (
            "📖 <b>Как пользоваться</b>\n\n"
            "1. Отправьте ссылку на пост или видео.\n"
            "2. Нажмите кнопку <b>Скачать видео</b> или <b>Скачать аудио</b>.\n"
            "3. Дождитесь загрузки файла.\n\n"
            "Публичный Telegram Bot API позволяет отправлять файлы до 50 МБ. "
            "Больший размер — только с self-hosted Bot API Server."
        )
        await message.answer(text, parse_mode="HTML")

    async def handle_url_message(self, message: Message) -> None:
        if not message.from_user:
            return

        text = sanitize_user_input(message.text or "")
        if not text or text.startswith("/"):
            return

        if self._is_rate_limited(message.from_user.id):
            await message.answer(
                "⏳ Слишком часто. Подождите немного и попробуйте снова."
            )
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

        url = strip_tracking_params(url)

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
            f"{self._get_platform_emoji(platform)} <b>{html.escape(platform.value)}</b>\n\n"
            "Выберите формат загрузки:",
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

        if self._is_rate_limited(user_id):
            await callback.answer("Слишком часто. Подождите немного.", show_alert=True)
            return

        url = self._resolve_pending_link(token, user_id)
        if not url:
            await callback.answer("Ссылка устарела. Отправьте её заново.", show_alert=True)
            return

        active_for_user = self.download_manager.get_user_active_downloads(user_id)
        if active_for_user >= MAX_USER_TASKS:
            await callback.answer(
                f"У вас уже {active_for_user} активных задач (лимит {MAX_USER_TASKS}). "
                "Подождите завершения.",
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

    # ---------- pending-link bookkeeping ----------

    def _create_pending_link(self, user_id: int, url: str) -> str:
        self._cleanup_pending_links()
        token = uuid.uuid4().hex[:12]
        self.pending_links[token] = {
            "user_id": user_id,
            "url": url,
            "created_at": time.time(),
        }

        user_tokens = self._user_tokens.setdefault(user_id, deque())
        user_tokens.append(token)
        while len(user_tokens) > MAX_PENDING_LINKS_PER_USER:
            old_token = user_tokens.popleft()
            self.pending_links.pop(old_token, None)
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
        now = time.time()
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

        # Also compact per-user token queues.
        for user_id, tokens in list(self._user_tokens.items()):
            live = deque(t for t in tokens if t in self.pending_links)
            if live:
                self._user_tokens[user_id] = live
            else:
                self._user_tokens.pop(user_id, None)

    # ---------- rate limiting ----------

    def _is_rate_limited(self, user_id: int) -> bool:
        now = time.time()
        window_start = now - USER_RATE_LIMIT_WINDOW_SECONDS
        events = self._user_events.setdefault(user_id, deque())
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= USER_RATE_LIMIT_MESSAGES:
            return True
        events.append(now)
        return False

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
