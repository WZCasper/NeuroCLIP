"""Панель результатов анализа: прогресс + список найденных моментов (с чекбоксами отбора)."""

from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from modules.detectors.base import DetectionEvent
from ui import theme


class AnalysisPanel(ctk.CTkFrame):
    def __init__(self, master, on_event_selected: Callable[[float], None], **kwargs):
        super().__init__(master, fg_color=theme.BG_SECONDARY, corner_radius=16, **kwargs)
        self._on_event_selected = on_event_selected
        self._empty_label: Optional[ctk.CTkLabel] = None
        self._row_count = 0
        self._event_vars: List[Tuple[DetectionEvent, ctk.BooleanVar]] = []

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header, text="НАЙДЕННЫЕ МОМЕНТЫ", text_color=theme.ACCENT_CYAN,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        select_buttons = ctk.CTkFrame(header, fg_color="transparent")
        select_buttons.grid(row=1, column=0, sticky="w", pady=(4, 0))

        ctk.CTkButton(
            select_buttons, text="Все", width=44, height=22, command=lambda: self._set_all(True),
            fg_color="transparent", border_width=1, border_color=theme.TEXT_MUTED,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=11),
        ).grid(row=0, column=0, padx=(0, 6))

        ctk.CTkButton(
            select_buttons, text="Ничего", width=54, height=22, command=lambda: self._set_all(False),
            fg_color="transparent", border_width=1, border_color=theme.TEXT_MUTED,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=11),
        ).grid(row=0, column=1)

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
        self._event_vars = []

    def show_empty_state(self, text: str) -> None:
        self.clear()
        self._empty_label = ctk.CTkLabel(
            self._scroll_frame, text=text, text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12), wraplength=220,
        )
        self._empty_label.grid(row=0, column=0, pady=20, padx=10)

    def get_selected_events(self) -> List[DetectionEvent]:
        """Возвращает события, у которых чекбокс включён (по умолчанию включены все)."""
        return [event for event, var in self._event_vars if var.get()]

    def _set_all(self, value: bool) -> None:
        for _event, var in self._event_vars:
            var.set(value)

    def add_event(self, event: DetectionEvent) -> None:
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None

        minutes, seconds = divmod(int(event.timestamp), 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        row = ctk.CTkFrame(self._scroll_frame, fg_color=theme.BG_PRIMARY, corner_radius=8)
        row.grid(row=self._row_count, column=0, sticky="ew", pady=3, padx=2)
        row.grid_columnconfigure(2, weight=1)

        include_var = ctk.BooleanVar(value=True)  # по умолчанию включено — как раньше
        checkbox = ctk.CTkCheckBox(
            row, text="", variable=include_var, width=18, checkbox_width=18, checkbox_height=18,
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE, border_color=theme.TEXT_MUTED,
        )
        checkbox.grid(row=0, column=0, padx=(10, 2), pady=8)
        self._event_vars.append((event, include_var))

        time_label = ctk.CTkLabel(
            row, text=time_str, text_color=theme.ACCENT_CYAN, width=44, cursor="hand2",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13, weight="bold"),
        )
        time_label.grid(row=0, column=1, padx=(4, 6), pady=8)

        label_widget = ctk.CTkLabel(
            row, text=event.label, text_color=theme.TEXT_PRIMARY, anchor="w", cursor="hand2",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
            wraplength=155, justify="left",
        )
        label_widget.grid(row=0, column=2, sticky="ew", padx=6, pady=8)

        confidence_label = ctk.CTkLabel(
            row, text=f"{int(event.confidence * 100)}%", text_color=theme.TEXT_MUTED, cursor="hand2",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=11),
        )
        confidence_label.grid(row=0, column=3, padx=(4, 10), pady=8)

        # Клик по строке (кроме самого чекбокса) — перемотка, как и раньше;
        # чекбокс обрабатывает клики сам через свою переменную, независимо.
        for widget in (row, time_label, label_widget, confidence_label):
            widget.bind("<Button-1>", lambda _event, ts=event.timestamp: self._on_event_selected(ts))

        self._row_count += 1
