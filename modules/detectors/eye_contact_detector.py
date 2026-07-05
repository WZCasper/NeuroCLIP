"""
Детектор прямого взгляда в веб-камеру.

Использует MediaPipe FaceLandmarker (актуальный Tasks API — старый
mp.solutions.face_mesh в установленной версии библиотеки уже отсутствует)
для получения 478 ландмарок лица, затем передаёт координаты в
gaze_geometry.py — чистую, ОТДЕЛЬНО протестированную математику оценки
направления взгляда (7/7 тестов на сфабрикованных координатах, см. чат).

═══════════════════════════════════════════════════════════════════════
ОБЯЗАТЕЛЬНАЯ НАСТРОЙКА ПЕРЕД ИСПОЛЬЗОВАНИЕМ
═══════════════════════════════════════════════════════════════════════
FaceLandmarker не поставляется со встроенной моделью — нужен отдельный
файл face_landmarker.task. Это не костыль и не недоделка: библиотека
устроена так для ЛЮБОГО, кто ей пользуется, — модель нужно скачать один
раз вручную и положить рядом с проектом.

  1. Официальный источник:
     https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

  2. Если недоступен (Google Storage иногда блокируется по регионам) —
     неофициальное зеркало на GitHub (стороннее, используйте на свой риск,
     я не могу поручиться за файл, который не публиковал сам Google):
     https://github.com/sanderdesnaijer/mediapipe-model-mirrors/releases/download/v1/face_landmarker.task

  Сохраните файл как assets/models/face_landmarker.task (папку models
  создайте, её нет в текущей структуре проекта).

═══════════════════════════════════════════════════════════════════════
ЧЕСТНО ПРО ТЕСТИРОВАНИЕ ЭТОГО ФАЙЛА
═══════════════════════════════════════════════════════════════════════
Оба адреса модели выше проверены и заблокированы также и из моей рабочей
песочницы (домены storage.googleapis.com и release-assets.githubusercontent.com
недоступны оттуда) — значит, полный цикл "кадр -> обнаружение лица -> оценка
взгляда" я прогнать не смог. Подделать это синтетическим кадром тоже нельзя:
MediaPipe — нейросеть, обученная на настоящих лицах, нарисованный овал с
кружками она не распознает как лицо, и такой тест ничего бы не доказал.
Импорты и сигнатуры методов ниже проверены на реальном API библиотеки
(create_from_options, detect_for_video, структура FaceLandmarkerResult и
NormalizedLandmark — все проверены вызовами, не по памяти). Первый настоящий
прогон на реальном лице возможен только у вас, после того как появится файл
модели.
"""

from typing import List, Optional, Tuple

import cv2
import numpy as np

from modules.detectors.base import DetectionEvent
from modules.detectors.gaze_geometry import compute_gaze_state

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
    _MEDIAPIPE_AVAILABLE = True
except ImportError:
    _MEDIAPIPE_AVAILABLE = False

_COOLDOWN_SECONDS = 2.0
_REQUIRED_LANDMARK_INDICES = [1, 33, 133, 159, 145, 468, 263, 362, 386, 374, 473]


class EyeContactDetector:
    """
    Детектор прямого взгляда в камеру.

    ПРЕДПОЛОЖЕНИЕ ОБ АРХИТЕКТУРЕ: рассчитан на facecam, наложенный поверх
    геймплея в том же видео (обычная практика у стримеров) — укажите его
    зону через facecam_roi. Если веб-камера — отдельный файл целиком с
    лицом, оставьте facecam_roi=None (анализируется весь кадр).
    """

    def __init__(self, model_path: str, sensitivity: float = 50.0,
                 facecam_roi: Optional[Tuple[float, float, float, float]] = None):
        if not _MEDIAPIPE_AVAILABLE:
            raise ImportError("Пакет 'mediapipe' не установлен. Установите: pip install mediapipe")

        self.sensitivity = max(0.0, min(sensitivity, 100.0))
        self.facecam_roi = facecam_roi  # (x1, y1, x2, y2) в долях кадра, 0.0-1.0
        self._last_event_time: float = -_COOLDOWN_SECONDS

        base_options = BaseOptions(model_asset_path=model_path)
        options = FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def reset(self) -> None:
        self._last_event_time = -_COOLDOWN_SECONDS

    def _extract_roi(self, frame_bgr: np.ndarray) -> np.ndarray:
        if self.facecam_roi is None:
            return frame_bgr
        height, width = frame_bgr.shape[:2]
        x1, y1, x2, y2 = self.facecam_roi
        return frame_bgr[int(y1 * height):int(y2 * height), int(x1 * width):int(x2 * width)]

    def _sensitivity_to_tolerances(self) -> dict:
        # sensitivity 0 -> строгие допуски; sensitivity 100 -> мягкие
        return {
            "horizontal_tolerance": 0.10 + (self.sensitivity / 100.0) * 0.16,
            "vertical_tolerance": 0.12 + (self.sensitivity / 100.0) * 0.18,
        }

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        roi_bgr = self._extract_roi(frame_bgr)
        if roi_bgr.size == 0:
            return []

        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=roi_rgb)

        result = self._landmarker.detect_for_video(mp_image, int(timestamp * 1000))
        if not result.face_landmarks:
            return []

        face = result.face_landmarks[0]
        if len(face) <= max(_REQUIRED_LANDMARK_INDICES):
            return []  # модель вернула меньше точек, чем ожидалось — пропускаем кадр

        landmarks = {i: (face[i].x, face[i].y) for i in _REQUIRED_LANDMARK_INDICES}
        gaze = compute_gaze_state(landmarks, **self._sensitivity_to_tolerances())

        if not gaze.is_looking_at_camera:
            return []
        if timestamp - self._last_event_time < _COOLDOWN_SECONDS:
            return []

        self._last_event_time = timestamp
        return [DetectionEvent(
            timestamp=timestamp,
            source="eye_contact",
            confidence=gaze.confidence,
            label="Прямой взгляд в камеру",
            metadata={
                "horizontal_ratio": gaze.horizontal_ratio,
                "vertical_ratio": gaze.vertical_ratio,
                "frontality_ratio": gaze.frontality_ratio,
            },
        )]

    def close(self) -> None:
        """Освобождает ресурсы MediaPipe. Обязательно вызовите после анализа видео."""
        self._landmarker.close()
