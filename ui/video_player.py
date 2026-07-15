"""
Компонент предпросмотра видео.

Покадровое чтение через OpenCV (cv2.VideoCapture) напрямую в виджет
CustomTkinter — без стороннего окна cv2.imshow. Файл читается потоково
(кадр за кадром), а не загружается в память целиком, поэтому большие
видеофайлы не создают проблем с ОЗУ.

Примечание: предпросмотр немой (без звука). Синхронизированное
воспроизведение аудио — отдельная задача (потребует microphone-совместимый
плеер вроде python-vlc); дайте знать, если это нужно на следующих этапах.
"""

from typing import Optional

import cv2
import customtkinter as ctk
from PIL import Image

from ui import theme


class VideoPlayer(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_SECONDARY, corner_radius=16, **kwargs)

        self._capture: Optional[cv2.VideoCapture] = None
        self._fps: float = 30.0
        self._frame_count: int = 0
        self._current_frame_index: int = 0
        self._is_playing: bool = False
        self._playback_job: Optional[str] = None
        self._current_pil_frame: Optional[Image.Image] = None
        self._seeking: bool = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._display_label = ctk.CTkLabel(
            self, text="Видео не загружено", text_color=theme.TEXT_MUTED,
            fg_color="transparent", font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=16),
        )
        self._display_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self._display_label.bind("<Configure>", self._on_display_resize)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        controls.grid_columnconfigure(1, weight=1)

        self._play_button = ctk.CTkButton(
            controls, text="▶", width=44, command=self.toggle_play,
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE,
            text_color="#050505", font=ctk.CTkFont(size=16, weight="bold"), state="disabled",
        )
        self._play_button.grid(row=0, column=0, padx=(0, 10))

        self._seek_slider = ctk.CTkSlider(
            controls, from_=0, to=1, number_of_steps=1000,
            command=self._on_seek_drag, progress_color=theme.ACCENT_CYAN,
            button_color=theme.ACCENT_MAGENTA, button_hover_color=theme.ACCENT_PURPLE,
            state="disabled",
        )
        self._seek_slider.set(0)
        self._seek_slider.grid(row=0, column=1, sticky="ew", padx=10)
        self._seek_slider.bind("<ButtonPress-1>", self._on_seek_start)
        self._seek_slider.bind("<ButtonRelease-1>", self._on_seek_end)

        self._time_label = ctk.CTkLabel(
            controls, text="00:00 / 00:00", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13),
        )
        self._time_label.grid(row=0, column=2, padx=(10, 0))

    # ------------------------------------------------------------------
    # Загрузка видео
    # ------------------------------------------------------------------
    def load_video(self, filepath: str) -> bool:
        """Открывает видеофайл через OpenCV и показывает первый кадр. Возвращает успех."""
        self.stop()

        capture = cv2.VideoCapture(filepath)
        if not capture.isOpened():
            self._display_label.configure(
                image="", text=f"Не удалось открыть файл:\n{filepath}", text_color=theme.DANGER,
            )
            capture.release()
            self._capture = None
            return False

        self._capture = capture
        self._fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
        self._current_frame_index = 0

        self._play_button.configure(state="normal")
        self._seek_slider.configure(state="normal", to=max(self._frame_count - 1, 1))

        self._render_frame_at(0)
        return True

    # ------------------------------------------------------------------
    # Воспроизведение
    # ------------------------------------------------------------------
    def toggle_play(self) -> None:
        if self._capture is None:
            return
        self.pause() if self._is_playing else self.play()

    def play(self) -> None:
        if self._capture is None or self._is_playing:
            return
        self._is_playing = True
        self._play_button.configure(text="⏸")
        self._schedule_next_frame()

    def pause(self) -> None:
        self._is_playing = False
        self._play_button.configure(text="▶")
        if self._playback_job is not None:
            self.after_cancel(self._playback_job)
            self._playback_job = None

    def stop(self) -> None:
        """Останавливает воспроизведение и освобождает файловый ресурс видео."""
        self.pause()
        if self._capture is not None:
            self._capture.release()
        self._capture = None

    def _schedule_next_frame(self) -> None:
        if not self._is_playing or self._capture is None:
            return
        self._advance_frame()
        delay_ms = max(int(1000 / self._fps), 1)
        self._playback_job = self.after(delay_ms, self._schedule_next_frame)

    def _advance_frame(self) -> None:
        if self._capture is None:
            return
        ok, frame_bgr = self._capture.read()
        if not ok:
            # Достигнут конец видео — останавливаемся и перематываем на начало.
            self.pause()
            self._current_frame_index = 0
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._update_seek_ui()
            return
        self._current_frame_index += 1
        self._show_frame(frame_bgr)

    def _render_frame_at(self, frame_index: int) -> None:
        """Перематывает на конкретный кадр и отображает его (используется слайдером seek)."""
        if self._capture is None:
            return
        frame_index = max(0, min(frame_index, self._frame_count - 1))
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame_bgr = self._capture.read()
        if not ok:
            return
        self._current_frame_index = frame_index
        self._show_frame(frame_bgr)

    def _show_frame(self, frame_bgr) -> None:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self._current_pil_frame = Image.fromarray(frame_rgb)
        self._redraw_current_frame()
        self._update_seek_ui()

    def _redraw_current_frame(self) -> None:
        """Перерисовывает текущий кадр под актуальный размер виджета (учитывает resize окна)."""
        if self._current_pil_frame is None:
            return
        target_w = max(self._display_label.winfo_width(), 1)
        target_h = max(self._display_label.winfo_height(), 1)
        display_image = self._fit_image(self._current_pil_frame, target_w, target_h)

        ctk_image = ctk.CTkImage(light_image=display_image, dark_image=display_image,
                                  size=display_image.size)
        self._display_label.configure(image=ctk_image, text="")
        self._display_label.image = ctk_image  # защита от сборки мусора

    @staticmethod
    def _fit_image(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
        ratio = min(max_w / image.width, max_h / image.height)
        ratio = max(ratio, 0.01)
        new_size = (max(int(image.width * ratio), 1), max(int(image.height * ratio), 1))
        return image.resize(new_size, Image.LANCZOS)

    def _on_display_resize(self, _event) -> None:
        self._redraw_current_frame()

    # ------------------------------------------------------------------
    # Перемотка (seek)
    #
    # Примечание: точность перемотки зависит от расстановки ключевых кадров
    # (keyframes) в исходном видео — это особенность работы с сжатым видео
    # через OpenCV/FFmpeg, а не ошибка реализации.
    # ------------------------------------------------------------------
    def _on_seek_start(self, _event) -> None:
        self._seeking = True

    def _on_seek_end(self, _event) -> None:
        self._seeking = False
        self._render_frame_at(int(self._seek_slider.get()))

    def _on_seek_drag(self, value: float) -> None:
        if self._seeking:
            self._render_frame_at(int(value))

    def _update_seek_ui(self) -> None:
        if not self._seeking:
            self._seek_slider.set(self._current_frame_index)
        current_seconds = self._current_frame_index / self._fps if self._fps else 0.0
        total_seconds = self._frame_count / self._fps if self._fps else 0.0
        self._time_label.configure(
            text=f"{self._format_time(current_seconds)} / {self._format_time(total_seconds)}"
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes:02d}:{secs:02d}"

    # ------------------------------------------------------------------
    # Доступ извне (используется окном репорта об ошибке — Модуль 3)
    # ------------------------------------------------------------------
    def get_current_frame(self) -> Optional[Image.Image]:
        """Возвращает текущий отображаемый кадр в полном разрешении (для скриншота в репорте)."""
        return self._current_pil_frame

    def get_current_timestamp(self) -> float:
        """Возвращает текущую позицию воспроизведения в секундах."""
        return self._current_frame_index / self._fps if self._fps else 0.0

    def get_duration(self) -> float:
        """Возвращает полную длительность загруженного видео в секундах."""
        return self._frame_count / self._fps if self._fps else 0.0

    def seek_to_timestamp(self, seconds: float) -> None:
        """Перематывает на указанную секунду (используется панелью результатов анализа)."""
        if self._capture is None:
            return
        self.pause()
        frame_index = int(max(seconds, 0) * self._fps)
        self._render_frame_at(frame_index)
        self._seek_slider.set(self._current_frame_index)
