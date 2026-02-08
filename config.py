"""
Minimal configuration for a download-only Telegram bot.
"""

import os
import re
from typing import Any, Dict, List


def require_bot_token() -> str:
    """Return bot token or raise if it is not configured."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Установите переменную окружения BOT_TOKEN")
    return token


LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "2048"))  # Telegram hard limit
DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "600"))

TEMP_DIR_PREFIX: str = "tgdl_"
YTDLP_COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "").strip()
YTDLP_COOKIES_FROM_BROWSER: str = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()

YTDL_BASE_OPTS: Dict[str, Any] = {
    "nocheckcertificate": True,
    "quiet": True,
    "no_warnings": True,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    },
}

URL_RE: re.Pattern[str] = re.compile(r"https?://[^\s<>'\"()\[\]{}]+", re.IGNORECASE)

DIRECT_FILE_RE: re.Pattern[str] = re.compile(
    r"(?:https?://)?[^\s]+\.(?:mp4|mkv|webm|avi|mov|wmv|flv|mp3|m4a|wav|aac|ogg)"
    r"(?:\?[^#\s]*)?(?:#[^\s]*)?$",
    re.IGNORECASE,
)

VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv")
AUDIO_EXTENSIONS: tuple[str, ...] = (".mp3", ".m4a", ".wav", ".aac", ".ogg")

SHORTENER_DOMAINS: tuple[str, ...] = (
    "vm.tiktok.com",
    "vt.tiktok.com",
    "m.tiktok.com",
    "www.tiktok.com",
    "tiktok.com",
)

SUPPORTED_DOMAINS: List[str] = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "m.tiktok.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "vk.com",
    "m.vkvideo.ru",
    "reddit.com",
    "pinterest.com",
    "pin.it",
    "dailymotion.com",
    "vimeo.com",
    "soundcloud.com",
]
