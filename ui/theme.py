"""
Цветовая палитра и типографика NeuroClip.

Поддержка светлой/тёмной темы: цвета ниже — КОРТЕЖИ (светлый, тёмный).
CustomTkinter понимает такой формат "из коробки" и сам перекрашивает уже
созданные виджеты при ctk.set_appearance_mode(...) — проверено на
внутреннем AppearanceModeTracker библиотеки, отдельный код перерисовки
для каждого виджета не нужен.
"""

import customtkinter as ctk

_DARK = {
    "BG_PRIMARY": "#0A0A14", "BG_SECONDARY": "#12121F",
    "ACCENT_CYAN": "#00E5FF", "ACCENT_MAGENTA": "#FF2FC1", "ACCENT_PURPLE": "#7B2FFF",
    "TEXT_PRIMARY": "#E7E9F5", "TEXT_MUTED": "#8B8FA8",
    "DANGER": "#FF3B3B", "SUCCESS": "#2FFFA0",
}

# Тот же неоновый киберпанк-характер, но на светлом фоне; акценты чуть
# притемнены относительно тёмной темы для читаемости контраста.
_LIGHT = {
    "BG_PRIMARY": "#F2F3F9", "BG_SECONDARY": "#E4E6F0",
    "ACCENT_CYAN": "#0091A8", "ACCENT_MAGENTA": "#C41CA0", "ACCENT_PURPLE": "#5A21C4",
    "TEXT_PRIMARY": "#15151F", "TEXT_MUTED": "#5B5F73",
    "DANGER": "#D42E2E", "SUCCESS": "#1D9E64",
}

BG_PRIMARY = (_LIGHT["BG_PRIMARY"], _DARK["BG_PRIMARY"])
BG_SECONDARY = (_LIGHT["BG_SECONDARY"], _DARK["BG_SECONDARY"])
ACCENT_CYAN = (_LIGHT["ACCENT_CYAN"], _DARK["ACCENT_CYAN"])
ACCENT_MAGENTA = (_LIGHT["ACCENT_MAGENTA"], _DARK["ACCENT_MAGENTA"])
ACCENT_PURPLE = (_LIGHT["ACCENT_PURPLE"], _DARK["ACCENT_PURPLE"])
TEXT_PRIMARY = (_LIGHT["TEXT_PRIMARY"], _DARK["TEXT_PRIMARY"])
TEXT_MUTED = (_LIGHT["TEXT_MUTED"], _DARK["TEXT_MUTED"])
DANGER = (_LIGHT["DANGER"], _DARK["DANGER"])
SUCCESS = (_LIGHT["SUCCESS"], _DARK["SUCCESS"])

# Фирменные цвета CASPER/Denis — НЕ адаптивные, рендерятся на прозрачном
# фоне (ui/nameplate.py), тема окна на них не влияет и не должна.
CASPER_RED = "#FF2A2A"
DENIS_YELLOW = "#FFD500"

FONT_FAMILY_UI = "Segoe UI"
BRAND_FONT_FILENAME = "RussoOne-Regular.ttf"


def hex_to_rgb(hex_color: str) -> tuple:
    """Конвертирует '#RRGGBB' в (R, G, B) — для Pillow, который не понимает
    ни hex-строки CTk, ни тем более кортежи светлый/тёмный."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def resolve(color) -> str:
    """Конкретное hex-значение под ТЕКУЩУЮ активную тему — нужно там, где
    работаем не с виджетом CTk (он сам понимает кортежи), а с Pillow при
    сборке финального превью для экспорта."""
    if isinstance(color, tuple):
        return color[0] if ctk.get_appearance_mode() == "Light" else color[1]
    return color
