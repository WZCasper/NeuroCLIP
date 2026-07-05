"""Панель результатов анализа: прогресс + список найденных моментов."""

from typing import Callable, Optional

import customtkinter as ctk

from modules.detectors.base import DetectionEvent
from ui import theme


class AnalysisPanel(ctk.CTkFrame):
    def __init__(self, master, on_event_selected: Callable[[float], None], **kwargs):
        super().__init__(master, fg_color=theme.BG_SECONDARY, corner_radius=16, **kwargs)
        self._on_event_selected = on_event_selected
        self._empty_label: Optional[ctk.CTkLabel] = None
        self._row_count = 0

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self, text="НАЙДЕННЫЕ МОМЕНТЫ", text_color=theme.ACCENT_CYAN,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self._progress_bar = ctk.CTkProgressBar(self, progress_color=theme.ACCENT_CYAN)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._progress_bar.grid_remove()

        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.ACCENT_PURPLE,
            scrollbar_button_hover_color=theme.ACCENT_MAGENTA,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self.show_empty_state("Загрузите видео и нажмите «Анализировать»")

    # ------------------------------------------------------------------
    def show_progress(self, fraction: float) -> None:
        self._progress_bar.grid()
        self._progress_bar.set(max(0.0, min(fraction, 1.0)))

    def hide_progress(self) -> None:
        self._progress_bar.grid_remove()

    def clear(self) -> None:
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()
        self._empty_label = None
        self._row_count = 0

    def show_empty_state(self, text: str) -> None:
        self.clear()
        self._empty_label = ctk.CTkLabel(
            self._scroll_frame, text=text, text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12), wraplength=220,
        )
        self._empty_label.grid(row=0, column=0, pady=20, padx=10)

    def add_event(self, event: DetectionEvent) -> None:
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None

        minutes, seconds = divmod(int(event.timestamp), 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        row = ctk.CTkFrame(self._scroll_frame, fg_color=theme.BG_PRIMARY, corner_radius=8,
                            cursor="hand2")
        row.grid(row=self._row_count, column=0, sticky="ew", pady=3, padx=2)
        row.grid_columnconfigure(1, weight=1)

        time_label = ctk.CTkLabel(
            row, text=time_str, text_color=theme.ACCENT_CYAN, width=48,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13, weight="bold"),
        )
        time_label.grid(row=0, column=0, padx=(10, 6), pady=8)

        label_widget = ctk.CTkLabel(
            row, text=event.label, text_color=theme.TEXT_PRIMARY, anchor="w",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
            wraplength=170, justify="left",
        )
        label_widget.grid(row=0, column=1, sticky="ew", padx=6, pady=8)

        confidence_label = ctk.CTkLabel(
            row, text=f"{int(event.confidence * 100)}%", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=11),
        )
        confidence_label.grid(row=0, column=2, padx=(4, 10), pady=8)

        for widget in (row, time_label, label_widget, confidence_label):
            widget.bind("<Button-1>", lambda _event, ts=event.timestamp: self._on_event_selected(ts))

        self._row_count += 1
