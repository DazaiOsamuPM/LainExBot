"""
Utilities for URL parsing, validation and file operations.
"""

import os
import re
import shutil
import tempfile
import html
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from typing import Optional, Tuple

import aiofiles
import aiohttp

from config import (
    URL_RE,
    DIRECT_FILE_RE,
    SUPPORTED_DOMAINS,
    SHORTENER_DOMAINS,
    TEMP_DIR_PREFIX,
)
from models import Platform


def find_first_url(text: str) -> Optional[str]:
    """Return first URL in text."""
    if not text:
        return None
    match = URL_RE.search(text)
    return match.group(0) if match else None


def strip_tracking_params(url: str) -> str:
    """Remove common tracking query params from URL."""
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        clean_params = {
            key: value
            for key, value in query_params.items()
            if key.lower()
            not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
        }
        clean_query = urlencode(clean_params, doseq=True)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment)
        )
    except Exception:
        return url


def _url_hostname(url: str) -> Optional[str]:
    """Safely extract lowercase hostname from URL."""
    try:
        host = urlparse(url).hostname
    except Exception:
        return None
    return host.lower() if host else None


def _host_matches(host: Optional[str], domain: str) -> bool:
    """True if `host` equals `domain` or is a subdomain of it."""
    if not host:
        return False
    domain = domain.lower()
    return host == domain or host.endswith("." + domain)


def host_matches_any(url: str, domains) -> bool:
    """True if URL host equals or is a subdomain of any entry in `domains`."""
    host = _url_hostname(url)
    if not host:
        return False
    return any(_host_matches(host, d) for d in domains)


def is_supported_url(url: str) -> bool:
    """Check whether URL belongs to a supported platform or is a direct media file."""
    if not url:
        return False
    if host_matches_any(url, SUPPORTED_DOMAINS):
        return True
    return bool(DIRECT_FILE_RE.search(url))


_PLATFORM_BY_DOMAIN = (
    (("youtube.com", "youtu.be"), Platform.YOUTUBE),
    (("tiktok.com",), Platform.TIKTOK),
    (("instagram.com",), Platform.INSTAGRAM),
    (("facebook.com", "fb.watch"), Platform.FACEBOOK),
    (("twitter.com", "x.com"), Platform.TWITTER),
    (("vk.com", "vkvideo.ru"), Platform.VK),
    (("reddit.com", "redd.it"), Platform.REDDIT),
    (("pinterest.com", "pin.it"), Platform.PINTEREST),
    (("dailymotion.com", "dai.ly"), Platform.DAILYMOTION),
    (("vimeo.com",), Platform.VIMEO),
    (("soundcloud.com",), Platform.SOUNDCLOUD),
)


def detect_platform(url: str) -> Platform:
    """Detect source platform by URL hostname."""
    if not url:
        return Platform.UNKNOWN

    host = _url_hostname(url)
    if host:
        for domains, platform in _PLATFORM_BY_DOMAIN:
            if any(_host_matches(host, d) for d in domains):
                return platform

    if DIRECT_FILE_RE.search(url):
        return Platform.DIRECT
    return Platform.UNKNOWN


def sanitize_filename(filename: str) -> str:
    """Return filesystem-safe filename."""
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", filename)
    safe_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", safe_name)
    safe_name = safe_name.strip().strip(".")
    return (safe_name or "media")[:255]


def get_file_size_mb(filepath: str) -> float:
    """File size in MB."""
    try:
        return os.path.getsize(filepath) / (1024 * 1024)
    except (FileNotFoundError, OSError):
        return 0.0


def has_enough_disk_space(path: str, required_mb: int = 500) -> bool:
    """Check available disk space."""
    try:
        _, _, free = shutil.disk_usage(path)
        return (free // (1024 * 1024)) >= required_mb
    except Exception:
        return True


def create_temp_dir(prefix: str = TEMP_DIR_PREFIX) -> str:
    """Create temp dir for one download job."""
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_temp_dir(temp_dir: str) -> None:
    """Remove temporary directory."""
    try:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
    except Exception:
        pass


def format_file_size(bytes_size: int) -> str:
    """Human readable file size."""
    if bytes_size is None:
        return "0.0 B"

    size = float(max(bytes_size, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return "0.0 B"


def format_duration(seconds: float) -> str:
    """Human readable duration."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def extract_tiktok_video_from_html(html: str) -> Optional[str]:
    """Try to extract canonical TikTok video URL from page HTML."""
    match = re.search(r"/@(?P<user>[^/]+)/video/(?P<id>\d+)", html)
    if match:
        return f"https://www.tiktok.com/@{match.group('user')}/video/{match.group('id')}"

    match = re.search(r'"itemId"\s*:\s*"(?P<id>\d+)"', html)
    if match:
        return f"https://www.tiktok.com/@_/video/{match.group('id')}"
    return None


def extract_tiktok_media_url_from_html(html_content: str) -> Optional[str]:
    """
    Extract direct TikTok media URL from HTML.

    Prefers watermark-free download URL when present.
    """
    if not html_content:
        return None

    patterns = [
        r'"downloadAddr"\s*:\s*"(?P<url>https?:\\/\\/[^"]+)"',
        r'"playAddr"\s*:\s*"(?P<url>https?:\\/\\/[^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_content)
        if not match:
            continue

        url = match.group("url")
        try:
            url = url.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        url = html.unescape(url).replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&")
        if url.startswith("http://") or url.startswith("https://"):
            return url

    return None


async def normalize_tiktok_url_async(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Normalize TikTok URL:
    - resolve short links
    - extract direct /video/ URL from destination page when needed
    """
    host = (_url_hostname(url) or "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15"
        )
    }

    try:
        final_url = url
        if any(_host_matches(host, domain) for domain in SHORTENER_DOMAINS):
            try:
                async with session.head(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers=headers,
                ) as resp:
                    final_url = str(resp.url)
            except Exception:
                async with session.get(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=12),
                    headers=headers,
                ) as resp:
                    final_url = str(resp.url)

        final_clean = strip_tracking_params(final_url)
        if "/video/" in final_clean:
            return final_clean

        async with session.get(
            final_url,
            timeout=aiohttp.ClientTimeout(total=12),
            headers=headers,
        ) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            return extract_tiktok_video_from_html(html)
    except Exception:
        return None


async def download_file_async(
    url: str,
    filepath: str,
    session: aiohttp.ClientSession,
    timeout: int = 300,
) -> None:
    """Download direct file URL to local path."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
        response.raise_for_status()
        async with aiofiles.open(filepath, "wb") as file:
            async for chunk in response.content.iter_chunked(8192):
                await file.write(chunk)


def validate_url_input(url: str) -> Tuple[bool, str]:
    """Validate URL format and safety."""
    if not url:
        return False, "URL не может быть пустым"
    if len(url) > 2000:
        return False, "URL слишком длинный"

    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False, "Поддерживаются только HTTP/HTTPS URL"
        if not parsed.netloc:
            return False, "Некорректный URL"
    except Exception:
        return False, "Некорректный URL"

    return True, ""


def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Remove control chars and trim length."""
    if not text:
        return ""
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
    return sanitized.strip()[:max_length]
