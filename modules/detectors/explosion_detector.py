"""
Детектор взрывов (и похожих ярких вспышек — см. честное примечание ниже).

АЛГОРИТМ (реальный, не имитация):
1. Отслеживаем среднюю яркость кадра (luminance) от кадра к кадру.
2. Взрыв даёт РЕЗКИЙ скачок яркости за один шаг анализа — не постепенное
   изменение освещения (как рассвет/переход между помещениями), а всплеск.
3. Проверяем цветовую характеристику ярких пикселей: у взрывов и похожих
   вспышек преобладают тёплые/белые тона (оранжевый, жёлтый, белый) —
   это отсекает часть случаев, когда экран резко становится ярким по
   другой причине (например, вспышка UI-эффекта другого цвета).
4. Если оба условия выполнены и прошёл cooldown — фиксируется событие.

ЧЕСТНО ПРО ТОЧНОСТЬ: это детектор "яркой вспышки", а не семантический
классификатор "это именно взрыв, а не флешбанг/другой яркий VFX". Взрыв,
флешбанг и похожие эффекты дают очень похожий сигнал по яркости и цвету —
различить их надёжно без обученной на размеченных примерах модели
(YOLO/CNN) практически невозможно. Для целей хайлайт-детектора это не
проблема: и то, и другое — обычно зрелищный момент, достойный клипа.
"""

from collections import deque
from typing import List

import cv2
import numpy as np

from modules.detectors.base import DetectionEvent

_COOLDOWN_SECONDS = 4.5  # было 2.0 - на реальных записях срабатывал слишком часто
_BASELINE_WINDOW = 5   # сколько прошлых кадров усредняем для baseline-яркости
_WARM_HUE_MAX = 45      # верхняя граница "тёплого" оттенка (оранжевый/жёлтый) в шкале OpenCV 0-180


class ExplosionDetector:
    """Детектор резкой яркой вспышки с тёплым/белым цветовым оттенком."""

    def __init__(self, sensitivity: float = 50.0):
        self.sensitivity = max(0.0, min(sensitivity, 100.0))
        self._brightness_history: deque = deque(maxlen=_BASELINE_WINDOW)
        self._last_event_time: float = -_COOLDOWN_SECONDS

    def reset(self) -> None:
        self._brightness_history.clear()
        self._last_event_time = -_COOLDOWN_SECONDS

    @staticmethod
    def _mean_brightness(frame_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    @staticmethod
    def _warm_bright_ratio(frame_bgr: np.ndarray, brightness_threshold: int = 200) -> float:
        """Доля ярких пикселей, которые к тому же тёплые/белые (не синие/зелёные/фиолетовые)."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        bright_mask = gray >= brightness_threshold
        bright_count = int(np.count_nonzero(bright_mask))
        if bright_count == 0:
            return 0.0

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        saturation = hsv[:, :, 1]

        # Тёплый цвет: оттенок в оранжево-жёлтом диапазоне, ИЛИ низкая насыщенность
        # (близко к белому — тоже характерно для яркой вспышки/взрыва).
        warm_or_white = ((hue <= _WARM_HUE_MAX) | (saturation <= 40)) & bright_mask
        return float(np.count_nonzero(warm_or_white)) / bright_count

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        current_brightness = self._mean_brightness(frame_bgr)

        if len(self._brightness_history) < self._brightness_history.maxlen:
            self._brightness_history.append(current_brightness)
            return []

        baseline = sum(self._brightness_history) / len(self._brightness_history)
        jump = current_brightness - baseline
        self._brightness_history.append(current_brightness)

        # sensitivity 0 -> нужен скачок минимум на 70 пунктов яркости (0-255)
        # sensitivity 100 -> достаточно скачка на 18 пунктов
        threshold = 100.0 - (self.sensitivity / 100.0) * 65.0  # было 70.0-52.0 - реальные вспышки от стрельбы оказались чаще и слабее киношного взрыва

        if jump < threshold:
            return []
        if timestamp - self._last_event_time < _COOLDOWN_SECONDS:
            return []

        warm_ratio = self._warm_bright_ratio(frame_bgr)
        if warm_ratio < 0.45:  # было 0.3 - строже отсекаем случайные яркие пятна
            return []  # яркая вспышка есть, но цвет не похож на взрыв/огонь/белую вспышку

        self._last_event_time = timestamp
        confidence = round(min(jump / max(threshold, 1e-6) * warm_ratio, 1.0), 2)
        return [DetectionEvent(
            timestamp=timestamp,
            source="explosion",
            confidence=confidence,
            label="Яркая вспышка (взрыв/эффект)",
            metadata={"brightness_jump": round(jump, 1), "warm_ratio": round(warm_ratio, 2)},
        )]
