"""NeuroClip — точка входа в приложение."""

from ui.main_window import NeuroClipApp


def main() -> None:
    app = NeuroClipApp()
    app.mainloop()


if __name__ == "__main__":
    main()
