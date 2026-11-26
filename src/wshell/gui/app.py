"""Qt application bootstrap."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from ..config import ShellConfig, ShellStore
from .main_window import MainWindow
from .theme import APP_QSS


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("webshell-mag")
    app.setApplicationDisplayName("webshell-mag")
    app.setOrganizationName("webshell-mag")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)
    return app


def main(argv: list[str] | None = None, quick: ShellConfig | None = None) -> int:
    app = create_app(argv)
    window = MainWindow()
    if quick is not None:
        window.shells[quick.id] = quick
        window._rebuild_tree()
        window.show()
        window.connect_shell(quick)
    else:
        window.show()
    return app.exec()
