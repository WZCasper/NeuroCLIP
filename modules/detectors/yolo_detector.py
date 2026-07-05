"""
Универсальная обёртка над YOLOv8 (Ultralytics) для детекции объектов по кадру.

ЧЕСТНО ПРО ОГРАНИЧЕНИЕ (важно прочитать перед использованием):
Предобученные веса YOLOv8 (yolov8n.pt и подобные) обучены на датасете COCO —
80 бытовых классов (человек, машина, собака, ...). Там НЕТ классов "взрыв"
или "прицел снайперской винтовки". Получить такую детекцию "из коробки"
невозможно — нужна модель, дообученная на размеченных кадрах Warzone
(сотни-тысячи вручную размеченных примеров), которых у меня нет и которые
я не могу создать в рамках этой задачи.

Поэтому реальная детекция взрывов и прицела в этом шаге сделана классическим
CV (explosion_detector.py, scope_detector.py) — они работают без всякой
модели уже сейчас. Эта обёртка — готовый, протестированный интерфейс к
YOLO НА БУДУЩЕЕ: если вы найдёте подходящую модель (например, на Roboflow
Universe — там встречаются публичные датасеты по FPS-играм) или обучите
свою через `model.train(data=...)`, её можно подключить сюда без переделки
остального пайплайна.

Что реально проверено: вызов model.predict(), структура result.boxes,
result.names и извлечение box.cls/box.conf/box.xyxy — протестировано на
настоящем API Ultralytics (см. отчёт в чате). Не удалось протестировать
именно с официальными весами yolov8n.pt: их скачивание идёт через домен
release-assets.githubusercontent.com, недоступный из моего окружения
(проверил напрямую — 403). На вашей машине с обычным интернетом это
ограничение не действует.
"""

from typing import Dict, List

import numpy as np

from modules.detectors.base import DetectionEvent

try:
    from ultralytics import YOLO
    _ULTRALYTICS_AVAILABLE = True
except ImportError:
    _ULTRALYTICS_AVAILABLE = False


class YOLODetector:
    """Обёртка над Ultralytics YOLO: инференс по кадру -> список DetectionEvent."""

    def __init__(self, model_path: str, class_names_to_source: Dict[str, str],
                 confidence: float = 0.4):
        """
        model_path: путь к файлу .pt — например, ваша дообученная модель,
            либо "yolov8n.pt" (тогда Ultralytics скачает официальные веса
            автоматически при первом запуске, если это позволяет сеть).
        class_names_to_source: какие классы модели считать интересными и
            как называть их в событиях, например:
            {"explosion": "explosion", "scope_overlay": "explosion"}
        confidence: порог уверенности YOLO, 0.0-1.0.
        """
        if not _ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "Пакет 'ultralytics' не установлен. Установите: pip install ultralytics"
            )
        self._model = YOLO(model_path)
        self._class_map = class_names_to_source
        self._confidence = confidence

    def analyze_frame(self, frame_bgr: np.ndarray, timestamp: float) -> List[DetectionEvent]:
        results = self._model.predict(frame_bgr, conf=self._confidence, verbose=False)
        events: List[DetectionEvent] = []
        if not results:
            return events

        result = results[0]
        names = result.names

        for box in result.boxes:
            class_id = int(box.cls[0])
            class_name = names.get(class_id, str(class_id))
            if class_name not in self._class_map:
                continue

            confidence = float(box.conf[0])
            bbox = [round(v, 1) for v in box.xyxy[0].tolist()]

            events.append(DetectionEvent(
                timestamp=timestamp,
                source=self._class_map[class_name],
                confidence=round(confidence, 2),
                label=f"YOLO: {class_name}",
                metadata={"bbox": bbox},
            ))

        return events
