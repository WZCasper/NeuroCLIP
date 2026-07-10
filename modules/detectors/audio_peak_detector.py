"""
Детектор резких громких звуковых пиков (выстрелы и похожие звуки).

АЛГОРИТМ (реальный, не имитация), два условия одновременно:
1. Онсет (librosa.onset.onset_detect) — момент резкого начала звукового
   события. Ловит МОМЕНТ, но сам по себе слишком чувствителен: онсеты
   бывают и у тихих звуков, и у границ сигнала (проверено эмпирически).
2. Амплитуда в этот момент (RMS) должна значимо превышать МЕДИАННЫЙ фон
   всей записи — медиана устойчива к редким громким пикам (в отличие от
   среднего), поэтому громкая перестрелка сама по себе не завышает "фон"
   и не маскирует последующие события.

ЧЕСТНО ПРО ТОЧНОСТЬ: это детектор "резкий громкий звук", а не семантический
классификатор "это именно выстрел, а не крик/взрыв/удар". Отличить их
надёжно без модели, обученной на размеченном звуке, невозможно — но для
хайлайт-детектора это не проблема: резкий громкий звук тем или иным образом
почти всегда означает "что-то произошло".
"""

from typing import List

import librosa
import numpy as np

from modules.detectors.base import DetectionEvent

_COOLDOWN_SECONDS = 2.0
_MIN_ABSOLUTE_RMS = 0.02  # игнорировать "пики" в записи, которая в целом почти беззвучна


class AudioPeakDetector:
    def __init__(self, sensitivity: float = 50.0):
        self.sensitivity = max(0.0, min(sensitivity, 100.0))

    def analyze_audio(self, wav_path: str) -> List[DetectionEvent]:
        y, sr = librosa.load(wav_path, sr=22050, mono=True)
        if len(y) == 0:
            return []

        rms = librosa.feature.rms(y=y)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
        background_rms = float(np.median(rms))

        onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time")

        # sensitivity 0 -> нужен пик минимум в 8x громче фона; sensitivity 100 -> в 2.5x
        threshold_ratio = 8.0 - (self.sensitivity / 100.0) * 5.5

        events: List[DetectionEvent] = []
        last_event_time = -_COOLDOWN_SECONDS

        for onset_time in onset_times:
            idx = int(np.argmin(np.abs(rms_times - onset_time)))
            peak_rms = float(rms[idx])

            if peak_rms < _MIN_ABSOLUTE_RMS:
                continue
            ratio = peak_rms / max(background_rms, 1e-6)
            if ratio < threshold_ratio:
                continue
            if onset_time - last_event_time < _COOLDOWN_SECONDS:
                continue

            last_event_time = float(onset_time)
            confidence = round(min(ratio / threshold_ratio / 2.0, 1.0), 2)
            events.append(DetectionEvent(
                timestamp=float(onset_time),
                source="audio_peak",
                confidence=confidence,
                label="Резкий громкий звук",
                metadata={"peak_rms": round(peak_rms, 4), "background_rms": round(background_rms, 4),
                          "ratio": round(ratio, 1)},
            ))

        return events
