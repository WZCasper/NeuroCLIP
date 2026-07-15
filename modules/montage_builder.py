"""
МОДУЛЬ 4, часть 1: Склейка найденных моментов в готовый монтаж через MoviePy.

Как работает:
1. Каждое DetectionEvent превращается в отрезок видео вокруг таймкода —
   с разным контекстным окном "до/после" в зависимости от типа события
   (например, для килфида важнее показать подготовку к килу, чем то, что
   происходит после, а для зрительного контакта — наоборот, реакция важнее
   того, что было до).
2. Отрезки, расположенные близко друг к другу, СКЛЕИВАЮТСЯ в один
   непрерывный отрезок вместо жёсткой нарезки впритык — иначе монтаж
   получается рваным на местах, где события идут одно за другим.
3. Итоговые отрезки вырезаются и склеиваются через moviepy.

ПРОВЕРЕНО ЭМПИРИЧЕСКИ (не по памяти): установленная версия moviepy — 2.x,
где API заметно отличается от 1.x (например, .subclip() переименован в
.subclipped()). Использую подтверждённые вызовами сигнатуры.
"""

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from proglog import ProgressBarLogger

from modules.detectors.base import DetectionEvent

# Контекстное окно (секунд ДО, секунд ПОСЛЕ) вокруг каждого типа события —
# у разных событий разная "драматургия": что важнее показать.
_EVENT_WINDOWS = {
    "low_hp": (2.0, 4.0),        # напряжение до + видно, выжил ли после
    "killfeed": (3.0, 1.5),       # подготовка к килу важнее последствий
    "explosion": (2.0, 2.0),
    "eye_contact": (1.5, 2.5),     # реакция важнее того, что было до неё
    "audio_peak": (2.0, 2.0),
    "laughter": (3.0, 2.0),        # что рассмешило важнее самого смеха
}
_DEFAULT_WINDOW = (2.0, 2.0)
_MERGE_GAP_SECONDS = 1.0  # отрезки ближе друг к другу — склеиваются в один


class MontageError(Exception):
    """Ошибка при построении монтажа (нет событий, сбой рендера и т.п.)."""


class _RenderProgressLogger(ProgressBarLogger):
    """Перехватывает прогресс рендера MoviePy и пересылает как долю 0.0-1.0."""

    def __init__(self, on_progress: Callable[[float], None]):
        super().__init__()
        self._on_progress = on_progress
        self._totals = {}

    def bars_callback(self, bar, attr, value, old_value=None):
        if attr == "total":
            self._totals[bar] = value
        elif attr == "index" and bar == "frame_index":
            total = self._totals.get("frame_index")
            if total:
                self._on_progress(min(value / total, 1.0))


@dataclass
class ClipSegment:
    start: float
    end: float
    source_events: List[DetectionEvent] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


def events_to_segments(events: List[DetectionEvent], video_duration: float) -> List[ClipSegment]:
    """Превращает список событий в непересекающиеся отрезки видео для склейки."""
    if not events:
        return []

    raw: List[tuple] = []
    for event in events:
        before, after = _EVENT_WINDOWS.get(event.source, _DEFAULT_WINDOW)
        start = max(0.0, event.timestamp - before)
        end = min(video_duration, event.timestamp + after)
        if end > start:
            raw.append((start, end, event))

    raw.sort(key=lambda item: item[0])

    merged: List[ClipSegment] = []
    for start, end, event in raw:
        if merged and start - merged[-1].end <= _MERGE_GAP_SECONDS:
            merged[-1].end = max(merged[-1].end, end)
            merged[-1].source_events.append(event)
        else:
            merged.append(ClipSegment(start=start, end=end, source_events=[event]))

    return merged


def build_montage(
    video_path: str,
    segments: List[ClipSegment],
    output_path: str,
    on_progress: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Вырезает и склеивает сегменты в один файл через MoviePy.
    Бросает MontageError при отсутствии сегментов или сбое рендера.
    """
    if not segments:
        raise MontageError("Нет сегментов для монтажа — сначала запустите анализ и найдите события.")

    from moviepy import VideoFileClip, concatenate_videoclips

    source = None
    subclips = []
    final = None
    try:
        source = VideoFileClip(video_path)
        subclips = [source.subclipped(seg.start, seg.end) for seg in segments]
        final = concatenate_videoclips(subclips, method="chain")

        logger = _RenderProgressLogger(on_progress) if on_progress else None
        final.write_videofile(
            output_path, codec="libx264", audio_codec="aac",
            logger=logger, temp_audiofile_path=os.path.dirname(output_path) or ".",
        )
    except Exception as exc:
        raise MontageError(f"Не удалось собрать монтаж: {exc}") from exc
    finally:
        if final is not None:
            final.close()
        for clip in subclips:
            clip.close()
        if source is not None:
            source.close()
