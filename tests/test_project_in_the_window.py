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
from immersive.core.document import UNTITLED
from immersive.core.edits import AddChannel
from immersive.core.io import project_io
from immersive.core.model import Channel, MediaFile, Project
from immersive.core.time import SAMPLE_RATE
from immersive.ui.main_window import WINDOW_TITLE, MainWindow, Unsaved
from immersive.ui.notices import Severity

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


def answering(window: MainWindow, answer: Unsaved) -> list[int]:
    """Replace the prompt with a fixed answer, and count how often it asked."""
    asked: list[int] = []

    def ask() -> Unsaved:
        asked.append(1)
        return answer

    window._ask_about_unsaved = ask  # type: ignore[method-assign]
    return asked


def choosing(
    window: MainWindow, *, open: Path | None = None, save: Path | None = None
) -> None:
    """Replace the file dialogs. `None` is the person pressing Cancel."""
    window._choose_open_path = lambda: open  # type: ignore[method-assign]
    window._choose_save_path = lambda: save  # type: ignore[method-assign]


def is_dirty(window: MainWindow) -> bool:
    return window.document().is_dirty


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


# --------------------------------------------------------------------------- #
# new, open, save, save as
# --------------------------------------------------------------------------- #


def test_a_project_saved_and_reopened_through_the_window_is_the_same(
    window: MainWindow, tmp_path: Path
) -> None:
    """The phase's first acceptance line, through the menus' own methods."""
    an_edit(window)
    built = window.document().project
    choosing(window, save=tmp_path / "round trip.3dim")
    assert window.save_project()

    other = MainWindow()
    choosing(other, open=tmp_path / "round trip.3dim")
    assert other.open_project()

    assert other.document().project == built
    other.deleteLater()


def test_saving_an_untitled_project_asks_where(
    window: MainWindow, tmp_path: Path
) -> None:
    choosing(window, save=tmp_path / "mix.3dim")

    assert window.save_project()

    assert window.document().path == tmp_path / "mix.3dim"


def test_a_bare_name_gets_the_suffix(window: MainWindow, tmp_path: Path) -> None:
    """Otherwise the Open dialog's own filter hides the file next time."""
    choosing(window, save=tmp_path / "mix")

    assert window.save_project_as()

    assert (tmp_path / "mix.3dim").is_file()
    assert window.document().title == "mix"


def test_a_cancelled_save_as_writes_nothing(window: MainWindow, tmp_path: Path) -> None:
    an_edit(window)
    choosing(window, save=None)

    assert not window.save_project()

    assert is_dirty(window)
    assert list(tmp_path.iterdir()) == []


def test_a_save_that_fails_is_an_error_and_stays_unsaved(
    window: MainWindow, tmp_path: Path
) -> None:
    an_edit(window)
    choosing(window, save=tmp_path / "no such folder" / "mix.3dim")

    assert not window.save_project_as()

    reported = window.notices().newest_first()
    assert [notice.severity for notice in reported] == [Severity.ERROR]
    assert is_dirty(window)


def test_success_is_quiet(window: MainWindow, tmp_path: Path) -> None:
    """The title's mark clearing is the feedback. A notice per Ctrl+S is the
    kind people learn to stop reading."""
    an_edit(window)
    choosing(window, save=tmp_path / "mix.3dim", open=tmp_path / "mix.3dim")

    window.save_project()
    window.open_project()

    assert window.notices().newest_first() == []


@pytest.mark.parametrize(
    "contents", [b"{ not json", b'{"schema_version": 1, "bpm": "fast"}']
)
def test_a_file_that_will_not_open_is_an_error_and_changes_nothing(
    window: MainWindow, tmp_path: Path, contents: bytes
) -> None:
    bad = tmp_path / "bad.3dim"
    bad.write_bytes(contents)
    an_edit(window)
    project = window.document().project
    choosing(window, open=bad)
    answering(window, Unsaved.DISCARD)

    assert not window.open_project()

    reported = window.notices().newest_first()
    assert len(reported) == 1
    assert reported[0].severity is Severity.ERROR
    assert reported[0].message == "bad.3dim could not be opened"
    assert reported[0].detail, "the reasons go with it"
    assert window.document().project is project
    assert is_dirty(window)


def test_a_file_that_is_not_there_is_an_error(
    window: MainWindow, tmp_path: Path
) -> None:
    choosing(window, open=tmp_path / "gone.3dim")

    assert not window.open_project()

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.ERROR


def test_missing_media_is_one_warning_naming_every_file(
    window: MainWindow, tmp_path: Path
) -> None:
    """F-3's report half. One notice per open, one line per file."""
    audio = [tmp_path / f"{name}.wav" for name in ("kick", "snare", "hat")]
    project = Project(
        media_pool=[
            MediaFile(f"m-0000000{n}", str(path), path.stem, SAMPLE_RATE, 1, 10)
            for n, path in enumerate(audio, start=1)
        ]
    )
    for path in audio:
        path.write_bytes(b"x")
    project_io.save(project, tmp_path / "song.3dim")
    audio[0].unlink()
    audio[2].unlink()
    choosing(window, open=tmp_path / "song.3dim")

    assert window.open_project()

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert notice.message == "song.3dim opened with 2 media files missing"
    assert list(notice.detail) == [str(audio[0]), str(audio[2])]
    assert window.document().title == "song", "and it is open"


def test_a_cancelled_open_dialog_changes_nothing(window: MainWindow) -> None:
    an_edit(window)
    answering(window, Unsaved.DISCARD)
    choosing(window, open=None)

    assert not window.open_project()

    assert is_dirty(window)
    assert window.notices().newest_first() == []


# --------------------------------------------------------------------------- #
# the one confirmation
# --------------------------------------------------------------------------- #


def test_nothing_unsaved_is_never_asked_about(window: MainWindow) -> None:
    asked = answering(window, Unsaved.CANCEL)

    assert window.new_project()
    assert window.close()

    assert asked == []


def test_discard_goes_ahead(window: MainWindow) -> None:
    an_edit(window)
    asked = answering(window, Unsaved.DISCARD)

    assert window.new_project()

    assert asked == [1]
    assert window.document().project.channels == []
    assert window.document().title == UNTITLED


def test_cancel_keeps_the_project_and_its_history(window: MainWindow) -> None:
    an_edit(window)
    project = window.document().project
    answering(window, Unsaved.CANCEL)

    assert not window.new_project()

    assert window.document().project is project
    assert window.document().can_undo


def test_save_saves_then_goes_ahead(window: MainWindow, tmp_path: Path) -> None:
    window.document().save_as(tmp_path / "kept.3dim")
    an_edit(window)
    answering(window, Unsaved.SAVE)

    assert window.new_project()

    assert "c-00000001" in (tmp_path / "kept.3dim").read_text(encoding="utf-8")
    assert window.document().title == UNTITLED


def test_save_whose_dialog_is_cancelled_does_not_go_ahead(window: MainWindow) -> None:
    """The case the confirmation exists for: the person asked to keep it."""
    an_edit(window)
    project = window.document().project
    answering(window, Unsaved.SAVE)
    choosing(window, save=None)

    assert not window.new_project()

    assert window.document().project is project
    assert is_dirty(window)


def test_open_asks_too(window: MainWindow, tmp_path: Path) -> None:
    project_io.save(Project(), tmp_path / "other.3dim")
    an_edit(window)
    asked = answering(window, Unsaved.CANCEL)
    choosing(window, open=tmp_path / "other.3dim")

    assert not window.open_project()

    assert asked == [1]
    assert window.document().title == UNTITLED


def test_quitting_with_unsaved_changes_asks_and_cancel_keeps_the_window(
    window: MainWindow,
) -> None:
    an_edit(window)
    asked = answering(window, Unsaved.CANCEL)

    assert not window.close()

    assert asked == [1]


def test_quitting_with_discard_closes(window: MainWindow) -> None:
    an_edit(window)
    answering(window, Unsaved.DISCARD)

    assert window.close()


def test_a_real_dialog_fails_the_test_rather_than_hanging_it(
    window: MainWindow,
) -> None:
    """conftest.py's guard, asserted - it is the only thing between a
    forgotten replacement and a suite that stops with no failure at all."""
    with pytest.raises(AssertionError, match="real modal dialog"):
        window._ask_about_unsaved()
    with pytest.raises(AssertionError, match="real modal dialog"):
        window._choose_open_path()
