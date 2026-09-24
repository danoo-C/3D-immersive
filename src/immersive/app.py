"""Application wiring.

Builds the QApplication, applies the theme, shows the main window. Kept
separate from __main__ so tests can construct the window without taking over
the process.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from immersive import __version__
from immersive.audio.audition import Audition
from immersive.audio.device import load_backend, settle
from immersive.ui import theme, theme_menu
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity


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


def run(
    argv: list[str] | None = None,
    *,
    device: str | None = None,
    block: str | None = None,
) -> int:
    """Start the GUI and block until it closes."""
    app = build_application(argv)
    # M9 phase 4: make the theme directory on a real launch, so there is
    # somewhere to put a .3dimtheme. Deliberately here rather than anywhere
    # a test reaches - building a window must not make directories on
    # somebody's machine.
    theme_menu.user_theme_directory()

    # The audio stack is looked at on a real launch too, and only here: a
    # window built by a test must not go looking for a sound card.
    backend = load_backend()
    audition: Audition | None = None
    if isinstance(backend, str):
        unavailable, problems = backend, [backend]
    else:
        settled = settle(backend, device, block)
        problems = settled.problems
        unavailable = "" if settled.usable else problems[-1]
        if settled.usable:
            audition = Audition(backend, settled.output)

    window = MainWindow(audition=audition, unavailable=unavailable)
    for problem in problems:
        window.notices().add(Severity.WARN, problem)
    window.show()
    return app.exec()
