"""
Детектор смеха через транскрипцию Whisper.

═══════════════════════════════════════════════════════════════════════
ЧЕСТНО ПРО НАДЁЖНОСТЬ ЭТОГО ДЕТЕКТОРА (прочитайте перед использованием)
═══════════════════════════════════════════════════════════════════════
Whisper — модель распознавания РЕЧИ, а не выделенный классификатор смеха.
То, что она иногда помечает несловесные звуки как "[laughter]"/"(laughs)" —
не официальная документированная функция, а побочный эффект того, что
часть её обучающих данных (субтитры с описанием звука) содержала такие
пометки. Это происходит НЕПОСЛЕДОВАТЕЛЬНО: более крупные модели (medium,
large) делают это заметно чаще, чем маленькие (tiny, base); реальный смех
без таких пометок Whisper просто расшифрует как несуществующие слова или
пропустит. Это honest best-effort бонус-сигнал, а НЕ надёжный детектор
смеха — не рассчитывайте на высокий recall.

Дополнительно ищутся русские и английские текстовые маркеры смеха
("ха-ха", "хах", "haha" и т.п.) на случай, если кто-то в войсчате
буквально произносит смех вслух как имитацию слова, а не смеётся —
Whisper может расшифровать это как реальный текст.

═══════════════════════════════════════════════════════════════════════
ЧЕСТНО ПРО ТЕСТИРОВАНИЕ
═══════════════════════════════════════════════════════════════════════
Скачивание любой модели Whisper заблокировано и в моей среде (тот же
паттерн, что с YOLO и MediaPipe — уже четвёртый раз в этом проекте).
Поэтому здесь протестирована ТОЛЬКО логика поиска маркеров в тексте
(_contains_laughter_marker) — на сфабрикованных строках, не через реальную
транскрипцию. Сам вызов model.transcribe() и структура его результата
(segments с start/end/text) проверены по исходному коду библиотеки, но не
прогонялись на реальном аудио. Первый настоящий прогон — на вашей машине.
"""

import re
from typing import List, Optional

from modules.detectors.base import DetectionEvent

_COOLDOWN_SECONDS = 3.0

# Явные несловесные пометки, которые Whisper иногда генерирует
_BRACKET_MARKERS = [
    r"\[laughter\]", r"\(laughs?\)", r"\(laughing\)", r"\[смех\]", r"\(смеётся\)", r"\(смеется\)",
]

# Онлайн-имитация смеха текстом (рус./англ.) - "ха"/"ha" повторённое 2+ раза
# подряд, с необязательной гласной в начале ("ахаха", "ahaha"). Обычные слова
# с одиночным "ха"/"ha" внутри (например "характер", "chaos") не совпадают —
# нужен именно ПОВТОР слога.
_TEXT_MARKERS_PATTERN = re.compile(r"а?(?:ха){2,}|a?(?:ha){2,}", re.IGNORECASE | re.UNICODE)

_BRACKET_PATTERN = re.compile("|".join(_BRACKET_MARKERS), re.IGNORECASE)


def _contains_laughter_marker(text: str) -> bool:
    """Чистая функция поиска маркеров смеха в тексте — тестируется отдельно
    от реальной транскрипции (см. test_laughter_markers.py)."""
    if not text:
        return False
    return bool(_BRACKET_PATTERN.search(text) or _TEXT_MARKERS_PATTERN.search(text))


class LaughterDetector:
    def __init__(self, model_size: str = "base", language: Optional[str] = None):
        """
        model_size: tiny/base/small/medium/large — больше = точнее и МЕДЛЕННЕЕ.
            Для CPU без GPU "base" — разумный компромисс.
        language: код языка ("ru", "en", ...) если известен заранее — ускоряет
            и немного повышает точность. None = автоопределение (медленнее).
        """
        try:
            import whisper
        except ImportError as exc:
            raise ImportError("Пакет 'openai-whisper' не установлен. Установите: pip install openai-whisper") from exc

        self._whisper = whisper
        self.model_size = model_size
        self.language = language
        self._model = None  # ленивая загрузка - модель тяжёлая, грузим один раз при первом использовании

    def _ensure_model_loaded(self):
        if self._model is None:
            self._model = self._whisper.load_model(self.model_size)
        return self._model

    def analyze_audio(self, wav_path: str) -> List[DetectionEvent]:
        model = self._ensure_model_loaded()
        result = model.transcribe(wav_path, language=self.language, verbose=False)

        events: List[DetectionEvent] = []
        last_event_time = -_COOLDOWN_SECONDS

        for segment in result.get("segments", []):
            text = segment.get("text", "")
            if not _contains_laughter_marker(text):
                continue

            start_time = float(segment.get("start", 0.0))
            if start_time - last_event_time < _COOLDOWN_SECONDS:
                continue

            last_event_time = start_time
            events.append(DetectionEvent(
                timestamp=start_time,
                source="laughter",
                confidence=0.5,  # честно средняя - см. примечание о ненадёжности выше
                label=f'Смех (реплика: "{text.strip()}")',
                metadata={"segment_text": text.strip(), "end": float(segment.get("end", start_time))},
            ))

        return events
