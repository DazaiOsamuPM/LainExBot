"""
Unit tests for minimal data models.
"""

from models import DownloadStatus, DownloadTask, FileFormat, Platform


def test_download_task_defaults():
    task = DownloadTask(task_id=1, user_id=42, url="https://example.com/v", mode="video")
    assert task.status == DownloadStatus.QUEUED
    assert task.start_ts is None
    assert task.end_ts is None
    assert task.error_message is None


def test_download_status_enum_values():
    assert DownloadStatus.QUEUED.value == "queued"
    assert DownloadStatus.DOWNLOADING.value == "downloading"
    assert DownloadStatus.SENDING.value == "sending"
    assert DownloadStatus.COMPLETED.value == "completed"
    assert DownloadStatus.FAILED.value == "failed"


def test_file_format_enum_values():
    assert FileFormat.VIDEO.value == "video"
    assert FileFormat.AUDIO.value == "audio"


def test_platform_enum_values():
    assert Platform.YOUTUBE.value == "YouTube"
    assert Platform.TIKTOK.value == "TikTok"
    assert Platform.UNKNOWN.value == "Unknown"
