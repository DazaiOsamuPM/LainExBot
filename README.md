# Telegram Downloader Bot

Минималистичный Telegram-бот для одной задачи: скачивание **видео** или **аудио** по ссылке.

## Что поддерживается
- YouTube
- TikTok
- Instagram
- Facebook
- X (Twitter)
- VK
- Reddit
- Pinterest
- Dailymotion
- Vimeo
- SoundCloud
- Прямые ссылки на медиафайлы (`.mp4`, `.mp3` и др.)

## Что убрано
- История загрузок
- Персональные настройки
- Админ-статистика
- Админская веб-статистика
- Лишние команды и callback-ветки

## Быстрый запуск
1. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
2. Добавьте в окружение:
   ```env
   BOT_TOKEN=your_token
   ```
3. Запустите:
   ```bash
   python main.py
   ```

## Команды
- `/start` — приветствие и краткая инструкция
- `/help` — как пользоваться

## Поток работы
1. Пользователь отправляет ссылку.
2. Бот показывает кнопки: `Скачать видео` / `Скачать аудио`.
3. Задача ставится в очередь.
4. `yt-dlp` скачивает файл, бот отправляет его в Telegram.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|--------------|-----------|
| `BOT_TOKEN` | — | Токен Telegram-бота (обязателен). |
| `LOG_LEVEL` | `INFO` | Уровень логирования. |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Сколько воркеров тянут файлы параллельно. |
| `MAX_USER_TASKS` | `2` | Лимит активных задач на пользователя. |
| `MAX_FILE_SIZE_MB` | `50` | Предельный размер файла для отправки. |
| `DOWNLOAD_TIMEOUT_SECONDS` | `600` | Таймаут одной загрузки. |
| `TELEGRAM_API_BASE` | — | URL self-hosted Bot API Server (включает лимит 2000 МБ). |
| `ENABLE_HEALTH_SERVER` | `false` | Включить HTTP `/health`, если хостинг требует открытый порт. |
| `MAX_PENDING_LINKS_PER_USER` | `20` | Сколько ссылок одного юзера хранить в ожидании выбора формата. |
| `USER_RATE_LIMIT_MESSAGES` / `USER_RATE_LIMIT_WINDOW_SECONDS` | `20` / `60` | Антиспам: максимум событий в окне. |
| `ALLOW_PRIVATE_URLS` | `false` | Разрешать локальные и приватные адреса (`127.0.0.1`, `10.0.0.0/8` и т.п.) для прямых ссылок. По умолчанию запрещено. |
| `YTDLP_COOKIES_FILE` | — | Путь к cookies.txt для yt-dlp. |
| `YTDLP_COOKIES_FROM_BROWSER` | — | Источник cookies из браузера, например `chrome` или `firefox:default-release`. |

## Ограничения по размеру файла

Публичный Telegram Bot API (`api.telegram.org`) пропускает через `sendVideo`/`sendAudio`/`sendDocument`
**не более 50 МБ**. Если нужно больше (до 2000 МБ), поднимите
[self-hosted Bot API Server](https://core.telegram.org/bots/api#using-a-local-bot-api-server)
и задайте `TELEGRAM_API_BASE=http://<host>:<port>` плюс соответствующий `MAX_FILE_SIZE_MB`.

## Деплой

Для VPS, systemd, Docker worker, Railway worker и похожих окружений достаточно запускать:

```bash
python main.py
```

HTTP health-endpoint по умолчанию выключен. Если хостинг требует открытый порт,
задайте `ENABLE_HEALTH_SERVER=true`; бот поднимет `/health` на `PORT` или `10000`.
