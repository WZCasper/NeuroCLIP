"""
Брендинг-неймплейт создателя NeuroClip.

Рендерит "CASPER" (красный, 64px) и "Denis" (жёлтый, 56px, визуально меньше и
второстепеннее) с эффектом неонового свечения. Свечение — настоящий Gaussian
Blur через Pillow (ImageFilter.GaussianBlur), а не имитация тенью/обводкой.

Текст рендерится в PIL.Image и отображается как CTkImage, поэтому шрифт
(assets/fonts/RussoOne-Regular.ttf) выглядит одинаково на любой ОС —
в отличие от обычных Tk-виджетов, здесь не требуется, чтобы шрифт был
установлен в системе пользователя.
"""

import os

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ui import theme

_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "fonts", theme.BRAND_FONT_FILENAME,
)

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _load_font(size: int) -> ImageFont.ImageFont:
    """Загружает и кеширует брендовый шрифт. При отсутствии файла — безопасный fallback."""
    if size in _font_cache:
        return _font_cache[size]
    try:
        font = ImageFont.truetype(_FONT_PATH, size)
    except (OSError, IOError):
        # Файл шрифта не найден — приложение не падает, использует системный шрифт PIL.
        font = ImageFont.load_default(size=size)
    _font_cache[size] = font
    return font


def render_glow_text(text: str, size: int, color: str, glow_radius: int = 12,
                      glow_boost: int = 2, padding: int = 36) -> Image.Image:
    """
    Рендерит строку текста с неоновым свечением.

    Технически — два прохода композитинга:
      1. Слой свечения: текст того же цвета, размытый настоящим Gaussian Blur,
         продублированный glow_boost раз для визуальной интенсивности.
      2. Слой чёткого текста поверх размытого свечения.

    Возвращает RGBA PIL.Image с прозрачным фоном, готовое к показу в CTkImage.
    """
    font = _load_font(size)

    measuring_surface = Image.new("RGBA", (10, 10))
    bbox = ImageDraw.Draw(measuring_surface).textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    canvas_w = text_w + padding * 2
    canvas_h = text_h + padding * 2
    origin = (padding - bbox[0], padding - bbox[1])

    glow_mask = Image.new("L", (canvas_w, canvas_h), 0)
    ImageDraw.Draw(glow_mask).text(origin, text, font=font, fill=255)
    glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(glow_radius))

    # Размываем ТОЛЬКО альфа-маску (одноканальную), а не RGBA целиком: если
    # размыть цвет вместе с альфой, прозрачные (RGB=0,0,0, A=0) пиксели по
    # краям "тянут" итоговый цвет к чёрному даже там, где новая альфа мала —
    # на тёмном фоне это незаметно, но на светлом видно как серый ореол
    # вокруг текста. Раздельное размытие маски полностью исключает эффект.
    glow_layer = Image.new("RGBA", (canvas_w, canvas_h), color)
    glow_layer.putalpha(glow_mask)

    result = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    for _ in range(max(glow_boost, 1)):
        result = Image.alpha_composite(result, glow_layer)

    sharp_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ImageDraw.Draw(sharp_layer).text(origin, text, font=font, fill=color)
    result = Image.alpha_composite(result, sharp_layer)

    return result


class Nameplate(ctk.CTkFrame):
    """
    Неймплейт создателя: CASPER (главный, красный, 64px) над Denis
    (жёлтый, 56px). Размер шрифта прямо кодирует визуальную иерархию —
    CASPER крупнее и, соответственно, "главнее".
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        casper_image = render_glow_text("CASPER", size=64, color=theme.CASPER_RED, glow_radius=14)
        denis_image = render_glow_text("Denis", size=56, color=theme.DENIS_YELLOW, glow_radius=10)

        # Ссылки на CTkImage хранятся на self, иначе Python соберёт их как мусор
        # и изображение исчезнет с экрана после первой отрисовки.
        self._casper_image = ctk.CTkImage(light_image=casper_image, dark_image=casper_image,
                                           size=casper_image.size)
        self._denis_image = ctk.CTkImage(light_image=denis_image, dark_image=denis_image,
                                          size=denis_image.size)

        casper_label = ctk.CTkLabel(self, image=self._casper_image, text="", fg_color="transparent")
        casper_label.pack(pady=(0, 0))

        denis_label = ctk.CTkLabel(self, image=self._denis_image, text="", fg_color="transparent")
        denis_label.pack(pady=(2, 0))
