"""
Конфигурация NeuroClip.

Секретные данные (токен Telegram-бота, chat_id) загружаются из файла .env
и НЕ хранятся в коде. Файл .env создаётся пользователем на основе
.env.example и никогда не должен публиковаться в открытом репозитории
(см. .gitignore).
"""

import os

from dotenv import load_dotenv

from paths import BASE_DIR

load_dotenv(os.path.join(BASE_DIR, ".env"))

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Участники сквада, доступные для выбора в окне репорта об ошибке ИИ.
SQUAD_MEMBERS: list[str] = ["Arkhangel", "Kobrel", "Maestro", "Opornik", "Boom"]

APP_NAME = "NeuroClip"
APP_VERSION = "0.1.0-alpha"

# Путь к файлу модели MediaPipe FaceLandmarker (см. eye_contact_detector.py
# для инструкции по скачиванию — библиотека не скачивает его сама).
FACE_LANDMARKER_MODEL_PATH = os.path.join(BASE_DIR, "assets", "models", "face_landmarker.task")
