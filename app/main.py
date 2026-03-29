from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


_window: MainWindow | None = None


def main() -> int:
    global _window

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName("Color Library Manager")
        app.setQuitOnLastWindowClosed(True)

    icon_path = Path(__file__).resolve().parents[1] / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    if _window is not None:
        _window.close()
        _window.deleteLater()
        _window = None

    _window = MainWindow(base_dir=Path.cwd())
    if icon_path.exists():
        _window.setWindowIcon(QIcon(str(icon_path)))
    _window.show()
    _window.raise_()
    _window.activateWindow()

    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
