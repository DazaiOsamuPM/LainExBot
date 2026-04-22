"""
Minimal configuration for a download-only Telegram bot.
"""

import os
import re
from typing import Any, Dict, List, Tuple


def require_bot_token() -> str:
    """Return bot token or raise if it is not configured."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Установите переменную окружения BOT_TOKEN")
    return token


LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Telegram public Bot API limits to 50 MB per file for bots. A self-hosted Bot API
# Server (https://core.telegram.org/bots/api#using-a-local-bot-api-server) supports
# up to 2000 MB. Bump MAX_FILE_SIZE_MB together with TELEGRAM_API_BASE for that.
MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
MAX_USER_TASKS: int = int(os.getenv("MAX_USER_TASKS", "2"))
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "600"))

# Optional custom Bot API endpoint (e.g. self-hosted server). Leave empty for the default.
TELEGRAM_API_BASE: str = os.getenv("TELEGRAM_API_BASE", "").strip()

# Per-user anti-spam limits (in-memory, best effort).
MAX_PENDING_LINKS_PER_USER: int = int(os.getenv("MAX_PENDING_LINKS_PER_USER", "20"))
USER_RATE_LIMIT_MESSAGES: int = int(os.getenv("USER_RATE_LIMIT_MESSAGES", "20"))
USER_RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("USER_RATE_LIMIT_WINDOW_SECONDS", "60"))

TEMP_DIR_PREFIX: str = "tgdl_"
YTDLP_COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "").strip()
YTDLP_COOKIES_FROM_BROWSER: str = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()

_DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

YTDL_BASE_OPTS: Dict[str, Any] = {
    "nocheckcertificate": True,
    "quiet": True,
    "no_warnings": True,
    "http_headers": {"User-Agent": _DEFAULT_USER_AGENT},
}

URL_RE: re.Pattern[str] = re.compile(r"https?://[^\s<>'\"()\[\]{}]+", re.IGNORECASE)

DIRECT_FILE_RE: re.Pattern[str] = re.compile(
    r"(?:https?://)?[^\s]+\.(?:mp4|mkv|webm|avi|mov|wmv|flv|mp3|m4a|wav|aac|ogg)"
    r"(?:\?[^#\s]*)?(?:#[^\s]*)?$",
    re.IGNORECASE,
)

VIDEO_EXTENSIONS: Tuple[str, ...] = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv")
AUDIO_EXTENSIONS: Tuple[str, ...] = (".mp3", ".m4a", ".wav", ".aac", ".ogg")

SHORTENER_DOMAINS: Tuple[str, ...] = (
    "vm.tiktok.com",
    "vt.tiktok.com",
    "m.tiktok.com",
    "www.tiktok.com",
    "tiktok.com",
)

# Base second-level domains accepted via URL host. Matching is hostname-based: a URL
# is considered supported iff its `urlparse().hostname` equals one of these values or
# ends with `.<value>`. This prevents spoofing like https://evil.com/?x=tiktok.com.
SUPPORTED_DOMAINS: List[str] = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "vk.com",
    "vkvideo.ru",
    "reddit.com",
    "redd.it",
    "pinterest.com",
    "pin.it",
    "dailymotion.com",
    "dai.ly",
    "vimeo.com",
    "soundcloud.com",
]
