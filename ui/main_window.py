"""Главное окно приложения NeuroClip: сборка всех компонентов интерфейса."""

import os
import threading
from tkinter import filedialog
from typing import List, Optional

import customtkinter as ctk

from config import APP_NAME, APP_VERSION
from modules.analysis_pipeline import AnalysisPipeline
from modules.detectors.base import DetectionEvent
from modules.montage_builder import MontageError, build_montage, events_to_segments
from modules.preview_generator import PreviewError, build_preview
from state import AISettings
from ui import theme
from ui.analysis_panel import AnalysisPanel
from ui.error_dialog import ErrorReportDialog
from ui.nameplate import Nameplate
from ui.video_player import VideoPlayer

ctk.set_appearance_mode("Dark")

_SLIDER_DEFINITIONS = [
    ("low_hp_sensitivity", "🩸 Низкое HP"),
    ("killfeed_sensitivity", "🎯 Килфид"),
    ("explosion_sensitivity", "💥 Взрывы / прицел"),
    ("audio_peak_sensitivity", "🔊 Громкие звуки"),
    ("eye_contact_sensitivity", "👁 Зрительный контакт"),
]


class NeuroClipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1360x820")
        self.minsize(1120, 680)
        self.configure(fg_color=theme.BG_PRIMARY)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.settings = AISettings()
        self.current_video_path: Optional[str] = None
        self._pipeline: Optional[AnalysisPipeline] = None
        self._found_events: List[DetectionEvent] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()
        self._build_main_area()
        self._build_status_bar()

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(20, 8))
        Nameplate(header).pack(anchor="center")

    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self, fg_color=theme.BG_SECONDARY, corner_radius=16,
            border_width=1, border_color=theme.ACCENT_PURPLE, width=300,
        )
        sidebar.grid(row=1, column=0, sticky="nsw", padx=(24, 12), pady=12)
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            sidebar, text="УПРАВЛЕНИЕ", text_color=theme.ACCENT_CYAN,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=18, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 12))

        self._upload_button = ctk.CTkButton(
            sidebar, text="📂 Загрузить видео", command=self._on_upload_video,
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE, text_color="#050505",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"), height=42,
        )
        self._upload_button.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))

        self._analyze_button = ctk.CTkButton(
            sidebar, text="🔍 Анализировать", command=self._on_analyze,
            fg_color="transparent", hover_color=theme.ACCENT_PURPLE, border_width=2,
            border_color=theme.ACCENT_CYAN, text_color=theme.ACCENT_CYAN,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
            height=42, state="disabled",
        )
        self._analyze_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))

        self._montage_button = ctk.CTkButton(
            sidebar, text="🎬 Собрать монтаж", command=self._on_build_montage,
            fg_color=theme.ACCENT_MAGENTA, hover_color=theme.ACCENT_PURPLE, text_color="#050505",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
            height=42, state="disabled",
        )
        self._montage_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))

        self._preview_button = ctk.CTkButton(
            sidebar, text="🖼 Создать превью", command=self._on_build_preview,
            fg_color="transparent", hover_color=theme.ACCENT_PURPLE, border_width=2,
            border_color=theme.ACCENT_MAGENTA, text_color=theme.ACCENT_MAGENTA,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"),
            height=42, state="disabled",
        )
        self._preview_button.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))

        self._add_separator(sidebar, row=5)

        sliders_title = ctk.CTkLabel(
            sidebar, text="ЧУВСТВИТЕЛЬНОСТЬ ИИ", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12, weight="bold"),
        )
        sliders_title.grid(row=6, column=0, sticky="w", padx=20, pady=(0, 8))

        row = 7
        for attr_name, label_text in _SLIDER_DEFINITIONS:
            row = self._add_sensitivity_slider(sidebar, row, attr_name, label_text)

        self._laughter_toggle_var = ctk.BooleanVar(value=False)
        self._laughter_toggle = ctk.CTkCheckBox(
            sidebar, text="😂 Распознавать смех (Whisper, медленно)",
            variable=self._laughter_toggle_var,
            text_color=theme.TEXT_PRIMARY, font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE, border_color=theme.TEXT_MUTED,
        )
        self._laughter_toggle.grid(row=row, column=0, sticky="w", padx=20, pady=(0, 16))
        row += 1

        self._add_separator(sidebar, row=row)
        row += 1

        self._error_button = ctk.CTkButton(
            sidebar, text="❌ Ошибка ИИ", command=self._on_report_error,
            fg_color="transparent", hover_color=theme.DANGER, border_width=2,
            border_color=theme.DANGER, text_color=theme.DANGER,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"), height=42,
        )
        self._error_button.grid(row=row, column=0, sticky="ew", padx=20, pady=(0, 20))

    @staticmethod
    def _add_separator(parent, row: int) -> None:
        sep = ctk.CTkFrame(parent, fg_color=theme.ACCENT_PURPLE, height=1)
        sep.grid(row=row, column=0, sticky="ew", padx=20, pady=(8, 16))

    def _add_sensitivity_slider(self, parent, row: int, attr_name: str, label_text: str) -> int:
        """Создаёт слайдер чувствительности, привязанный к self.settings. Возвращает следующую свободную строку."""
        initial_value = getattr(self.settings, attr_name)
        value_label = ctk.CTkLabel(
            parent, text=f"{label_text}: {int(initial_value)}%", text_color=theme.TEXT_PRIMARY,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13),
        )
        value_label.grid(row=row, column=0, sticky="w", padx=20, pady=(4, 2))

        def _on_change(value: float, _attr=attr_name, _label=value_label, _text=label_text) -> None:
            setattr(self.settings, _attr, round(float(value), 1))
            _label.configure(text=f"{_text}: {int(round(float(value)))}%")

        slider = ctk.CTkSlider(
            parent, from_=0, to=100, number_of_steps=100, command=_on_change,
            progress_color=theme.ACCENT_CYAN, button_color=theme.ACCENT_MAGENTA,
            button_hover_color=theme.ACCENT_PURPLE,
        )
        slider.set(initial_value)
        slider.grid(row=row + 1, column=0, sticky="ew", padx=20, pady=(0, 4))

        return row + 2

    # ------------------------------------------------------------------
    def _build_main_area(self) -> None:
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.grid(row=1, column=1, sticky="nsew", padx=(12, 24), pady=12)
        main_area.grid_rowconfigure(0, weight=1)
        main_area.grid_columnconfigure(0, weight=3)
        main_area.grid_columnconfigure(1, weight=1)

        self.video_player = VideoPlayer(main_area)
        self.video_player.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        self.analysis_panel = AnalysisPanel(main_area, on_event_selected=self._on_event_selected,
                                             width=260)
        self.analysis_panel.grid(row=0, column=1, sticky="nsew")
        self.analysis_panel.grid_propagate(False)

    # ------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        self._status_label = ctk.CTkLabel(
            self, text="Готов к работе", text_color=theme.TEXT_MUTED, anchor="w",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
        )
        self._status_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=28, pady=(0, 12))

    def _set_status(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._status_label.configure(text=text, text_color=color)

    # ------------------------------------------------------------------
    # Обработчики событий
    # ------------------------------------------------------------------
    def _on_upload_video(self) -> None:
        filepath = filedialog.askopenfilename(
            title="Выберите видео",
            filetypes=[("Видео файлы", "*.mp4 *.mkv *.mov *.avi *.webm"), ("Все файлы", "*.*")],
        )
        if not filepath:
            return

        if self.video_player.load_video(filepath):
            self.current_video_path = filepath
            self._analyze_button.configure(state="normal")
            self._found_events = []
            self._montage_button.configure(state="disabled")
            self._preview_button.configure(state="disabled")
            self.analysis_panel.show_empty_state("Нажмите «Анализировать», чтобы найти моменты")
            self._set_status(f"Загружено: {os.path.basename(filepath)}", theme.SUCCESS)
        else:
            self.current_video_path = None
            self._analyze_button.configure(state="disabled")
            self._set_status(f"Не удалось открыть файл: {os.path.basename(filepath)}", theme.DANGER)

    def _on_report_error(self) -> None:
        ErrorReportDialog(
            self,
            get_frame=self.video_player.get_current_frame,
            get_timestamp=self.video_player.get_current_timestamp,
            video_filename=os.path.basename(self.current_video_path) if self.current_video_path else None,
            on_status=self._set_status,
        )

    def _on_analyze(self) -> None:
        if not self.current_video_path:
            self._set_status("Сначала загрузите видео", theme.DANGER)
            return

        self._analyze_button.configure(state="disabled", text="Анализ...")
        self._upload_button.configure(state="disabled")
        self.analysis_panel.clear()
        self.analysis_panel.show_progress(0.0)
        self._set_status("Анализ запущен...", theme.ACCENT_CYAN)

        self._pipeline = AnalysisPipeline(self.settings)

        def on_progress(fraction: float) -> None:
            self.after(0, lambda: self.analysis_panel.show_progress(fraction))

        def on_event(event: DetectionEvent) -> None:
            self.after(0, lambda: self.analysis_panel.add_event(event))

        def on_done(events: list) -> None:
            def _finish() -> None:
                self.analysis_panel.hide_progress()
                self._analyze_button.configure(state="normal", text="🔍 Анализировать")
                self._upload_button.configure(state="normal")
                self._found_events = events
                if events:
                    self._montage_button.configure(state="normal")
                    self._preview_button.configure(state="normal")
                else:
                    self.analysis_panel.show_empty_state("Событий не найдено")
                self._set_status(f"Анализ завершён — найдено моментов: {len(events)}", theme.SUCCESS)
            self.after(0, _finish)

        def on_error(message: str) -> None:
            def _finish() -> None:
                self.analysis_panel.hide_progress()
                self._analyze_button.configure(state="normal", text="🔍 Анализировать")
                self._upload_button.configure(state="normal")
                self._set_status(f"Ошибка анализа: {message}", theme.DANGER)
            self.after(0, _finish)

        def on_warning(message: str) -> None:
            self.after(0, lambda: self._set_status(f"⚠️ {message}", theme.TEXT_MUTED))

        def on_status(message: str) -> None:
            self.after(0, lambda: self._set_status(message, theme.ACCENT_CYAN))

        self._pipeline.run(
            self.current_video_path,
            on_progress=on_progress, on_event=on_event, on_done=on_done, on_error=on_error,
            on_warning=on_warning, on_status=on_status,
            enable_laughter=self._laughter_toggle_var.get(),
        )

    def _on_event_selected(self, timestamp: float) -> None:
        self.video_player.seek_to_timestamp(timestamp)

    def _on_build_montage(self) -> None:
        selected_events = self.analysis_panel.get_selected_events()
        if not selected_events or not self.current_video_path:
            self._set_status("Отметьте хотя бы один момент галочкой", theme.DANGER)
            return

        output_path = filedialog.asksaveasfilename(
            title="Сохранить монтаж как",
            defaultextension=".mp4",
            filetypes=[("Видео MP4", "*.mp4")],
            initialfile="neuroclip_montage.mp4",
        )
        if not output_path:
            return

        duration = self.video_player.get_duration()
        segments = events_to_segments(selected_events, video_duration=duration)

        self._montage_button.configure(state="disabled", text="Собираю монтаж...")
        self._preview_button.configure(state="disabled")
        self._set_status(f"Собираю монтаж из {len(segments)} отрезков...", theme.ACCENT_CYAN)

        def _worker() -> None:
            try:
                def on_progress(fraction: float) -> None:
                    self.after(0, lambda: self._set_status(
                        f"Рендер монтажа: {int(fraction * 100)}%", theme.ACCENT_CYAN))

                build_montage(self.current_video_path, segments, output_path, on_progress=on_progress)

                def _success() -> None:
                    self._montage_button.configure(state="normal", text="🎬 Собрать монтаж")
                    self._preview_button.configure(state="normal")
                    self._set_status(f"✅ Монтаж сохранён: {os.path.basename(output_path)}", theme.SUCCESS)
                self.after(0, _success)

            except MontageError as exc:
                def _fail() -> None:
                    self._montage_button.configure(state="normal", text="🎬 Собрать монтаж")
                    self._preview_button.configure(state="normal")
                    self._set_status(f"❌ Ошибка монтажа: {exc}", theme.DANGER)
                self.after(0, _fail)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_build_preview(self) -> None:
        selected_events = self.analysis_panel.get_selected_events()
        if not selected_events or not self.current_video_path:
            self._set_status("Отметьте хотя бы один момент галочкой", theme.DANGER)
            return

        output_path = filedialog.asksaveasfilename(
            title="Сохранить превью как",
            defaultextension=".png",
            filetypes=[("Изображение PNG", "*.png")],
            initialfile="neuroclip_preview.png",
        )
        if not output_path:
            return

        self._montage_button.configure(state="disabled")
        self._preview_button.configure(state="disabled", text="Создаю превью...")
        self._set_status("Создаю превью (первый запуск может скачивать модель rembg)...", theme.ACCENT_CYAN)

        def _worker() -> None:
            try:
                _, background_removed = build_preview(self.current_video_path, selected_events, output_path)

                def _success() -> None:
                    self._montage_button.configure(state="normal")
                    self._preview_button.configure(state="normal", text="🖼 Создать превью")
                    note = "" if background_removed else " (без удаления фона — rembg недоступен)"
                    self._set_status(f"✅ Превью сохранено: {os.path.basename(output_path)}{note}", theme.SUCCESS)
                self.after(0, _success)

            except PreviewError as exc:
                def _fail() -> None:
                    self._montage_button.configure(state="normal")
                    self._preview_button.configure(state="normal", text="🖼 Создать превью")
                    self._set_status(f"❌ Ошибка превью: {exc}", theme.DANGER)
                self.after(0, _fail)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.cancel()
        self.video_player.stop()
        self.destroy()
