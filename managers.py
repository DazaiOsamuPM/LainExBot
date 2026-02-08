"""
Download manager focused only on media extraction and delivery.
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

from config import (
    AUDIO_EXTENSIONS,
    DOWNLOAD_TIMEOUT_SECONDS,
    MAX_CONCURRENT_DOWNLOADS,
    MAX_FILE_SIZE_MB,
    VIDEO_EXTENSIONS,
    YTDL_BASE_OPTS,
    YTDLP_COOKIES_FILE,
    YTDLP_COOKIES_FROM_BROWSER,
)
from errors import error_manager
from models import DownloadStatus, DownloadTask, FileFormat, Platform
from utils import (
    cleanup_temp_dir,
    create_temp_dir,
    detect_platform,
    download_file_async,
    extract_tiktok_media_url_from_html,
    get_file_size_mb,
    has_enough_disk_space,
    normalize_tiktok_url_async,
    sanitize_filename,
)

logger = logging.getLogger(__name__)


class DownloadManager:
    """Queue-based media downloader."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS):
        self.max_concurrent = max(1, max_concurrent)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.processing = 0
        self.task_counter = 0
        self.active_tasks: Dict[int, set[int]] = {}
        self.queued_tasks: Dict[int, int] = {}

        self._workers: List[asyncio.Task] = [
            asyncio.create_task(self._worker_loop(idx))
            for idx in range(self.max_concurrent)
        ]

    async def add_download(self, callback_query: Any, url: str, mode: str) -> bool:
        """Queue a new download task for user."""
        if mode not in {FileFormat.VIDEO.value, FileFormat.AUDIO.value}:
            await callback_query.answer("Неверный формат загрузки.", show_alert=True)
            return False

        user_id = callback_query.from_user.id
        async with self.lock:
            active = len(self.active_tasks.get(user_id, set()))
            queued = self.queued_tasks.get(user_id, 0)
            if active + queued >= self.max_concurrent:
                await callback_query.message.answer(
                    f"Лимит задач: {self.max_concurrent}. Дождитесь завершения текущих загрузок."
                )
                return False

            self.task_counter += 1
            task_id = self.task_counter
            self.queued_tasks[user_id] = queued + 1

        await self.queue.put((task_id, callback_query, url, mode))
        return True

    async def _worker_loop(self, worker_id: int) -> None:
        """Consume queue entries until sentinel is received."""
        while True:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break

            task_id, callback_query, url, mode = item
            user_id = callback_query.from_user.id
            await self._mark_task_started(user_id, task_id)
            try:
                await self._handle_download(
                    callback_query=callback_query,
                    task_id=task_id,
                    user_id=user_id,
                    url=url,
                    mode=mode,
                )
            except Exception:
                logger.exception("Unexpected worker error (worker=%s task=%s)", worker_id, task_id)
            finally:
                await self._mark_task_finished(user_id, task_id)
                self.queue.task_done()

    async def _mark_task_started(self, user_id: int, task_id: int) -> None:
        async with self.lock:
            queued = self.queued_tasks.get(user_id, 0) - 1
            if queued > 0:
                self.queued_tasks[user_id] = queued
            else:
                self.queued_tasks.pop(user_id, None)

            tasks = self.active_tasks.setdefault(user_id, set())
            tasks.add(task_id)
            self.processing += 1

    async def _mark_task_finished(self, user_id: int, task_id: int) -> None:
        async with self.lock:
            tasks = self.active_tasks.get(user_id)
            if tasks and task_id in tasks:
                tasks.remove(task_id)
                if not tasks:
                    self.active_tasks.pop(user_id, None)

            if self.processing > 0:
                self.processing -= 1

    async def _handle_download(
        self,
        callback_query: Any,
        task_id: int,
        user_id: int,
        url: str,
        mode: str,
    ) -> None:
        task = DownloadTask(task_id=task_id, user_id=user_id, url=url, mode=mode)
        task.start_ts = time.time()
        status_msg = None
        temp_dir = None

        try:
            temp_dir = create_temp_dir()
            if not has_enough_disk_space(temp_dir, required_mb=500):
                raise RuntimeError("Недостаточно места на диске.")

            status_msg = await callback_query.message.answer(f"Загрузка #{task_id} запущена...")
            task.status = DownloadStatus.DOWNLOADING

            filepath = await self._download_content(url, temp_dir, mode, status_msg)
            if not filepath or not os.path.exists(filepath):
                raise FileNotFoundError("Файл не найден после загрузки.")

            file_size_mb = get_file_size_mb(filepath)
            if file_size_mb > MAX_FILE_SIZE_MB:
                raise ValueError(f"Файл больше лимита Telegram ({MAX_FILE_SIZE_MB} МБ).")

            task.status = DownloadStatus.SENDING
            await self._send_file(callback_query, filepath, mode, status_msg)

            task.status = DownloadStatus.COMPLETED
            task.end_ts = time.time()
        except Exception as error:
            task.status = DownloadStatus.FAILED
            task.end_ts = time.time()
            task.error_message = str(error)
            await self._handle_download_error(callback_query, error, url, status_msg)
        finally:
            if temp_dir:
                cleanup_temp_dir(temp_dir)

    async def _download_content(
        self,
        url: str,
        temp_dir: str,
        mode: str,
        status_msg: Any,
    ) -> Optional[str]:
        if status_msg:
            try:
                await status_msg.edit_text("Скачиваю медиа...")
            except Exception:
                pass

        platform = detect_platform(url)
        is_audio = mode == FileFormat.AUDIO.value
        allowed_ext = AUDIO_EXTENSIONS if is_audio else VIDEO_EXTENSIONS

        if platform == Platform.DIRECT:
            parsed = urlparse(url)
            filename = sanitize_filename(os.path.basename(parsed.path) or f"download_{int(time.time())}")
            if "." not in filename:
                filename += ".mp3" if is_audio else ".mp4"

            filepath = os.path.join(temp_dir, filename)
            async with aiohttp.ClientSession() as session:
                await download_file_async(
                    url=url,
                    filepath=filepath,
                    session=session,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                )
            return filepath

        download_url = url
        if platform == Platform.TIKTOK:
            normalized = await self._normalize_tiktok_url(url)
            if normalized:
                download_url = normalized

        loop = asyncio.get_running_loop()
        if platform != Platform.TIKTOK:
            return await loop.run_in_executor(
                None,
                self._download_with_ytdlp,
                download_url,
                temp_dir,
                is_audio,
                allowed_ext,
                False,
            )

        attempts = self._build_tiktok_attempt_plan(download_url)
        last_error: Optional[Exception] = None
        for attempt_url, use_tiktok_app_api in attempts:
            try:
                return await loop.run_in_executor(
                    None,
                    self._download_with_ytdlp,
                    attempt_url,
                    temp_dir,
                    is_audio,
                    allowed_ext,
                    use_tiktok_app_api,
                )
            except Exception as error:
                last_error = error
                if not self._is_tiktok_extraction_error(error):
                    raise
                logger.warning(
                    "TikTok attempt failed (url=%s app_api=%s): %s",
                    attempt_url,
                    use_tiktok_app_api,
                    error,
                )

        # Last-resort TikTok fallback for video mode only:
        # parse direct media URL from HTML and download mp4.
        if not is_audio:
            direct_file = await self._download_tiktok_direct_from_html(download_url, temp_dir)
            if direct_file:
                return direct_file

        if last_error:
            raise last_error
        return None

    async def _download_tiktok_direct_from_html(self, url: str, temp_dir: str) -> Optional[str]:
        """Best-effort fallback download for TikTok when yt-dlp extractor fails."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15"
            ),
            "Referer": "https://www.tiktok.com/",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        return None
                    html_content = await response.text()

                media_url = extract_tiktok_media_url_from_html(html_content)
                if not media_url:
                    return None

                filepath = os.path.join(temp_dir, f"tiktok_{int(time.time())}.mp4")
                await download_file_async(
                    url=media_url,
                    filepath=filepath,
                    session=session,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                )
                if os.path.exists(filepath):
                    logger.info("TikTok direct HTML fallback succeeded")
                    return filepath
        except Exception as error:
            logger.warning("TikTok direct HTML fallback failed for %s: %s", url, error)

        return None

    async def _normalize_tiktok_url(self, url: str) -> Optional[str]:
        """Resolve and normalize TikTok URLs before yt-dlp extraction."""
        try:
            async with aiohttp.ClientSession() as session:
                return await normalize_tiktok_url_async(url, session)
        except Exception as error:
            logger.warning("TikTok normalization failed for %s: %s", url, error)
            return None

    @staticmethod
    def _canonicalize_tiktok_video_url(url: str) -> Optional[str]:
        """Build canonical TikTok URL by video id."""
        match = re.search(r"/video/(?P<video_id>\d+)", url)
        if not match:
            return None
        return f"https://www.tiktok.com/@_/video/{match.group('video_id')}"

    def _build_tiktok_attempt_plan(self, url: str) -> List[Tuple[str, bool]]:
        """
        Build deduplicated fallback plan:
        1) web extraction with original URL
        2) web extraction with canonical URL
        3) app-api extraction with original URL
        4) app-api extraction with canonical URL
        """
        seen = set()
        attempts: List[Tuple[str, bool]] = []
        canonical = self._canonicalize_tiktok_video_url(url)

        for attempt_url, app_api in ((url, False), (canonical, False), (url, True), (canonical, True)):
            if not attempt_url:
                continue
            key = (attempt_url, app_api)
            if key in seen:
                continue
            seen.add(key)
            attempts.append(key)

        return attempts

    @staticmethod
    def _is_tiktok_extraction_error(error: Exception) -> bool:
        """Detect recoverable TikTok extraction failures."""
        msg = str(error).lower()
        if "tiktok" not in msg:
            return False
        return any(
            token in msg
            for token in (
                "unable to extract webpage video data",
                "unable to download webpage",
                "video not available",
                "extractorerror",
            )
        )

    def _build_ytdlp_options(
        self,
        temp_dir: str,
        is_audio: bool,
        use_tiktok_app_api: bool,
    ) -> Dict[str, Any]:
        output_template = os.path.join(temp_dir, "%(title).80s_%(id)s.%(ext)s")
        ydl_opts: Dict[str, Any] = {
            **YTDL_BASE_OPTS,
            "outtmpl": output_template,
            "noplaylist": True,
            "socket_timeout": DOWNLOAD_TIMEOUT_SECONDS,
            "retries": 3,
            "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
        }

        if is_audio:
            ydl_opts.update(
                {
                    # Keep original best audio to avoid mandatory ffmpeg dependency on free hosts.
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                }
            )
        else:
            ydl_opts.update(
                {
                    "format": "bestvideo+bestaudio/best",
                    "merge_output_format": "mp4",
                }
            )

        if use_tiktok_app_api:
            mobile_ua = (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Mobile Safari/537.36"
            )
            ydl_opts.update(
                {
                    "user_agent": mobile_ua,
                    "http_headers": {
                        "User-Agent": mobile_ua,
                        "Referer": "https://www.tiktok.com/",
                    },
                    "extractor_retries": 5,
                    "extractor_args": {
                        "TikTok": {
                            "app_info": [
                                "musical_ly/35.1.3/2023501030/0",
                                "musical_ly/36.7.4/2023607040/0",
                                "musical_ly/37.1.4/2023701040/0",
                            ],
                            "api_hostname": [
                                "api16-normal-c-useast1a.tiktokv.com",
                                "api22-normal-c-useast1a.tiktokv.com",
                                "api16-normal-useast5.us.tiktokv.com",
                            ],
                        },
                        "tiktok": {
                            "app_info": [
                                "musical_ly/35.1.3/2023501030/0",
                                "musical_ly/36.7.4/2023607040/0",
                                "musical_ly/37.1.4/2023701040/0",
                            ],
                            "api_hostname": [
                                "api16-normal-c-useast1a.tiktokv.com",
                                "api22-normal-c-useast1a.tiktokv.com",
                                "api16-normal-useast5.us.tiktokv.com",
                            ],
                        },
                    },
                }
            )

        cookie_file = (YTDLP_COOKIES_FILE or "").strip()
        if cookie_file:
            if os.path.exists(cookie_file):
                ydl_opts["cookiefile"] = cookie_file
            else:
                logger.warning("YTDLP_COOKIES_FILE is set but file does not exist: %s", cookie_file)

        cookies_from_browser = self._parse_cookies_from_browser(YTDLP_COOKIES_FROM_BROWSER)
        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = cookies_from_browser

        return ydl_opts

    @staticmethod
    def _parse_cookies_from_browser(raw_value: str) -> Optional[Tuple[str, ...]]:
        """
        Parse env string into yt-dlp `cookiesfrombrowser` tuple.

        Examples:
        - chrome
        - firefox:default-release
        - edge::Profile 1
        """
        if not raw_value:
            return None

        parts = [part.strip() for part in raw_value.split(":")]
        if not parts or not parts[0]:
            return None

        values: List[str] = [parts[0]]
        for part in parts[1:4]:
            if part:
                values.append(part)
        return tuple(values)

    def _download_with_ytdlp(
        self,
        url: str,
        temp_dir: str,
        is_audio: bool,
        allowed_ext: Tuple[str, ...],
        use_tiktok_app_api: bool,
    ) -> Optional[str]:
        """Blocking yt-dlp execution function used in thread pool."""
        from yt_dlp import YoutubeDL

        options = self._build_ytdlp_options(
            temp_dir=temp_dir,
            is_audio=is_audio,
            use_tiktok_app_api=use_tiktok_app_api,
        )

        with YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
        return self._find_latest_file(temp_dir, allowed_ext)

    @staticmethod
    def _find_latest_file(temp_dir: str, allowed_ext: Tuple[str, ...]) -> Optional[str]:
        files = []
        for entry in Path(temp_dir).iterdir():
            if not entry.is_file():
                continue
            if allowed_ext and entry.suffix.lower() not in allowed_ext:
                continue
            files.append(entry)

        if not files:
            files = [entry for entry in Path(temp_dir).iterdir() if entry.is_file()]
        if not files:
            return None
        return str(max(files, key=lambda item: item.stat().st_mtime))

    async def _send_file(self, callback_query: Any, filepath: str, mode: str, status_msg: Any) -> None:
        from aiogram.types import FSInputFile

        if status_msg:
            try:
                await status_msg.edit_text("Отправляю файл в Telegram...")
            except Exception:
                pass

        caption = f"Готово: {Path(filepath).name}"
        file = FSInputFile(filepath)

        try:
            if mode == FileFormat.AUDIO.value:
                await callback_query.message.answer_audio(audio=file, caption=caption)
            else:
                await callback_query.message.answer_video(video=file, caption=caption)
        except Exception:
            await callback_query.message.answer_document(document=file, caption=caption)

        if status_msg:
            try:
                await status_msg.edit_text("Загрузка завершена.")
            except Exception:
                pass

    async def _handle_download_error(
        self,
        callback_query: Any,
        error: Exception,
        url: str,
        status_msg: Any,
    ) -> None:
        if status_msg:
            try:
                await status_msg.edit_text("Ошибка при загрузке.")
            except Exception:
                pass

        msg = str(error).lower()
        is_expected = (
            "drm protected" in msg
            or "unable to extract webpage video data" in msg
            or "video not available" in msg
        )
        if is_expected:
            logger.warning("Download failed for user=%s url=%s: %s", callback_query.from_user.id, url, error)
        else:
            logger.error("Download failed for user=%s url=%s", callback_query.from_user.id, url, exc_info=True)

        user_message = error_manager.to_user_message(error, url=url)
        await callback_query.message.answer(user_message, parse_mode="HTML")

    def get_active_downloads_count(self) -> int:
        return self.processing

    def get_user_active_downloads(self, user_id: int) -> int:
        active = len(self.active_tasks.get(user_id, set()))
        queued = self.queued_tasks.get(user_id, 0)
        return active + queued

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    async def stop(self) -> None:
        """Stop worker tasks gracefully."""
        for _ in self._workers:
            await self.queue.put(None)

        for worker in self._workers:
            try:
                await worker
            except Exception:
                logger.exception("Worker stop failed")
