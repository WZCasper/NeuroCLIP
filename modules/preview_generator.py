"""
МОДУЛЬ 4, часть 2: Генерация превью.

1. Выбор кадра "максимального экшена" — не абстрактная метрика движения, а
   переиспользование уже посчитанных данных: кадр берётся из события с
   наибольшим произведением "зрелищности источника" (взрыв заметнее, чем
   лёгкий звуковой пик) и уверенности детектора. Это честнее и надёжнее,
   чем городить отдельный, ничем не проверенный алгоритм "экшена" с нуля.
2. Удаление фона через rembg (сегментационная модель, скачивается при первом
   использовании).
3. Наложение заголовка — переиспользует ту же технику неонового свечения
   (настоящий Gaussian Blur), что и брендовый неймплейт в ui/nameplate.py.

ЧЕСТНО ПРО ТЕСТИРОВАНИЕ: скачать модель rembg (u2net.onnx) не удалось и из
моей среды — тот же заблокированный домен releases-assets.githubusercontent.com,
что и с YOLO/MediaPipe/Whisper (пятый раз за проект). Выбор кадра и генерация
заголовка протестированы полностью — это чистая логика без внешних моделей.
Удаление фона у вас должно сработать штатно при обычном интернете; если нет —
превью всё равно соберётся, просто с исходным (не обрезанным) фоном кадра,
без падения программы.
"""

import os
from collections import Counter
from typing import List, Optional, Tuple

import cv2
from PIL import Image

from modules.detectors.base import DetectionEvent
from ui import theme
from ui.nameplate import render_glow_text

_SOURCE_VISUAL_WEIGHT = {
    "explosion": 5.0,
    "killfeed": 4.0,
    "audio_peak": 3.0,
    "low_hp": 2.0,
    "eye_contact": 2.0,
    "laughter": 1.0,
}
_DEFAULT_WEIGHT = 1.0


class PreviewError(Exception):
    """Не удалось собрать превью (нет кадра, сбой чтения видео и т.п.)."""


class BackgroundRemovalError(Exception):
    """Не удалось убрать фон (нет rembg, не скачалась модель и т.п.) — не
    критично, build_preview в этом случае просто оставляет исходный фон."""


def select_best_frame_timestamp(events: List[DetectionEvent]) -> Optional[float]:
    """
    Выбирает секунду для превью — момент события с максимальной "зрелищностью"
    (вес типа события × уверенность детектора). None, если событий нет.
    """
    if not events:
        return None

    def score(event: DetectionEvent) -> float:
        return _SOURCE_VISUAL_WEIGHT.get(event.source, _DEFAULT_WEIGHT) * event.confidence

    return max(events, key=score).timestamp


def generate_title(events: List[DetectionEvent]) -> str:
    """Генерирует заголовок превью на основе статистики найденных событий —
    простые понятные правила, без ML."""
    counts = Counter(event.source for event in events)

    if counts.get("killfeed", 0) >= 3:
        return "МЕГА-ФРАГ"
    if counts.get("explosion", 0) >= 2:
        return "ЧИСТЫЙ ХАОС"
    if counts.get("low_hp", 0) >= 1 and counts.get("killfeed", 0) >= 1:
        return "ВЫЖИЛ НА ГРАНИ"
    if counts.get("killfeed", 0) >= 1:
        return "ФРАГ"
    if counts.get("laughter", 0) >= 1:
        return "УГАР В СКВАДЕ"
    if counts.get("explosion", 0) >= 1:
        return "ВЗРЫВНОЙ МОМЕНТ"
    return "ЛУЧШИЙ МОМЕНТ"


def extract_frame(video_path: str, timestamp: float) -> Image.Image:
    """Извлекает один кадр видео на заданной секунде как PIL.Image (RGB)."""
    capture = cv2.VideoCapture(video_path)
    try:
        if not capture.isOpened():
            raise PreviewError(f"Не удалось открыть видео: {video_path}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(int(timestamp * fps), 0))
        ok, frame_bgr = capture.read()
        if not ok:
            raise PreviewError(f"Не удалось прочитать кадр на {timestamp:.1f}с")
        return Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()


def remove_background(image: Image.Image) -> Image.Image:
    """Убирает фон через rembg. Возвращает RGBA-изображение с прозрачным фоном."""
    try:
        from rembg import remove
    except ImportError as exc:
        raise BackgroundRemovalError(
            "Пакет 'rembg' не установлен. Установите: pip install rembg"
        ) from exc

    try:
        result = remove(image)
    except Exception as exc:
        raise BackgroundRemovalError(f"Не удалось убрать фон: {exc}") from exc

    return result.convert("RGBA") if result.mode != "RGBA" else result


def _overlay_title(base_image: Image.Image, title: str) -> Image.Image:
    """Накладывает заголовок с неоновым свечением в нижней трети изображения."""
    canvas = base_image.convert("RGBA")
    width, height = canvas.size

    font_size = max(int(width * 0.09), 28)
    title_layer = render_glow_text(title, size=font_size, color=theme.TEXT_PRIMARY,
                                    glow_radius=max(int(font_size * 0.2), 6))

    # Вписываем по ширине, если заголовок оказался шире холста
    if title_layer.width > width * 0.92:
        scale = (width * 0.92) / title_layer.width
        title_layer = title_layer.resize(
            (int(title_layer.width * scale), int(title_layer.height * scale)), Image.LANCZOS
        )

    x = (width - title_layer.width) // 2
    y = int(height * 0.78) - title_layer.height // 2
    canvas.alpha_composite(title_layer, (x, y))
    return canvas


def build_preview(
    video_path: str,
    events: List[DetectionEvent],
    output_path: str,
    title: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Собирает финальное превью: кадр максимального экшена + (по возможности)
    удалённый фон + наложенный заголовок. Сохраняет в output_path (PNG).

    Возвращает (output_path, background_was_removed) — второй элемент False,
    если rembg недоступен/не смог убрать фон — превью всё равно собирается,
    просто с исходным фоном кадра.
    """
    timestamp = select_best_frame_timestamp(events)
    if timestamp is None:
        raise PreviewError("Нет событий для генерации превью — сначала запустите анализ.")

    frame = extract_frame(video_path, timestamp)

    background_removed = False
    try:
        subject_rgba = remove_background(frame)
        canvas = Image.new("RGB", frame.size, theme.hex_to_rgb(theme.resolve(theme.BG_PRIMARY)))
        canvas.paste(subject_rgba, (0, 0), subject_rgba)
        base_image = canvas
        background_removed = True
    except BackgroundRemovalError:
        base_image = frame.convert("RGB")

    final_title = title if title is not None else generate_title(events)
    result_image = _overlay_title(base_image, final_title)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    result_image.convert("RGB").save(output_path, quality=95)

    return output_path, background_removed
