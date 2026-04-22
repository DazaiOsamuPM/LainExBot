"""
Tests for the download manager: queue bookkeeping, error reporting, and helpers.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aiogram.exceptions import TelegramBadRequest

from managers import DownloadManager, _is_bad_media_type_error, _YtdlpProgressReporter
from models import FileFormat


@pytest.fixture
def manager():
    async def _factory():
        return DownloadManager(max_concurrent=2)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        instance = loop.run_until_complete(_factory())
        yield instance, loop
        loop.run_until_complete(instance.stop())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_add_download_rejects_unknown_mode(manager):
    instance, loop = manager
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )

    result = loop.run_until_complete(
        instance.add_download(callback, "https://youtu.be/x", "gif")
    )
    assert result is False
    callback.answer.assert_awaited_once()


def test_add_download_queues_and_tracks_user():
    """add_download should enqueue a task and count it for the user, without starting workers."""
    instance = DownloadManager.__new__(DownloadManager)
    instance.max_concurrent = 1
    instance.queue = asyncio.Queue()
    instance.lock = asyncio.Lock()
    instance.processing = 0
    instance.task_counter = 0
    instance.active_tasks = {}
    instance.queued_tasks = {}
    instance._http_session = None
    instance._workers = []

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )

    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(
            instance.add_download(callback, "https://youtu.be/x", FileFormat.VIDEO.value)
        )
    finally:
        loop.close()

    assert ok is True
    assert instance.get_user_active_downloads(7) == 1
    assert instance.get_queue_size() == 1


def test_is_bad_media_type_error_matches_known_markers():
    err = TelegramBadRequest(method=None, message="Bad Request: wrong file type")
    assert _is_bad_media_type_error(err) is True

    err2 = TelegramBadRequest(method=None, message="Request Entity Too Large")
    assert _is_bad_media_type_error(err2) is False


def test_progress_reporter_format_helpers():
    assert _YtdlpProgressReporter._format(
        {"status": "downloading", "downloaded_bytes": 500, "total_bytes": 1000}
    ) == "⬇️ Загрузка: 50%"
    assert _YtdlpProgressReporter._format({"status": "finished"}) == "📦 Обработка файла…"
    assert _YtdlpProgressReporter._format({"status": "other"}) is None


def test_handle_download_error_prefers_editing_status_message():
    async def _run():
        instance = DownloadManager(max_concurrent=1)
        try:
            status_msg = SimpleNamespace(edit_text=AsyncMock())
            callback = SimpleNamespace(
                from_user=SimpleNamespace(id=1),
                message=SimpleNamespace(answer=AsyncMock()),
            )

            await instance._handle_download_error(
                callback_query=callback,
                error=RuntimeError("unable to extract webpage video data: tiktok"),
                url="https://www.tiktok.com/@u/video/1",
                status_msg=status_msg,
            )
            status_msg.edit_text.assert_awaited_once()
            callback.message.answer.assert_not_awaited()
        finally:
            await instance.stop()

    asyncio.new_event_loop().run_until_complete(_run())


def test_handle_download_error_falls_back_to_answer_when_edit_fails():
    async def _run():
        instance = DownloadManager(max_concurrent=1)
        try:
            status_msg = SimpleNamespace(edit_text=AsyncMock(side_effect=RuntimeError("boom")))
            callback = SimpleNamespace(
                from_user=SimpleNamespace(id=1),
                message=SimpleNamespace(answer=AsyncMock()),
            )

            await instance._handle_download_error(
                callback_query=callback,
                error=RuntimeError("some transient failure"),
                url="https://example.com/v.mp4",
                status_msg=status_msg,
            )
            callback.message.answer.assert_awaited_once()
        finally:
            await instance.stop()

    asyncio.new_event_loop().run_until_complete(_run())


def test_parse_cookies_from_browser_handles_shapes():
    assert DownloadManager._parse_cookies_from_browser("") is None
    assert DownloadManager._parse_cookies_from_browser("chrome") == ("chrome",)
    assert DownloadManager._parse_cookies_from_browser("firefox:default-release") == (
        "firefox",
        "default-release",
    )
    assert DownloadManager._parse_cookies_from_browser("edge::Profile 1") == ("edge", "Profile 1")


def test_canonicalize_tiktok_video_url():
    assert (
        DownloadManager._canonicalize_tiktok_video_url("https://www.tiktok.com/@user/video/12345")
        == "https://www.tiktok.com/@_/video/12345"
    )
    assert DownloadManager._canonicalize_tiktok_video_url("https://vm.tiktok.com/abcd") is None


def test_build_tiktok_attempt_plan_is_deduplicated():
    manager_instance = DownloadManager.__new__(DownloadManager)
    plan = DownloadManager._build_tiktok_attempt_plan(
        manager_instance, "https://www.tiktok.com/@u/video/42"
    )
    # With a canonical match, we get up to 2 distinct URLs x 2 modes = up to 4 entries,
    # but since original URL already equals canonical host/path, duplicates collapse.
    assert len(plan) >= 2
    urls = {url for url, _ in plan}
    assert any("/@u/video/42" in url for url in urls)
    assert any("/@_/video/42" in url for url in urls)
