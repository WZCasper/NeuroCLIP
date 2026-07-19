"""
Базовая директория приложения — по-разному для обычного запуска и для
собранного PyInstaller-экзешника.

Обычный запуск (`python main.py`): папка, где лежит main.py.
Собранный .exe: папка, где лежит сам .exe, а НЕ временная папка
распаковки PyInstaller (sys._MEIPASS) — туда нельзя сохранять .env и
подобные пользовательские файлы, она пересоздаётся при каждом запуске.
"""

import os
import sys


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
