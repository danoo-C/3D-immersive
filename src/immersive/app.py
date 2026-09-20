"""Application wiring.

Builds the QApplication, applies the theme, shows the main window. Kept
separate from __main__ so tests can construct the window without taking over
the process.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from immersive import __version__
from immersive.ui import theme
from immersive.ui.main_window import MainWindow


def build_application(argv: list[str] | None = None) -> QApplication:
    """Create (or reuse) the QApplication and apply the theme."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv[:1])
    assert isinstance(app, QApplication)

    app.setApplicationName("3d immersive")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("3d immersive")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet())
    return app


def run(argv: list[str] | None = None) -> int:
    """Start the GUI and block until it closes."""
    app = build_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()
