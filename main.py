"""
Entry point for the minimal download-only Telegram bot.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from dotenv import load_dotenv

from config import LOG_LEVEL, require_bot_token
from errors import setup_logging
from handlers import BotHandlers
from managers import DownloadManager

load_dotenv()
shutdown_event = asyncio.Event()


async def start_health_server() -> None:
    """Run a tiny HTTP server so Render Web Service can keep this app healthy."""
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    host = "0.0.0.0"
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.getLogger(__name__).info("Health server started on %s:%s", host, port)

    try:
        await shutdown_event.wait()
    finally:
        await runner.cleanup()


async def main() -> None:
    logger = setup_logging(level=LOG_LEVEL)
    logger.info("Starting downloader bot")

    bot = None
    download_manager = None
    health_server_task = None
    try:
        bot = Bot(token=require_bot_token(), default=DefaultBotProperties(parse_mode="HTML"))
        dispatcher = Dispatcher(storage=MemoryStorage())

        download_manager = DownloadManager()
        BotHandlers(dp=dispatcher, download_manager=download_manager)

        health_server_task = asyncio.create_task(start_health_server())
        await dispatcher.start_polling(bot)
    except Exception:
        logging.getLogger(__name__).exception("Fatal startup/runtime error")
        sys.exit(1)
    finally:
        shutdown_event.set()
        if health_server_task is not None:
            try:
                await health_server_task
            except Exception:
                logging.getLogger(__name__).debug("Health server shutdown failed", exc_info=True)
        if download_manager is not None:
            await download_manager.stop()
        if bot is not None:
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
