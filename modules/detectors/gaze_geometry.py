"""
Чистая геометрия оценки взгляда — без зависимости от MediaPipe.

Вынесена отдельно намеренно: эту математику можно проверить на
сфабрикованных координатах ландмарок с заранее известным результатом
(см. test_gaze_geometry.py), не имея под рукой реальной модели лица.
Реальный источник координат (MediaPipe FaceLandmarker) подключается в
eye_contact_detector.py.

ЧЕСТНО ПРО ИНДЕКСЫ ЛАНДМАРОК: в разных источниках по MediaPipe индексы 33/468
и 263/473 подписаны то как "левый глаз", то как "правый" (путаница из-за
разных конвенций — от лица или от зрителя). Кто из них прав — не критично
для этого алгоритма: оба глаза обрабатываются полностью симметрично и
усредняются, поэтому даже если подписи "левый/правый" в комментариях ниже
перепутаны местами, сам расчёт остаётся верным.

АЛГОРИТМ:
1. Для каждого глаза отдельно: считаем, где находится центр радужки между
   внешним и внутренним уголком глаза (горизонтальный gaze ratio) и между
   верхним и нижним веком (вертикальный gaze ratio). Значение ~0.5 в обоих
   случаях означает "радужка по центру глаза" — взгляд направлен прямо
   относительно оси ЭТОГО глаза.
2. Проверяем фронтальность лица: сравниваем расстояние от кончика носа до
   внешнего уголка каждого глаза. Если лицо развёрнуто в сторону, даже
   "центрированная" радужка не означает взгляд в камеру — сама голова
   повёрнута. Без этой проверки алгоритм давал бы ложные срабатывания при
   повороте головы с компенsирующим движением глаз.
3. "Взгляд в камеру" = центрированный gaze ratio (оба глаза) И фронтальное
   лицо одновременно.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

Landmarks = Dict[int, Tuple[float, float]]

# Индексы ландмарок MediaPipe FaceLandmarker (478-точечная модель).
NOSE_TIP = 1

EYE_1 = {"outer": 33, "inner": 133, "top": 159, "bottom": 145, "iris": 468}
EYE_2 = {"outer": 263, "inner": 362, "top": 386, "bottom": 374, "iris": 473}


@dataclass
class GazeState:
    horizontal_ratio: float   # 0.5 = центр; <0.5 или >0.5 = взгляд в сторону
    vertical_ratio: float     # 0.5 = центр; <0.5 или >0.5 = взгляд вверх/вниз
    frontality_ratio: float   # 1.0 = лицо строго анфас; сильное отклонение = поворот головы
    is_looking_at_camera: bool
    confidence: float


def _eye_ratios(landmarks: Landmarks, eye: dict) -> Tuple[float, float]:
    outer = landmarks[eye["outer"]]
    inner = landmarks[eye["inner"]]
    top = landmarks[eye["top"]]
    bottom = landmarks[eye["bottom"]]
    iris = landmarks[eye["iris"]]

    horizontal_span = outer[0] - inner[0]
    vertical_span = bottom[1] - top[1]

    h_ratio = (iris[0] - inner[0]) / horizontal_span if abs(horizontal_span) > 1e-6 else 0.5
    v_ratio = (iris[1] - top[1]) / vertical_span if abs(vertical_span) > 1e-6 else 0.5
    return h_ratio, v_ratio


def _frontality_ratio(landmarks: Landmarks) -> float:
    """1.0 = лицо строго анфас. Чем дальше от 1.0 (в обе стороны), тем сильнее поворот головы."""
    nose = landmarks[NOSE_TIP]
    dist_to_eye1 = abs(landmarks[EYE_1["outer"]][0] - nose[0])
    dist_to_eye2 = abs(landmarks[EYE_2["outer"]][0] - nose[0])

    smaller, larger = sorted([dist_to_eye1, dist_to_eye2])
    if larger < 1e-6:
        return 0.0
    return smaller / larger  # 1.0 при полной симметрии, -> 0 при сильном повороте


def compute_gaze_state(
    landmarks: Landmarks,
    horizontal_tolerance: float = 0.18,
    vertical_tolerance: float = 0.20,
    min_frontality: float = 0.75,
) -> GazeState:
    """
    Вычисляет состояние взгляда по словарю ландмарок {индекс: (x, y)}.
    Координаты ожидаются нормализованными (0.0-1.0), как их отдаёт MediaPipe.

    Допуски (tolerance) настраиваются через чувствительность пользователя
    в eye_contact_detector.py — здесь заданы разумные значения по умолчанию.
    """
    h1, v1 = _eye_ratios(landmarks, EYE_1)
    h2, v2 = _eye_ratios(landmarks, EYE_2)

    horizontal_ratio = (h1 + h2) / 2.0
    vertical_ratio = (v1 + v2) / 2.0
    frontality = _frontality_ratio(landmarks)

    horizontal_centered = abs(horizontal_ratio - 0.5) <= horizontal_tolerance
    vertical_centered = abs(vertical_ratio - 0.5) <= vertical_tolerance
    is_frontal = frontality >= min_frontality

    is_looking = horizontal_centered and vertical_centered and is_frontal

    # confidence: насколько уверенно выполнены условия, а не просто True/False на грани
    h_margin = 1.0 - min(abs(horizontal_ratio - 0.5) / max(horizontal_tolerance, 1e-6), 1.0)
    v_margin = 1.0 - min(abs(vertical_ratio - 0.5) / max(vertical_tolerance, 1e-6), 1.0)
    f_margin = min(frontality / max(min_frontality, 1e-6), 1.0)
    confidence = round((h_margin + v_margin + f_margin) / 3.0, 2) if is_looking else 0.0

    return GazeState(
        horizontal_ratio=round(horizontal_ratio, 3),
        vertical_ratio=round(vertical_ratio, 3),
        frontality_ratio=round(frontality, 3),
        is_looking_at_camera=is_looking,
        confidence=confidence,
    )
