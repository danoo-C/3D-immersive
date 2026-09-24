"""The window as the document's front door (D-85). Marked gui.

What a document does is `test_document.py`'s, headless. This file asserts
only what the window adds: that it shows the document's state and never
keeps a second copy of it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QToolBar

from immersive.app import build_application
from immersive.core.edits import AddChannel
from immersive.core.model import Channel
from immersive.ui.main_window import WINDOW_TITLE, MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def window() -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow()
    yield made
    made.deleteLater()


def an_edit(window: MainWindow, channel_id: str = "c-00000001") -> None:
    project = window.document().project
    window.document().push(AddChannel(project, Channel(channel_id, "A", "#A855F7")))


# --------------------------------------------------------------------------- #
# undo and redo
# --------------------------------------------------------------------------- #


def test_undo_and_redo_start_disabled_and_say_why(window: MainWindow) -> None:
    assert not window._undo.isEnabled()
    assert not window._redo.isEnabled()
    assert window._undo.toolTip() == "Undo  (Ctrl+Z)\nNothing to undo."
    assert window._redo.toolTip() == "Redo  (Ctrl+Shift+Z)\nNothing to redo."


def test_undo_and_redo_follow_the_document(window: MainWindow) -> None:
    an_edit(window)
    assert window._undo.isEnabled()
    assert not window._redo.isEnabled()
    assert window._undo.toolTip() == "Undo  (Ctrl+Z)", "no stale reason"

    window._undo.trigger()
    assert window.document().project.channels == []
    assert not window._undo.isEnabled()
    assert window._redo.isEnabled()

    window._redo.trigger()
    assert len(window.document().project.channels) == 1
    assert window._undo.isEnabled()
    assert not window._redo.isEnabled()


def test_the_toolbar_undo_is_the_menu_undo(window: MainWindow) -> None:
    """One object, so the two can never disagree about the stack."""
    toolbar = window.findChildren(QToolBar)[0]

    assert window._undo in toolbar.actions()
    assert window._redo in toolbar.actions()


# --------------------------------------------------------------------------- #
# the title
# --------------------------------------------------------------------------- #


def test_an_untitled_project_says_so(window: MainWindow) -> None:
    assert window.windowTitle() == f"Untitled[*] — {WINDOW_TITLE}"
    assert not window.isWindowModified()


def test_the_title_marks_unsaved_changes(window: MainWindow) -> None:
    an_edit(window)
    assert window.isWindowModified()

    window.document().undo()
    assert not window.isWindowModified(), "back where it was saved"


def test_the_title_names_the_file_and_saving_clears_the_mark(
    window: MainWindow, tmp_path: Path
) -> None:
    an_edit(window)

    window.document().save_as(tmp_path / "mix.3dim")

    assert window.windowTitle() == f"mix[*] — {WINDOW_TITLE}"
    assert not window.isWindowModified()

    an_edit(window, "c-00000002")
    assert window.isWindowModified(), "the next edit brings it back"
