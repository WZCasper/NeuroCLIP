"""
Детектор критически низкого HP.

Warzone (как и большинство игр Call of Duty) при низком здоровье показывает
красную виньетку по краям экрана — это стабильный визуальный сигнал,
не зависящий от разрешения HUD или его масштаба. Он надёжнее, чем попытка
читать числовое значение полоски HP: сама полоска мелкая, её точное
положение и формат менялись между сезонами игры, и распознавание
потребовало бы OCR на маленьком элементе — гораздо более хрупкое решение.

АЛГОРИТМ (реальный, не имитация):
1. Кадр переводится в HSV.
2. Строится маска "красного" оттенка (два диапазона, т.к. красный
   "оборачивается" через границу 0°/180° в цветовом круге OpenCV).
3. Считается доля красных пикселей в кольцевой зоне по периметру кадра
   (там, где рендерится виньетка) — не по всему кадру, чтобы яркая красная
   текстура в центре экрана (кровь, огонь и т.п.) не давала ложных срабатываний.
4. Если доля превышает порог (зависит от чувствительности пользователя)
   и прошло достаточно времени с прошлого события — фиксируется DetectionEvent.
"""

from typing import List

import cv2
import numpy as np

from modules.detectors.base import DetectionEvent

# HSV-диапазоны красного оттенка (Hue идёт 0-180 в OpenCV, а не 0-360)
_RED_RANGES = (
    (np.array([0, 70, 50]), np.array([10, 255, 255])),
    (np.array([170, 70, 50]), np.array([180, 255, 255])),
)

_COOLDOWN_SECONDS = 4.5  # было 3.0  # не повторять событие чаще, чем раз в столько секунд


class LowHPDetector:
    """Детектор красной виньетки низкого здоровья."""

    def __init__(self, sensitivity: float = 50.0, vignette_thickness_ratio: float = 0.16):
        """
        sensitivity: 0-100 (со слайдера пользователя). Чем выше — тем меньшей
            доли красных пикселей достаточно для срабатывания.
        vignette_thickness_ratio: толщина кольца анализа как доля меньшей
            стороны кадра. 0.16 — разумное значение для полноэкранной записи.
        """
        self.sensitivity = max(0.0, min(sensitivity, 100.0))
        self.vignette_thickness_ratio = vignette_thickness_ratio
        self._last_event_time: float = -_COOLDOWN_SECONDS
        self._cached_mask_key = None
        self._cached_mask: np.ndarray = None

    def reset(self) -> None:
        self._last_event_time = -_COOLDOWN_SECONDS

    def _get_ring_mask(self, height: int, width: int) -> np.ndarray:
        """Кэширует маску кольца по размеру кадра, чтобы не пересчитывать каждый раз."""
        key = (height, width)
        if key != self._cached_mask_key:
            thickness = max(int(min(height, width) * self.vignette_thickness_ratio), 1)
            mask = np.zeros((height, width), dtype=np.uint8)
            mask[:] = 255
            mask[thickness:height - thickness, thickness:width - thickness] = 0
            self._cached_mask_key = key
            self._cached_mask = mask
        return self._cached_mask

    def _red_ratio_in_vignette(self, frame_bgr: np.ndarray) -> float:
        height, width = frame_bgr.shape[:2]
        ring_mask = self._get_ring_mask(height, width)

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        red_mask = np.zeros((height, width), dtype=np.uint8)
        for lower, upper in _RED_RANGES:
            red_mask = cv2.bitwise_or(red_mask, cv2.inRange(hsv, lower, upper))

        red_in_ring = cv2.bitwise_and(red_mask, ring_mask)
        ring_area = int(np.count_nonzero(ring_mask))
        if ring_area == 0:
            return 0.0
        return float(np.count_nonzero(red_in_ring)) / ring_area

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        ratio = self._red_ratio_in_vignette(frame_bgr)

        # sensitivity 0 -> порог 35% (нужно очень много красного)
        # sensitivity 100 -> порог 6% (срабатывает от лёгкого намёка)
        threshold = 0.35 - (self.sensitivity / 100.0) * 0.29

        if ratio < threshold:
            return []
        if timestamp - self._last_event_time < _COOLDOWN_SECONDS:
            return []

        self._last_event_time = timestamp
        confidence = round(min(ratio / max(threshold, 1e-6), 1.0), 2)
        return [DetectionEvent(
            timestamp=timestamp,
            source="low_hp",
            confidence=confidence,
            label="Критически низкое HP",
            metadata={"red_ratio": round(ratio, 4), "threshold": round(threshold, 4)},
        )]
