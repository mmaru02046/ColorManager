from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.branding import APP_NAME
from app.ui.main_window import MainWindow


_window: MainWindow | None = None


def app_resource_path(*parts: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).joinpath(*parts)
    return Path(__file__).resolve().parents[1].joinpath(*parts)


def main() -> int:
    global _window

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setQuitOnLastWindowClosed(True)

    icon_path = app_resource_path("icon.ico")
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    if _window is not None:
        _window.close()
        _window.deleteLater()
        _window = None

    _window = MainWindow(base_dir=Path.cwd())
    if not icon.isNull():
        _window.setWindowIcon(icon)
    _window.show()
    _window.raise_()
    _window.activateWindow()

    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
