"""
Извлечение кадров-кандидатов для разметки датасета взрыв/прицел/фон.

Не читает вслепую всё видео подряд — использует уже существующие детекторы
(ExplosionDetector, ScopeDetector) на ПОВЫШЕННОЙ чувствительности, чтобы
поймать максимум потенциальных кандидатов (включая ложные срабатывания —
это нормально и ожидаемо, отсеивать их будет человек в label_tool.py).
Дополнительно берёт случайную выборку кадров, НЕ отмеченных ни одним
детектором, как кандидатов в класс "фон" — без явных негативных примеров
классификатор не сможет отличить "ничего не происходит" от взрыва/прицела.

Кандидаты сохраняются как JPEG в dataset/_staging/ с именем, кодирующим
источник и ПРЕДПОЛАГАЕМУЮ метку (это только подсказка для человека при
разметке, не финальное решение — его принимает label_tool.py по факту клика).
"""

import json
import os
import random
from typing import List, Tuple

import cv2

from modules.detectors.explosion_detector import ExplosionDetector
from modules.detectors.scope_detector import ScopeDetector

STAGING_DIR = os.path.join("dataset", "_staging")
PROCESSED_LOG = os.path.join("dataset", "_processed_videos.json")

EXTRACTION_FPS = 6.0
MIN_BACKGROUND_GAP_SECONDS = 2.0


def _load_processed() -> dict:
    if not os.path.exists(PROCESSED_LOG):
        return {}
    with open(PROCESSED_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_processed(processed: dict) -> None:
    os.makedirs(os.path.dirname(PROCESSED_LOG), exist_ok=True)
    with open(PROCESSED_LOG, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)


def _safe_stem(video_path: str) -> str:
    base = os.path.splitext(os.path.basename(video_path))[0]
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in base)


def extract_candidates(video_path: str, max_background: int = 40,
                        sensitivity: float = 85.0) -> Tuple[int, int, int]:
    """
    Сканирует видео, сохраняет кандидатов в STAGING_DIR.
    Возвращает (число_взрыв_кандидатов, число_прицел_кандидатов, число_фон_кандидатов).
    Повторный вызов на уже обработанном видео ничего не делает (см. _processed_videos.json).
    """
    processed = _load_processed()
    abs_path = os.path.abspath(video_path)
    if abs_path in processed:
        print(f"  Пропущено (уже обработано ранее): {video_path}")
        return (0, 0, 0)

    os.makedirs(STAGING_DIR, exist_ok=True)
    stem = _safe_stem(video_path)

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        print(f"  ОШИБКА: не удалось открыть {video_path}")
        return (0, 0, 0)

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_skip = max(int(round(fps / EXTRACTION_FPS)), 1)

    explosion_detector = ExplosionDetector(sensitivity=sensitivity)
    scope_detector = ScopeDetector(sensitivity=sensitivity)

    positive_count = {"explosion": 0, "scope": 0}
    background_pool: List[Tuple[int, float]] = []  # (frame_index, timestamp) без срабатываний
    last_background_time = -MIN_BACKGROUND_GAP_SECONDS

    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        if frame_index % frame_skip == 0:
            timestamp = frame_index / fps
            explosion_hits = explosion_detector.analyze_frame(frame, timestamp)
            scope_hits = scope_detector.analyze_frame(frame, timestamp)

            if explosion_hits:
                _save_candidate(frame, stem, timestamp, "explosion")
                positive_count["explosion"] += 1
            elif scope_hits:
                _save_candidate(frame, stem, timestamp, "scope")
                positive_count["scope"] += 1
            elif timestamp - last_background_time >= MIN_BACKGROUND_GAP_SECONDS:
                background_pool.append((frame_index, timestamp))
                last_background_time = timestamp

        frame_index += 1

    capture.release()

    # Из всех "спокойных" моментов берём случайную выборку под фон,
    # чтобы не заваливать разметчика тысячами однообразных кадров.
    background_sample = random.sample(background_pool, min(max_background, len(background_pool)))
    capture = cv2.VideoCapture(video_path)
    background_count = 0
    for frame_index, timestamp in background_sample:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if ok:
            _save_candidate(frame, stem, timestamp, "background")
            background_count += 1
    capture.release()

    processed[abs_path] = {
        "explosion_candidates": positive_count["explosion"],
        "scope_candidates": positive_count["scope"],
        "background_candidates": background_count,
    }
    _save_processed(processed)

    return (positive_count["explosion"], positive_count["scope"], background_count)


def _save_candidate(frame_bgr, video_stem: str, timestamp: float, suggested_label: str) -> None:
    minutes, seconds = divmod(int(timestamp), 60)
    ms = int((timestamp % 1) * 1000)
    filename = f"{video_stem}_{minutes:02d}m{seconds:02d}s{ms:03d}_{suggested_label}.jpg"
    path = os.path.join(STAGING_DIR, filename)
    cv2.imwrite(path, frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
