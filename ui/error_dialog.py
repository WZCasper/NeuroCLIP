"""Модальное окно репорта об ошибке ИИ — интерфейс к Модулю 3 (Telegram)."""

from typing import Callable, Optional

import customtkinter as ctk

from config import SQUAD_MEMBERS
from modules.telegram_reporter import send_error_report
from ui import theme


class ErrorReportDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        get_frame: Callable,
        get_timestamp: Callable,
        video_filename: Optional[str],
        on_status: Callable[[str, str], None],
    ):
        super().__init__(master)

        self._get_frame = get_frame
        self._get_timestamp = get_timestamp
        self._video_filename = video_filename
        self._on_status = on_status

        self.title("Репорт об ошибке ИИ")
        self.geometry("460x460")
        self.configure(fg_color=theme.BG_PRIMARY)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self, text="Ошибка ИИ", text_color=theme.DANGER,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=22, weight="bold"),
        )
        header.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 8))

        reporter_label = ctk.CTkLabel(
            self, text="Кто репортит:", text_color=theme.TEXT_PRIMARY,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13),
        )
        reporter_label.grid(row=1, column=0, sticky="w", padx=24, pady=(8, 2))

        self._reporter_menu = ctk.CTkOptionMenu(
            self, values=SQUAD_MEMBERS, fg_color=theme.BG_SECONDARY,
            button_color=theme.ACCENT_CYAN, button_hover_color=theme.ACCENT_PURPLE,
            text_color=theme.TEXT_PRIMARY,
        )
        self._reporter_menu.set(SQUAD_MEMBERS[0])
        self._reporter_menu.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

        description_label = ctk.CTkLabel(
            self, text="Описание проблемы:", text_color=theme.TEXT_PRIMARY,
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=13),
        )
        description_label.grid(row=3, column=0, sticky="w", padx=24, pady=(0, 2))

        self._description_box = ctk.CTkTextbox(
            self, height=140, fg_color=theme.BG_SECONDARY, text_color=theme.TEXT_PRIMARY,
            border_width=1, border_color=theme.ACCENT_PURPLE,
        )
        self._description_box.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 8))

        has_frame = self._get_frame() is not None
        self._frame_status_label = ctk.CTkLabel(
            self,
            text=("К отчёту будет приложен текущий кадр видео." if has_frame
                  else "Видео не загружено — отчёт уйдёт без скриншота."),
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
            wraplength=400, justify="left",
        )
        self._frame_status_label.grid(row=5, column=0, sticky="w", padx=24, pady=(0, 16))

        self._error_label = ctk.CTkLabel(
            self, text="", text_color=theme.DANGER, wraplength=400, justify="left",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=12),
        )
        self._error_label.grid(row=6, column=0, sticky="w", padx=24, pady=(0, 4))

        self._send_button = ctk.CTkButton(
            self, text="Отправить в Telegram", command=self._on_send,
            fg_color=theme.ACCENT_CYAN, hover_color=theme.ACCENT_PURPLE, text_color="#050505",
            font=ctk.CTkFont(family=theme.FONT_FAMILY_UI, size=14, weight="bold"), height=42,
        )
        self._send_button.grid(row=7, column=0, sticky="ew", padx=24, pady=(4, 24))

    def _on_send(self) -> None:
        reporter = self._reporter_menu.get()
        description = self._description_box.get("1.0", "end").strip()
        frame = self._get_frame()

        self._send_button.configure(state="disabled", text="Отправка...")
        self._error_label.configure(text="")

        send_error_report(
            reporter=reporter,
            description=description,
            frame=frame,
            video_filename=self._video_filename,
            video_timestamp=self._get_timestamp() if frame is not None else None,
            on_success=lambda: self.after(0, self._handle_success),
            on_error=lambda msg: self.after(0, lambda: self._handle_error(msg)),
        )

    def _handle_success(self) -> None:
        self._on_status("Репорт отправлен в Telegram", theme.SUCCESS)
        self.destroy()

    def _handle_error(self, message: str) -> None:
        self._send_button.configure(state="normal", text="Отправить в Telegram")
        self._error_label.configure(text=message)
        self._on_status("Не удалось отправить репорт", theme.DANGER)
