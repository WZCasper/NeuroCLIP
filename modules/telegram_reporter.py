"""
МОДУЛЬ 3: Телеграм-репортер.

Отправляет скриншот текущего кадра предпросмотра вместе с метаданными об
ошибке в Telegram-чат через реальные HTTP-запросы к Bot API (requests.post).
Никаких заглушек: сеть, сериализация изображения и обработка ошибок API
выполнены полностью.
"""

import datetime
import io
import threading
from typing import Callable, Optional

import requests
from PIL import Image

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

REQUEST_TIMEOUT = 15  # секунд


class TelegramReportError(Exception):
    """Выбрасывается при ошибке отправки репорта (сеть, неверный токен, отказ API)."""


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _build_caption(reporter: str, description: str, video_filename: Optional[str],
                    video_timestamp: Optional[float]) -> str:
    """Формирует текст подписи с метаданными ошибки."""
    lines = [
        "🔴 NEUROCLIP — ОШИБКА ИИ",
        f"👤 Репортит: {reporter}",
        f"🕒 Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if video_filename:
        lines.append(f"🎬 Файл: {video_filename}")
    if video_timestamp is not None:
        minutes, seconds = divmod(int(video_timestamp), 60)
        lines.append(f"⏱ Таймкод в видео: {minutes:02d}:{seconds:02d}")
    lines.append("")
    lines.append(f"📝 Описание: {description.strip() if description.strip() else '— не указано —'}")
    return "\n".join(lines)


def _raise_for_telegram_error(response: requests.Response) -> None:
    """Проверяет ответ Telegram API и выбрасывает понятную ошибку при неудаче."""
    try:
        payload = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise TelegramReportError("Некорректный (не-JSON) ответ от Telegram API.") from exc

    if not response.ok or not payload.get("ok", False):
        description = payload.get("description", f"HTTP {response.status_code}")
        raise TelegramReportError(f"Telegram API отклонил запрос: {description}")


def _send_photo(image: Image.Image, caption: str) -> None:
    """Отправляет JPEG-кадр с подписью через sendPhoto."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    files = {"photo": ("error_frame.jpg", buffer, "image/jpeg")}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}

    response = requests.post(_api_url("sendPhoto"), data=data, files=files, timeout=REQUEST_TIMEOUT)
    _raise_for_telegram_error(response)


def _send_text(text: str) -> None:
    """Отправляет текстовое сообщение (без скриншота) через sendMessage."""
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    response = requests.post(_api_url("sendMessage"), data=data, timeout=REQUEST_TIMEOUT)
    _raise_for_telegram_error(response)


def send_error_report(
    reporter: str,
    description: str,
    frame: Optional[Image.Image] = None,
    video_filename: Optional[str] = None,
    video_timestamp: Optional[float] = None,
    on_success: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Отправляет репорт об ошибке в Telegram в фоновом потоке, чтобы не
    блокировать интерфейс во время сетевого запроса.

    on_success() вызывается без аргументов при успехе.
    on_error(сообщение) вызывается с текстом ошибки при неудаче.
    Оба колбэка вызываются из фонового потока — вызывающая сторона обязана
    сама передать управление в главный поток Tkinter (например, через
    widget.after(0, ...)), если внутри колбэка обновляются виджеты.
    """

    def _worker() -> None:
        try:
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                raise TelegramReportError(
                    "Не задан TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID. "
                    "Заполните файл .env (см. .env.example) перед отправкой репортов."
                )

            caption = _build_caption(reporter, description, video_filename, video_timestamp)

            if frame is not None:
                _send_photo(frame, caption)
            else:
                _send_text(caption + "\n\n⚠️ Видео не загружено — кадр не приложен.")

            if on_success:
                on_success()

        except TelegramReportError as exc:
            if on_error:
                on_error(str(exc))
        except requests.exceptions.RequestException as exc:
            if on_error:
                on_error(f"Ошибка сети: {exc}")

    threading.Thread(target=_worker, daemon=True).start()
