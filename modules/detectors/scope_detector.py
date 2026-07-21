"""
Детектор прицела снайперской винтовки.

Когда игрок прицеливается через оптику в Call of Duty, экран почти
полностью закрывается чёрной маской с круглым "окном" в центре — это
геометрически очень характерный, стабильный паттерн (в отличие от взрыва,
который у каждой игры/эффекта выглядит немного иначе).

АЛГОРИТМ (реальный, не имитация), два уровня:
1. Быстрая проверка (на каждом кадре): доля почти чёрных пикселей во всём
   кадре должна попадать в характерный диапазон для маски прицела (не
   слишком мало — значит, маски нет; не слишком много — значит, это,
   скорее, чёрный экран загрузки/смерти), а центральная область кадра
   должна оставаться "живой" (не быть тёмной) — иначе это может быть
   и просто закрытые глаза персонажа/тёмная сцена.
2. Если быстрая проверка проходит — подтверждение через cv2.HoughCircles
   на границе тёмной маски: реальная круглая граница специально ищется,
   а не просто предполагается по соотношению тёмных пикселей.
"""

from typing import List, Optional

import cv2
import numpy as np

from modules.detectors.base import DetectionEvent

_COOLDOWN_SECONDS = 2.5  # было 1.0
_DARK_THRESHOLD = 25          # яркость (0-255), ниже которой пиксель считается "чёрным"
_MIN_DARK_RATIO = 0.45         # минимальная доля чёрных пикселей в кадре для маски прицела
_MAX_DARK_RATIO = 0.90         # максимальная — иначе это, вероятно, просто чёрный экран


class ScopeDetector:
    """Детектор кругового виньетирования оптического прицела."""

    def __init__(self, sensitivity: float = 50.0, center_box_ratio: float = 0.18):
        self.sensitivity = max(0.0, min(sensitivity, 100.0))
        self.center_box_ratio = center_box_ratio  # размер центральной проверочной зоны
        self._last_event_time: float = -_COOLDOWN_SECONDS

    def reset(self) -> None:
        self._last_event_time = -_COOLDOWN_SECONDS

    def _quick_check(self, gray: np.ndarray) -> Optional[float]:
        """Быстрая проверка по соотношению тёмных пикселей. Возвращает dark_ratio или None."""
        height, width = gray.shape
        dark_mask = gray < _DARK_THRESHOLD
        dark_ratio = float(np.count_nonzero(dark_mask)) / (height * width)

        if not (_MIN_DARK_RATIO <= dark_ratio <= _MAX_DARK_RATIO):
            return None

        # Центральная область не должна быть тёмной — там "окно" прицела.
        box_h = int(height * self.center_box_ratio)
        box_w = int(width * self.center_box_ratio)
        cy, cx = height // 2, width // 2
        center_region = gray[cy - box_h:cy + box_h, cx - box_w:cx + box_w]
        if center_region.size == 0:
            return None

        center_dark_ratio = float(np.count_nonzero(center_region < _DARK_THRESHOLD)) / center_region.size
        if center_dark_ratio > 0.3:
            return None  # центр тоже тёмный -> это не прицел (весь кадр просто тёмный)

        return dark_ratio

    @staticmethod
    def _confirm_circle(gray: np.ndarray) -> bool:
        """Подтверждение через поиск круглой границы между маской и центром (Hough Circle)."""
        height, width = gray.shape
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        min_dim = min(height, width)

        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=1.5, minDist=min_dim,
            param1=60, param2=40,
            minRadius=int(min_dim * 0.15), maxRadius=int(min_dim * 0.5),
        )
        return circles is not None and len(circles[0]) > 0

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        dark_ratio = self._quick_check(gray)
        if dark_ratio is None:
            return []
        if timestamp - self._last_event_time < _COOLDOWN_SECONDS:
            return []

        # Чувствительность сдвигает, насколько обязательно геометрическое
        # подтверждение кругом: при высокой чувствительности достаточно
        # быстрой проверки; при низкой — требуем реальный найденный круг.
        require_circle = self.sensitivity < 70.0
        circle_confirmed = self._confirm_circle(gray)

        if require_circle and not circle_confirmed:
            return []

        self._last_event_time = timestamp
        confidence = 0.95 if circle_confirmed else 0.6
        return [DetectionEvent(
            timestamp=timestamp,
            source="explosion",  # использует тот же слайдер "Взрывы/прицел", что и explosion
            confidence=confidence,
            label="Прицеливание через оптику" + (" (круг подтверждён)" if circle_confirmed else ""),
            metadata={"dark_ratio": round(dark_ratio, 3), "circle_confirmed": circle_confirmed},
        )]
