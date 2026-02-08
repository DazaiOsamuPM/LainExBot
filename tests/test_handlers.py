"""
Unit tests for minimal handler flow.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Dispatcher

from handlers import BotHandlers


class _StubDownloadManager:
    max_concurrent = 3

    def __init__(self):
        self.add_download = AsyncMock(return_value=True)

    def get_user_active_downloads(self, user_id):
        return 0

    def get_queue_size(self):
        return 1


def _make_handlers():
    manager = _StubDownloadManager()
    handlers = BotHandlers(dp=Dispatcher(), download_manager=manager)
    return handlers, manager


def test_resolve_pending_link_allows_owner_only():
    handlers, _ = _make_handlers()
    token = handlers._create_pending_link(1001, "https://youtube.com/watch?v=test")

    assert handlers._resolve_pending_link(token, 1001) is not None
    assert handlers._resolve_pending_link(token, 2002) is None


def test_download_callback_queues_task():
    handlers, manager = _make_handlers()
    token = handlers._create_pending_link(1001, "https://youtube.com/watch?v=test")

    callback = SimpleNamespace(
        data=f"download:video:{token}",
        from_user=SimpleNamespace(id=1001),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )

    asyncio.run(handlers.handle_download_callback(callback))

    manager.add_download.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()


def test_download_callback_rejects_expired_token():
    handlers, manager = _make_handlers()
    callback = SimpleNamespace(
        data="download:video:missingtoken",
        from_user=SimpleNamespace(id=1001),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )

    asyncio.run(handlers.handle_download_callback(callback))

    manager.add_download.assert_not_awaited()
    assert callback.answer.await_count == 1
