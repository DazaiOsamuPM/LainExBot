"""
Minimal data models for the downloader bot.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DownloadStatus(Enum):
    """Lifecycle states for a single download task."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"


class FileFormat(Enum):
    """Supported output modes."""

    VIDEO = "video"
    AUDIO = "audio"


class Platform(Enum):
    """Supported media source platforms."""

    YOUTUBE = "YouTube"
    TIKTOK = "TikTok"
    INSTAGRAM = "Instagram"
    FACEBOOK = "Facebook"
    TWITTER = "Twitter/X"
    VK = "VK"
    REDDIT = "Reddit"
    PINTEREST = "Pinterest"
    DAILYMOTION = "Dailymotion"
    VIMEO = "Vimeo"
    SOUNDCLOUD = "SoundCloud"
    DIRECT = "Direct Link"
    UNKNOWN = "Unknown"


@dataclass
class DownloadTask:
    """Runtime info for one queued or active download."""

    task_id: int
    user_id: int
    url: str
    mode: str
    status: DownloadStatus = DownloadStatus.QUEUED
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    error_message: Optional[str] = None
