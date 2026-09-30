"""Application wiring.

Builds the QApplication, applies the theme, shows the main window. Kept
separate from __main__ so tests can construct the window without taking over
the process.
"""

from __future__ import annotations

import gc
import sys
from typing import Final

from PySide6.QtWidgets import QApplication

from immersive import __version__
from immersive.audio.device import load_backend, settle
from immersive.audio.player import Player
from immersive.ui import theme, theme_menu
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity

#: How long a thread may hold the GIL while another waits for it (D-39):
#: 1 ms, not CPython's 5. It bounds each wait, and the audio thread waits
#: once for every numpy call that releases the GIL, which with a busy UI
#: is many a block (D-137): so this bounds each of those, and is not the
#: whole of the answer.
SWITCH_INTERVAL: Final = 0.001


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


def settle_memory() -> None:
    """Collect what is garbage now, then freeze the rest (D-142): a later
    collection scans only what was made since, where a full one of a
    32-channel window's heap held the GIL for 67 ms, six blocks. Unfrozen
    first, so what the previous project left in cycles is still freed."""
    gc.unfreeze()
    gc.collect()
    gc.freeze()


def run(
    argv: list[str] | None = None,
    *,
    device: str | None = None,
    block: str | None = None,
) -> int:
    """Start the GUI and block until it closes."""
    # First, before the output is so much as looked for, so every stream
    # this process opens is called under it (D-39). Here and not in
    # build_application, which every test calls.
    sys.setswitchinterval(SWITCH_INTERVAL)
    app = build_application(argv)
    # M9 phase 4: make the theme directory on a real launch, so there is
    # somewhere to put a .3dimtheme. Deliberately here rather than anywhere
    # a test reaches - building a window must not make directories on
    # somebody's machine.
    theme_menu.user_theme_directory()

    # The audio stack is looked at on a real launch too, and only here: a
    # window built by a test must not go looking for a sound card.
    backend = load_backend()
    player: Player | None = None
    if isinstance(backend, str):
        unavailable, problems = backend, [backend]
    else:
        settled = settle(backend, device, block)
        problems = settled.problems
        unavailable = "" if settled.usable else problems[-1]
        if settled.usable:
            player = Player(backend, settled.output)

    window = MainWindow(player=player, unavailable=unavailable)
    window.settle = settle_memory
    for problem in problems:
        window.notices().add(Severity.WARN, problem)
    window.show()
    settle_memory()
    # The HRTF set, on a worker (D-120): here, where a real launch is, and
    # never in the window's constructor, where every test is.
    window.prepare_hrtf()
    code = app.exec()
    window.stop_work()
    return code
