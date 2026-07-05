"""
Утилита калибровки регионов интереса (ROI).

Координаты killfeed и толщина виньетки HP в modules/detectors/*.py — это
разумная ОТПРАВНАЯ ТОЧКА для полноэкранной записи 16:9 со стандартным
HUD-масштабом, а НЕ гарантированно точные значения: реальное положение
зависит от разрешения записи, соотношения сторон и настройки HUD Scale
в игре, которые у каждого свои и точно неизвестны мне заранее.

Этот скрипт берёт кадр из вашего РЕАЛЬНОГО видео и рисует поверх него
зоны, которые сейчас использует детектор — так вы можете сразу увидеть,
накладывается ли жёлтая рамка на настоящий килфид, и поправить координаты
в killfeed_detector.py, если нет.

Использование:
    python calibrate_roi.py путь/к/видео.mp4 [секунда]

Пример:
    python calibrate_roi.py C:\\Clips\\warzone_match.mp4 45
"""

import sys

import cv2

from modules.detectors.killfeed_detector import DEFAULT_KILLFEED_ROI
from modules.detectors.hp_detector import LowHPDetector


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python calibrate_roi.py путь/к/видео.mp4 [секунда]")
        sys.exit(1)

    video_path = sys.argv[1]
    at_second = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        print(f"Не удалось открыть видео: {video_path}")
        sys.exit(1)

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(at_second * fps))
    ok, frame = capture.read()
    capture.release()

    if not ok:
        print("Не удалось прочитать кадр на указанной секунде (видео короче? другая секунда?).")
        sys.exit(1)

    height, width = frame.shape[:2]

    # --- Килфид ---
    x1, y1, x2, y2 = DEFAULT_KILLFEED_ROI.to_pixels(width, height)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 229, 255), 2)
    cv2.putText(frame, "KILLFEED ROI", (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 229, 255), 2)

    # --- Виньетка HP (кольцо между внешней и внутренней рамкой) ---
    thickness = int(min(height, width) * LowHPDetector().vignette_thickness_ratio)
    cv2.rectangle(frame, (0, 0), (width - 1, height - 1), (0, 0, 255), 2)
    cv2.rectangle(frame, (thickness, thickness), (width - thickness, height - thickness),
                  (0, 0, 255), 2)
    cv2.putText(frame, "HP VIGNETTE ZONE (между рамками)", (thickness + 8, thickness + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    output_path = "roi_calibration_preview.png"
    cv2.imwrite(output_path, frame)

    print(f"Сохранено: {output_path} (кадр на {at_second} сек, размер {width}x{height})")
    print()
    print("Проверьте:")
    print("  1. Жёлтая рамка (KILLFEED ROI) должна накрывать зону, где появляются")
    print("     строки убийств в правом верхнем углу.")
    print("  2. Красное кольцо (HP VIGNETTE ZONE) — зона по краям экрана, где должна")
    print("     появляться красная вспышка при низком HP.")
    print()
    print("Если рамки не совпадают с нужными элементами — поправьте координаты:")
    print("  • killfeed: DEFAULT_KILLFEED_ROI в modules/detectors/killfeed_detector.py")
    print("    (x1, y1, x2, y2 — доли от ширины/высоты кадра, от 0.0 до 1.0)")
    print("  • виньетка: vignette_thickness_ratio при создании LowHPDetector")


if __name__ == "__main__":
    main()
