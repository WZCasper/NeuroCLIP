# Файл модели для детектора зрительного контакта

Положите сюда файл `face_landmarker.task` — он не входит в поставку
библиотеки MediaPipe и его нужно скачать один раз вручную.

**Официальный источник:**
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

**Если недоступен (Google Storage иногда блокируется по регионам) —
неофициальное зеркало на GitHub** (стороннее, на ваш риск):
https://github.com/sanderdesnaijer/mediapipe-model-mirrors/releases/download/v1/face_landmarker.task

После скачивания путь должен быть: `assets/models/face_landmarker.task`

Без этого файла NeuroClip продолжит работать нормально — детектор
зрительного контакта просто пропускается при анализе (остальные детекторы
не затрагиваются), в статусе будет предупреждение об этом.
