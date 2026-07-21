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
from modules.audio_extractor import AudioExtractionError, extract_audio
from modules.detectors.audio_peak_detector import AudioPeakDetector
from modules.detectors.base import DetectionEvent
from modules.detectors.explosion_detector import ExplosionDetector
from modules.detectors.eye_contact_detector import EyeContactDetector
from modules.detectors.hp_detector import LowHPDetector
from modules.detectors.killfeed_detector import KillfeedDetector
from modules.detectors.laughter_detector import LaughterDetector
from modules.detectors.scope_detector import ScopeDetector
from state import AISettings

TARGET_ANALYSIS_FPS = 6.0

# Общий кулдаун МЕЖДУ ЛЮБЫМИ событиями, независимо от того, какой детектор их
# нашёл. У каждого детектора уже есть свой кулдаун, но на реальных записях
# (в отличие от чистой синтетики, на которой всё тестировалось) несколько
# разных детекторов могут срабатывать почти одновременно, создавая ощущение
# "что-то находится каждые пару секунд" — этот общий кулдаун служит жёсткой
# страховкой сверху индивидуальных, а не заменяет их.
GLOBAL_EVENT_COOLDOWN_SECONDS = 3.0

# Если один источник даёт больше такой доли от всех найденных событий —
# это подозрительно похоже на то, что порог для него слишком чувствителен
# именно для этой записи, а не на честную статистику разных моментов.
_DOMINANT_SOURCE_FRACTION = 0.6
_DOMINANT_SOURCE_MIN_COUNT = 6


class AnalysisPipeline:
    """Запускает набор детекторов Модуля 2 по видео в фоновом потоке."""

    def __init__(self, settings: AISettings):
        self._settings = settings
        self._cancelled = False
        self._eye_contact_detector = None  # закрывается отдельно (держит ресурсы MediaPipe)
        self._last_any_event_time = -GLOBAL_EVENT_COOLDOWN_SECONDS

    def cancel(self) -> None:
        self._cancelled = True

    def _try_emit(self, event: DetectionEvent, all_events: List[DetectionEvent],
                   on_event: Callable[[DetectionEvent], None]) -> None:
        """Пропускает событие дальше, только если прошёл общий кулдаун с
        предыдущего ЛЮБОГО события — см. GLOBAL_EVENT_COOLDOWN_SECONDS."""
        if event.timestamp - self._last_any_event_time < GLOBAL_EVENT_COOLDOWN_SECONDS:
            return
        self._last_any_event_time = event.timestamp
        all_events.append(event)
        on_event(event)

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
        on_status: Callable[[str], None] = lambda msg: None,
        enable_laughter: bool = False,
    ) -> None:
        """
        Запускает анализ в фоновом потоке.

        Колбэки вызываются ИЗ ФОНОВОГО ПОТОКА — если внутри них обновляются
        виджеты Tkinter, вызывающая сторона обязана сама передать управление
        в главный поток (например, через widget.after(0, ...)).
        on_warning — некритичные предупреждения (детектор пропущен, но анализ
        продолжается остальными). on_status — информационный текст о текущем
        этапе (не проблема, просто "что сейчас происходит").
        enable_laughter — детектор смеха через Whisper ОТКЛЮЧЁН по умолчанию:
        он на порядок медленнее остальных (полная транскрипция аудио) и
        не является надёжным (см. честное примечание в laughter_detector.py).
        """

        def _worker() -> None:
            capture = cv2.VideoCapture(video_path)
            if not capture.isOpened():
                on_error(f"Не удалось открыть видео для анализа: {video_path}")
                return

            eye_contact_detector_ref = None
            try:
                fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
                frame_skip = max(int(round(fps / TARGET_ANALYSIS_FPS)), 1)

                detectors = self._build_detectors(on_warning)
                eye_contact_detector_ref = self._eye_contact_detector
                all_events: List[DetectionEvent] = []
                frame_index = 0

                on_status("Анализирую видео...")
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
                                self._try_emit(event, all_events, on_event)
                        # Видео — первые 70% общего прогресса, аудио-фазы — оставшиеся 30%
                        on_progress(min(frame_index / total_frames, 1.0) * 0.7)

                    frame_index += 1

                if self._cancelled:
                    return

                self._run_audio_phase(video_path, all_events, on_event, on_warning,
                                       on_status, on_progress, enable_laughter)

                all_events.sort(key=lambda e: e.timestamp)
                self._warn_if_dominant_source(all_events, on_warning)
                on_progress(1.0)
                on_done(all_events)
            finally:
                capture.release()
                if eye_contact_detector_ref is not None:
                    eye_contact_detector_ref.close()

        threading.Thread(target=_worker, daemon=True).start()

    def _warn_if_dominant_source(self, events: List[DetectionEvent],
                                  on_warning: Callable[[str], None]) -> None:
        """Если один источник даёт подавляющее большинство событий — это,
        скорее всего, означает, что порог для него слишком чувствителен
        именно для этой записи, а не честное распределение разных моментов.
        Подсказывает, какой именно ползунок стоит понизить."""
        if len(events) < _DOMINANT_SOURCE_MIN_COUNT:
            return

        counts: dict = {}
        for event in events:
            counts[event.source] = counts.get(event.source, 0) + 1

        source_names = {
            "low_hp": "«Низкое HP»", "killfeed": "«Килфид»",
            "explosion": "«Взрывы / прицел»", "audio_peak": "«Громкие звуки»",
            "eye_contact": "«Зрительный контакт»", "laughter": "распознавание смеха",
        }

        dominant_source, dominant_count = max(counts.items(), key=lambda kv: kv[1])
        if dominant_count / len(events) >= _DOMINANT_SOURCE_FRACTION:
            label = source_names.get(dominant_source, dominant_source)
            on_warning(
                f"Детектор {label} нашёл {dominant_count} из {len(events)} моментов — "
                f"похоже, порог слишком чувствителен для этой записи. Попробуйте "
                f"уменьшить соответствующий ползунок чувствительности и повторить анализ."
            )

    def _run_audio_phase(
        self, video_path: str, all_events: List[DetectionEvent],
        on_event: Callable[[DetectionEvent], None], on_warning: Callable[[str], None],
        on_status: Callable[[str], None], on_progress: Callable[[float], None],
        enable_laughter: bool,
    ) -> None:
        on_status("Извлекаю аудиодорожку...")
        try:
            wav_path = extract_audio(video_path)
        except AudioExtractionError as exc:
            on_warning(f"Аудио-анализ пропущен: {exc}")
            return

        try:
            on_progress(0.75)
            on_status("Ищу резкие звуковые пики...")
            peak_detector = AudioPeakDetector(sensitivity=self._settings.audio_peak_sensitivity)
            for event in peak_detector.analyze_audio(wav_path):
                self._try_emit(event, all_events, on_event)
            on_progress(0.85)

            if enable_laughter:
                on_status("Распознаю речь (Whisper) — это медленнее остального...")
                try:
                    laughter_detector = LaughterDetector(model_size="base")
                    for event in laughter_detector.analyze_audio(wav_path):
                        self._try_emit(event, all_events, on_event)
                except ImportError as exc:
                    on_warning(f"Детектор смеха отключён: {exc}")
                except Exception as exc:  # модель Whisper не скачалась, ошибка транскрипции и т.п.
                    on_warning(f"Детектор смеха пропущен из-за ошибки: {exc}")
            on_progress(0.95)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)
