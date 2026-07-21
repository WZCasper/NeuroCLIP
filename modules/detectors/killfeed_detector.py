"""
Детектор события в килфиде (kill feed) — правый верхний угол экрана, куда
Warzone выводит строки вида "ИгрокA уничтожил ИгрокB".

АЛГОРИТМ (реальный, не имитация):
1. Из кадра вырезается ROI килфида.
2. ROI сравнивается с ROI предыдущего проанализированного кадра
   (cv2.absdiff + порог) — появление новой строки даёт заметный всплеск
   изменившихся пикселей именно в этой зоне.
3. Если доля изменившихся пикселей превышает порог чувствительности —
   фиксируется событие.
4. Опционально (если установлен Tesseract OCR) делается best-effort попытка
   распознать текст строки для метаданных. Это не гарантия точного текста —
   зависит от разрешения записи, шрифта и HUD-скейла — но полезно для
   ручной проверки в репорте.

ВАЖНО: координаты ROI заданы в ДОЛЯХ ширины/высоты кадра (0.0-1.0), а не в
пикселях — так они не зависят от разрешения записи. Значения по умолчанию —
разумная отправная точка для полноэкранной записи 16:9 со стандартным HUD.
Если у вас другой HUD-скейл или соотношение сторон — проверьте и поправьте
через calibrate_roi.py (см. корень проекта).
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from modules.detectors.base import DetectionEvent

try:
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


@dataclass
class ROI:
    """Регион интереса в долях от размера кадра (0.0-1.0 по каждой оси)."""
    x1: float
    y1: float
    x2: float
    y2: float

    def to_pixels(self, width: int, height: int) -> Tuple[int, int, int, int]:
        return (
            int(self.x1 * width), int(self.y1 * height),
            int(self.x2 * width), int(self.y2 * height),
        )


# Отправная точка для killfeed в правом верхнем углу, полноэкранная запись 16:9.
# Проверьте на своей записи через calibrate_roi.py и поправьте при необходимости.
DEFAULT_KILLFEED_ROI = ROI(x1=0.62, y1=0.05, x2=0.99, y2=0.28)

_COOLDOWN_SECONDS = 3.0  # было 1.5


class KillfeedDetector:
    """Детектор появления новой строки в килфиде через покадровое сравнение ROI."""

    def __init__(self, roi: ROI = None, sensitivity: float = 50.0, enable_ocr: bool = True):
        self.roi = roi or DEFAULT_KILLFEED_ROI
        self.sensitivity = max(0.0, min(sensitivity, 100.0))
        self.enable_ocr = enable_ocr and _OCR_AVAILABLE
        self._previous_gray: Optional[np.ndarray] = None
        self._previous_non_red: Optional[np.ndarray] = None
        self._last_event_time: float = -_COOLDOWN_SECONDS

    def reset(self) -> None:
        self._previous_gray = None
        self._previous_non_red = None
        self._last_event_time = -_COOLDOWN_SECONDS

    def _extract_roi(self, frame_bgr: np.ndarray) -> np.ndarray:
        height, width = frame_bgr.shape[:2]
        x1, y1, x2, y2 = self.roi.to_pixels(width, height)
        return frame_bgr[y1:y2, x1:x2]

    @staticmethod
    def _non_red_mask(roi_bgr: np.ndarray) -> np.ndarray:
        """
        Маска пикселей, НЕ являющихся красно-доминантными (255 = не красный).

        Зачем: красная виньетка низкого HP может визуально заходить в верхний
        правый угол экрана, где также находится килфид (обе зоны — у краёв
        экрана). Если просто занулить красные пиксели перед вычислением
        разницы кадров, само появление/исчезновение виньетки создаёт
        искусственный "диф" (фон был серым ~30, стал нулевым) — то есть
        проблема не решается, а просто перемещается. Правильно — полностью
        ИСКЛЮЧИТЬ такие пиксели и из числителя, и из знаменателя доли
        изменения (см. analyze_frame), а не подменять их значением.
        """
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        red_mask = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        red_mask |= cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
        return cv2.bitwise_not(red_mask)

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        roi_bgr = self._extract_roi(frame_bgr)
        if roi_bgr.size == 0:
            return []

        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        non_red = self._non_red_mask(roi_bgr)

        if self._previous_gray is None or self._previous_gray.shape != gray.shape:
            self._previous_gray = gray
            self._previous_non_red = non_red
            return []

        diff = cv2.absdiff(gray, self._previous_gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        # Пиксель учитывается только если он НЕ был красным ни в этом, ни в
        # предыдущем кадре — иначе появление/исчезновение виньетки само по
        # себе создаёт ложный "диф", не имеющий отношения к килфиду.
        valid_mask = cv2.bitwise_and(non_red, self._previous_non_red)
        valid_area = int(np.count_nonzero(valid_mask))

        self._previous_gray = gray
        self._previous_non_red = non_red

        if valid_area == 0:
            return []  # весь ROI сейчас закрыт красным — судить о килфиде нельзя

        changed_and_valid = cv2.bitwise_and(thresh, valid_mask)
        change_ratio = float(np.count_nonzero(changed_and_valid)) / valid_area

        # sensitivity 0 -> порог 4% изменившихся пикселей; sensitivity 100 -> порог 0.8%
        threshold = 0.06 - (self.sensitivity / 100.0) * 0.04  # было 0.04-0.032 - реальный HUD "шевелится" (миникарта, счётчики) сильнее, чем синтетика

        if change_ratio < threshold:
            return []
        if timestamp - self._last_event_time < _COOLDOWN_SECONDS:
            return []

        self._last_event_time = timestamp
        recognized_text = self._try_ocr(roi_bgr) if self.enable_ocr else None
        label = "Новая строка килфида"
        if recognized_text:
            label += f': "{recognized_text}"'

        return [DetectionEvent(
            timestamp=timestamp,
            source="killfeed",
            confidence=round(min(change_ratio / max(threshold, 1e-6), 1.0), 2),
            label=label,
            metadata={"change_ratio": round(change_ratio, 4), "ocr_text": recognized_text},
        )]

    @staticmethod
    def _try_ocr(roi_bgr: np.ndarray) -> Optional[str]:
        """Best-effort OCR текста килфида. None при неудаче или отсутствии Tesseract —
        детекция самого события от этого не зависит, это только обогащение метаданных."""
        try:
            gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            scaled = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            _, binary = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(binary, lang="eng", config="--psm 6").strip()
            return text if text else None
        except Exception:
            return None
