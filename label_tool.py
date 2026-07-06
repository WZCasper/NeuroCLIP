"""
label_tool.py — инструмент разметки датасета для дообучения классификатора
взрыв / прицел / фон.

ИСПОЛЬЗОВАНИЕ:
    python label_tool.py путь/к/видео1.mp4 [путь/к/видео2.mp4 ...]

Что происходит:
1. Для каждого НОВОГО видео (уже обработанные пропускаются автоматически)
   извлекаются кадры-кандидаты через dataset_extract.py — часть из них
   похожа на взрыв, часть на прицел, часть — случайный "спокойный" фон.
2. Открывается окно разметки: кадры показываются по одному, вы решаете,
   что на самом деле на кадре — окончательное слово всегда за вами,
   предположение детектора в имени файла ни на что не влияет.
3. Файл перекладывается в dataset/explosion/, dataset/scope/,
   dataset/background/, либо в dataset/_deleted/, если это мусор или
   ложное срабатывание, непригодное даже как фон. Ничего не стирается
   физически необратимо — это позволяет корректно отменять решения
   (Undo); при желании освободить место папку dataset/_deleted можно
   почистить вручную в любой момент, когда она вам больше не нужна.

Можно закрыть окно в любой момент — уже размеченные кадры остаются
в соответствующих папках, а неразмеченные остатки дождутся вас в
dataset/_staging/ при следующем запуске.

Управление с клавиатуры: 1 — взрыв, 2 — прицел, 3 или Delete — удалить,
Z или Backspace — отменить последнее решение.
"""

import glob
import os
import sys
from typing import List, Optional

import customtkinter as ctk
from PIL import Image

from dataset_extract import STAGING_DIR, extract_candidates
from ui import theme

DATASET_DIR = "dataset"
CLASS_LABELS = {
    "explosion": ("💥 Взрыв", theme.DANGER),
    "scope": ("🎯 Прицел", theme.ACCENT_CYAN),
    "background": ("🚫 Фон (не взрыв/прицел)", theme.TEXT_MUTED),
}


class LabelToolApp(ctk.CTk):
    def __init__(self, video_paths: List[str]):
        super().__init__()
        ctk.set_appearance_mode("Dark")

        self.title("NeuroClip — Разметка датасета")
        self.geometry("1000x760")
        self.configure(fg_color=theme.BG_PRIMARY)

        self._run_extraction(video_paths)

        self._staging_files: List[str] = self._reload_staging_list()
        self._index = 0
        self._counts = {"explosion": 0, "scope": 0, "background": 0, "deleted": 0}
        self._history: List[dict] = []  # для отмены последнего действия
        self._current_ctk_image: Optional[ctk.CTkImage] = None

        self._build_ui()
        self.bind("<Key>", self._on_key)
        self._show_current()

    # ------------------------------------------------------------------
    def _run_extraction(self, video_paths: List[str]) -> None:
        for path in video_paths:
            if not os.path.exists(path):
                print(f"Файл не найден, пропускаю: {path}")
                continue
            print(f"Извлекаю кандидатов из: {path}")
            exp, scope, bg = extract_candidates(path)
            print(f"  найдено — взрыв: {exp}, прицел: {scope}, фон: {bg}")

    @staticmethod
    def _reload_staging_list() -> List[str]:
        return sorted(glob.glob(os.path.join(STAGING_DIR, "*.jpg")))

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._progress_label = ctk.CTkLabel(
            self, text="", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13),
        )
        self._progress_label.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))

        self._image_label = ctk.CTkLabel(self, text="", fg_color=theme.BG_SECONDARY, corner_radius=12)
        self._image_label.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self._image_label.bind("<Configure>", lambda _e: self._redraw_image())

        self._filename_label = ctk.CTkLabel(
            self, text="", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=11),
        )
        self._filename_label.grid(row=2, column=0, sticky="ew", padx=20)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=20, pady=16)
        for i in range(4):
            buttons.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(
            buttons, text="1 · 💥 Взрыв", command=lambda: self._classify("explosion"),
            fg_color=theme.DANGER, hover_color="#B32222", height=48,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        ).grid(row=0, column=0, padx=6, sticky="ew")

        ctk.CTkButton(
            buttons, text="2 · 🎯 Прицел", command=lambda: self._classify("scope"),
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE, text_color="#050505",
            height=48, font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        ).grid(row=0, column=1, padx=6, sticky="ew")

        ctk.CTkButton(
            buttons, text="3 · 🚫 Удалить", command=lambda: self._classify(None),
            fg_color="transparent", border_width=2, border_color=theme.TEXT_MUTED,
            text_color=theme.TEXT_MUTED, height=48,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        ).grid(row=0, column=2, padx=6, sticky="ew")

        ctk.CTkButton(
            buttons, text="Z · ⬅ Отменить", command=self._undo,
            fg_color="transparent", border_width=2, border_color=theme.ACCENT_PURPLE,
            text_color=theme.ACCENT_PURPLE, height=48,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        ).grid(row=0, column=3, padx=6, sticky="ew")

        self._stats_label = ctk.CTkLabel(
            self, text="", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
        )
        self._stats_label.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 16))

    # ------------------------------------------------------------------
    def _current_path(self) -> Optional[str]:
        if self._index >= len(self._staging_files):
            return None
        return self._staging_files[self._index]

    def _show_current(self) -> None:
        path = self._current_path()
        self._update_stats()

        if path is None:
            self._image_label.configure(image=None, text="Все кандидаты размечены 🎉")
            self._filename_label.configure(text="")
            self._progress_label.configure(text=f"Готово: {len(self._staging_files)} из {len(self._staging_files)}")
            return

        self._progress_label.configure(
            text=f"Кандидат {self._index + 1} из {len(self._staging_files)}"
        )
        suggested = os.path.basename(path).rsplit("_", 1)[-1].replace(".jpg", "")
        suggested_label = CLASS_LABELS.get(suggested, ("?", theme.TEXT_MUTED))[0]
        self._filename_label.configure(
            text=f"{os.path.basename(path)}   (предположение детектора: {suggested_label} — не финально)"
        )

        self._current_pil_image = Image.open(path)
        self._redraw_image()

    def _redraw_image(self) -> None:
        if self._current_path() is None or not hasattr(self, "_current_pil_image"):
            return
        max_w = max(self._image_label.winfo_width(), 1)
        max_h = max(self._image_label.winfo_height(), 1)
        ratio = min(max_w / self._current_pil_image.width, max_h / self._current_pil_image.height, 1.0)
        ratio = max(ratio, 0.05)
        new_size = (max(int(self._current_pil_image.width * ratio), 1),
                    max(int(self._current_pil_image.height * ratio), 1))
        resized = self._current_pil_image.resize(new_size, Image.LANCZOS)
        self._current_ctk_image = ctk.CTkImage(light_image=resized, dark_image=resized, size=resized.size)
        self._image_label.configure(image=self._current_ctk_image, text="")

    def _update_stats(self) -> None:
        self._stats_label.configure(
            text=(f"Размечено — взрыв: {self._counts['explosion']}, "
                  f"прицел: {self._counts['scope']}, фон: {self._counts['background']}, "
                  f"удалено: {self._counts['deleted']}")
        )

    # ------------------------------------------------------------------
    def _classify(self, label: Optional[str]) -> None:
        path = self._current_path()
        if path is None:
            return

        filename = os.path.basename(path)
        # "Удаление" реализовано как перемещение в корзину, а не os.remove() —
        # так отмена (Undo) работает ОДИНАКОВО для всех действий: физически
        # переместить файл обратно. Настоящее необратимое стирание файла,
        # который человек уже открывал и отсеял, не даёт возможности
        # передумать и создаёт риск случайной потери разметки.
        actual_label = label if label is not None else "_deleted"
        counts_key = label if label is not None else "deleted"

        dest_dir = os.path.join(DATASET_DIR, actual_label)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        os.replace(path, dest_path)

        self._counts[counts_key] += 1
        self._history.append({"action": "move", "from": path, "to": dest_path, "counts_key": counts_key})

        self._index += 1
        self._show_current()

    def _undo(self) -> None:
        if not self._history:
            return
        last = self._history.pop()
        os.replace(last["to"], last["from"])
        self._counts[last["counts_key"]] -= 1
        self._index -= 1
        self._show_current()

    def _on_key(self, event) -> None:
        key = event.keysym.lower()
        if key == "1":
            self._classify("explosion")
        elif key == "2":
            self._classify("scope")
        elif key in ("3", "delete"):
            self._classify(None)
        elif key in ("z", "backspace"):
            self._undo()


def main() -> None:
    video_paths = sys.argv[1:]
    if not video_paths:
        print("Использование: python label_tool.py путь/к/видео1.mp4 [видео2.mp4 ...]")
        print("(можно запустить и без аргументов, чтобы просто разметить то,")
        print(" что уже лежит в dataset/_staging/ с прошлого раза)")

    app = LabelToolApp(video_paths)
    app.mainloop()


if __name__ == "__main__":
    main()
