"""
Оркестратор анализа видео.

Прогоняет доступные детекторы Модуля 2 по видеофайлу и собирает единый
список DetectionEvent. Работает в фоновом потоке (анализ длинной записи
занимает время, интерфейс не должен зависать).

Кадры анализируются с фиксированной частотой TARGET_ANALYSIS_FPS, а не на
каждом кадре исходника: события вроде красной виньетки или новой строки
килфида держатся на экране гораздо дольше 1/30 секунды, поэтому разумное
прореживание не теряет события, зато на порядок ускоряет обработку
длинных записей (например, часовой стрим при 30 fps — это 108 000 кадров;
при целевой частоте анализа 6 fps это всего 21 600 проходов).
"""

import os
import threading
from typing import Callable, List

import cv2

from config import FACE_LANDMARKER_MODEL_PATH
from modules.detectors.base import DetectionEvent
from modules.detectors.explosion_detector import ExplosionDetector
from modules.detectors.eye_contact_detector import EyeContactDetector
from modules.detectors.hp_detector import LowHPDetector
from modules.detectors.killfeed_detector import KillfeedDetector
from modules.detectors.scope_detector import ScopeDetector
from state import AISettings

TARGET_ANALYSIS_FPS = 6.0


class AnalysisPipeline:
    """Запускает набор детекторов Модуля 2 по видео в фоновом потоке."""

    def __init__(self, settings: AISettings):
        self._settings = settings
        self._cancelled = False
        self._eye_contact_detector = None  # закрывается отдельно (держит ресурсы MediaPipe)

    def cancel(self) -> None:
        self._cancelled = True

    def _build_detectors(self, on_warning: Callable[[str], None]) -> list:
        detectors = [
            LowHPDetector(sensitivity=self._settings.low_hp_sensitivity),
            KillfeedDetector(sensitivity=self._settings.killfeed_sensitivity),
            ExplosionDetector(sensitivity=self._settings.explosion_sensitivity),
            ScopeDetector(sensitivity=self._settings.explosion_sensitivity),
        ]

        if os.path.exists(FACE_LANDMARKER_MODEL_PATH):
            try:
                self._eye_contact_detector = EyeContactDetector(
                    model_path=FACE_LANDMARKER_MODEL_PATH,
                    sensitivity=self._settings.eye_contact_sensitivity,
                )
                detectors.append(self._eye_contact_detector)
            except Exception as exc:  # ImportError (нет mediapipe) или ошибка модели
                on_warning(f"Детектор зрительного контакта отключён: {exc}")
        else:
            on_warning(
                "Детектор зрительного контакта пропущен: не найден файл "
                f"{FACE_LANDMARKER_MODEL_PATH} (см. eye_contact_detector.py, "
                "как его скачать)."
            )

        return detectors

    def run(
        self,
        video_path: str,
        on_progress: Callable[[float], None],
        on_event: Callable[[DetectionEvent], None],
        on_done: Callable[[List[DetectionEvent]], None],
        on_error: Callable[[str], None],
        on_warning: Callable[[str], None] = lambda msg: None,
    ) -> None:
        """
        Запускает анализ в фоновом потоке.

        Колбэки вызываются ИЗ ФОНОВОГО ПОТОКА — если внутри них обновляются
        виджеты Tkinter, вызывающая сторона обязана сама передать управление
        в главный поток (например, через widget.after(0, ...)).
        on_warning — некритичные предупреждения (например, детектор
        зрительного контакта пропущен из-за отсутствия файла модели);
        анализ продолжается остальными детекторами.
        """

        def _worker() -> None:
            capture = cv2.VideoCapture(video_path)
            if not capture.isOpened():
                on_error(f"Не удалось открыть видео для анализа: {video_path}")
                return

            try:
                fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
                frame_skip = max(int(round(fps / TARGET_ANALYSIS_FPS)), 1)

                detectors = self._build_detectors(on_warning)
                all_events: List[DetectionEvent] = []
                frame_index = 0

                while True:
                    if self._cancelled:
                        return

                    ok, frame = capture.read()
                    if not ok:
                        break

                    if frame_index % frame_skip == 0:
                        timestamp = frame_index / fps
                        for detector in detectors:
                            for event in detector.analyze_frame(frame, timestamp):
                                all_events.append(event)
                                on_event(event)
                        on_progress(min(frame_index / total_frames, 1.0))

                    frame_index += 1

                all_events.sort(key=lambda e: e.timestamp)
                on_progress(1.0)
                on_done(all_events)
            finally:
                capture.release()
                if self._eye_contact_detector is not None:
                    self._eye_contact_detector.close()

        threading.Thread(target=_worker, daemon=True).start()
