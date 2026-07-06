"""
train_classifier.py — дообучение классификатора взрыв/прицел/фон на вашем
размеченном датасете (см. label_tool.py).

ИСПОЛЬЗОВАНИЕ:
    python train_classifier.py

Что происходит:
1. Проверяет, что в dataset/explosion/, dataset/scope/, dataset/background/
   достаточно примеров (минимум MIN_IMAGES_PER_CLASS на класс).
2. Делает train/val разбиение (85/15) в dataset_split/ — КОПИРУЕТ файлы,
   оригинальные папки в dataset/ не трогает, можно пересобрать split заново
   в любой момент, если добавите ещё размеченных кадров.
3. Дообучает YOLOv8-classification (предобученный на ImageNet, transfer
   learning — учится быстрее и качественнее, чем с нуля) на вашем датасете.
4. Выводит путь к готовой модели и готовый код для подключения в yolo_detector.py.

ЧЕСТНО ПРО ТЕСТИРОВАНИЕ: сама механика (структура папок, вызов train(),
формат результата) проверена на реальном API Ultralytics — но с локально
собранной, необученной архитектурой, а не настоящими предобученными весами:
скачать yolov8n-cls.pt не получилось и из моей среды (тот же заблокированный
домен, что и раньше). У вас с обычным интернетом загрузка должна пройти
штатно — это стандартное, документированное поведение библиотеки. На случай,
если у вас в моменте тоже не заладится сеть, ниже есть понятный fallback,
а не необъяснимый краш.
"""

import os
import random
import shutil
import sys

DATASET_DIR = "dataset"
SPLIT_DIR = "dataset_split"
CLASSES = ["explosion", "scope", "background"]
MIN_IMAGES_PER_CLASS = 30
VAL_FRACTION = 0.15
PRETRAINED_WEIGHTS = "yolov8n-cls.pt"
FALLBACK_ARCHITECTURE = "yolov8n-cls.yaml"  # без предобучения, если сеть недоступна


def _check_dataset() -> dict:
    counts = {}
    for cls in CLASSES:
        class_dir = os.path.join(DATASET_DIR, cls)
        if not os.path.isdir(class_dir):
            counts[cls] = 0
            continue
        counts[cls] = len([f for f in os.listdir(class_dir)
                            if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    return counts


def _prepare_split() -> None:
    if os.path.exists(SPLIT_DIR):
        shutil.rmtree(SPLIT_DIR)

    for cls in CLASSES:
        class_dir = os.path.join(DATASET_DIR, cls)
        images = [f for f in os.listdir(class_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        random.shuffle(images)

        val_count = max(1, int(len(images) * VAL_FRACTION))
        subsets = {"val": images[:val_count], "train": images[val_count:]}

        for subset_name, subset_images in subsets.items():
            dest_dir = os.path.join(SPLIT_DIR, subset_name, cls)
            os.makedirs(dest_dir, exist_ok=True)
            for filename in subset_images:
                shutil.copy2(os.path.join(class_dir, filename), os.path.join(dest_dir, filename))

        print(f"  {cls}: {len(subsets['train'])} train / {len(subsets['val'])} val")


def _load_model():
    """Пробует настоящие предобученные веса (transfer learning). Если сеть
    подвела — честно предупреждает и предлагает обучение с нуля вместо
    непонятного краша."""
    from ultralytics import YOLO
    try:
        return YOLO(PRETRAINED_WEIGHTS), True
    except Exception as exc:
        print(f"⚠️  Не удалось загрузить предобученные веса {PRETRAINED_WEIGHTS}: {exc}")
        print("    Проверьте интернет-соединение. Можно продолжить обучением")
        print("    С НУЛЯ (без transfer learning — потребуется намного больше")
        print("    примеров и эпох для приличного качества).")
        answer = input("    Продолжить с нуля? [y/N]: ").strip().lower()
        if answer != "y":
            sys.exit(1)
        return YOLO(FALLBACK_ARCHITECTURE), False


def main() -> None:
    print("Проверяю датасет...")
    counts = _check_dataset()
    for cls, count in counts.items():
        print(f"  {cls}: {count} изображений")

    missing = [cls for cls, count in counts.items() if count < MIN_IMAGES_PER_CLASS]
    if missing:
        print()
        print(f"Недостаточно примеров для классов: {', '.join(missing)} "
              f"(нужно минимум {MIN_IMAGES_PER_CLASS} на класс).")
        print("Доразметьте ещё через: python label_tool.py путь/к/видео.mp4")
        sys.exit(1)

    try:
        import ultralytics  # noqa: F401
    except ImportError:
        print("Пакет 'ultralytics' не установлен. Установите: pip install ultralytics")
        sys.exit(1)

    print()
    print("Готовлю train/val разбиение (85/15)...")
    _prepare_split()

    model, is_pretrained = _load_model()

    print()
    print(f"Начинаю {'дообучение' if is_pretrained else 'обучение с нуля'}...")
    print("Это может занять от нескольких минут до часа в зависимости от размера")
    print("датасета и наличия GPU. Прогресс выводится ниже.")
    print()

    results = model.train(
        data=os.path.abspath(SPLIT_DIR),
        epochs=50 if is_pretrained else 150,
        imgsz=224,
        patience=10,
        project="runs_neuroclip",
        name="explosion_scope_classifier",
    )

    best_weights = os.path.join(results.save_dir, "weights", "best.pt")
    print()
    print("=" * 60)
    print("Готово! Обученная модель:")
    print(f"  {best_weights}")
    print()
    print("Чтобы подключить в NeuroClip — в modules/analysis_pipeline.py:")
    print()
    print("  from modules.detectors.yolo_detector import YOLODetector")
    print("  YOLODetector(")
    print(f'      model_path=r"{os.path.abspath(best_weights)}",')
    print('      class_names_to_source={"explosion": "explosion", "scope": "explosion"},')
    print("  )")
    print("=" * 60)


if __name__ == "__main__":
    main()
