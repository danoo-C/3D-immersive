"""The parameters pane: following the selection, and the project's settings,
the clip's, the channel's and the sample's fields. Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.model import Clip, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE, to_bar_beat
from immersive.ui import theme
from immersive.ui.main_window import COMMON_SIGNATURES, MainWindow
from immersive.ui.parameters.views import ProjectView
from immersive.ui.widgets.numeric import NumericField

pytestmark = pytest.mark.gui

SECOND = SAMPLE_RATE
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10 * SECOND)


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def arrange(document: Document, lanes: int = 2) -> list[list[Clip]]:
    """`lanes` channels, each with clips a second long at 0, 2 and 4 s."""
    document.push(AddMedia(document.project, [MEDIA]))
    grid = []
    for lane in range(lanes):
        project = document.project
        document.push(
            AddChannel(project, new_channel(project, theme.active().channels))
        )
        clips = [
            Clip(f"k-000{lane}{n}000", MEDIA.id, n * 2 * SECOND, 0, SECOND)
            for n in range(3)
        ]
        document.push(DropClips(project, project.channels[lane], clips))
        grid.append(clips)
    return grid


def a_window(lanes: int = 2) -> tuple[MainWindow, list[list[Clip]]]:
    window = MainWindow()
    grid = arrange(window.document(), lanes)
    window.show()
    QApplication.processEvents()
    return window, grid


def stacked(window: MainWindow) -> int:
    return len(window.document()._stack)


def press(field: NumericField) -> None:
    """A click that never moved: it opens the field for typing."""
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            field,
            QMouseEvent(
                kind,
                QPointF(20, 8),
                field.mapToGlobal(QPointF(20, 8)),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )


def type_into(field: NumericField, text: str) -> None:
    press(field)
    field.selectAll()
    QTest.keyClicks(field, text)
    QTest.keyClick(field, Qt.Key.Key_Return)


def project_view(window: MainWindow) -> ProjectView:
    view = window.parameters().view()
    assert isinstance(view, ProjectView)
    return view


# --------------------------------------------------------------------------- #
# following the selection
# --------------------------------------------------------------------------- #


def test_the_pane_follows_the_selections_kind() -> None:
    window, grid = a_window()
    document, pane = window.document(), window.parameters()
    assert pane.view().heading() == "Project"

    document.selection.select(Kind.CLIPS, [grid[0][0]])
    assert not isinstance(pane.view(), ProjectView)
    document.selection.select(Kind.CHANNELS, document.project.channels[:1])
    assert not isinstance(pane.view(), ProjectView)
    document.selection.select(Kind.MEDIA, document.project.media_pool)
    assert not isinstance(pane.view(), ProjectView)
    document.selection.clear()
    assert isinstance(pane.view(), ProjectView)


def test_the_view_is_rebuilt_only_when_the_kind_changes() -> None:
    window, grid = a_window()
    document, pane = window.document(), window.parameters()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    view = pane.view()

    document.selection.select(Kind.CLIPS, [grid[1][2]])
    document.push(SetAttribute(document.project.channels[0], "name", "Kick"))

    assert pane.view() is view


def test_a_value_being_typed_survives_an_edit_elsewhere() -> None:
    window, _ = a_window()
    document = window.document()
    tempo = project_view(window).tempo
    press(tempo)
    tempo.selectAll()
    QTest.keyClicks(tempo, "133")

    document.push(SetAttribute(document.project.channels[0], "name", "Kick"))

    assert tempo.text() == "133"
    QTest.keyClick(tempo, Qt.Key.Key_Return)
    assert document.project.bpm == 133.0


# --------------------------------------------------------------------------- #
# the project's settings
# --------------------------------------------------------------------------- #


def test_a_tempo_from_the_pane_is_one_undo_and_the_toolbar_follows() -> None:
    window, _ = a_window()
    document = window.document()
    count = stacked(window)

    type_into(project_view(window).tempo, "96.5 BPM")

    assert document.project.bpm == 96.5 and stacked(window) == count + 1
    assert window._tempo.text() == "96.5 BPM"
    document.undo()
    assert project_view(window).tempo.text() == window._tempo.text() == "120.0 BPM"


def test_a_tempo_from_the_toolbar_is_one_undo_and_the_pane_follows() -> None:
    window, _ = a_window()
    document = window.document()
    count = stacked(window)

    type_into(window._tempo, "140")

    assert document.project.bpm == 140.0 and stacked(window) == count + 1
    assert project_view(window).tempo.text() == "140.0 BPM"


@pytest.mark.parametrize(("typed", "landed"), [("5", 20.0), ("5000 BPM", 999.0)])
def test_a_tempo_out_of_range_lands_at_its_end_and_says_so(
    typed: str, landed: float
) -> None:
    """D-104: the field shows where it landed, which is how it says so."""
    window, _ = a_window()
    tempo = project_view(window).tempo
    type_into(tempo, typed)
    assert window.document().project.bpm == landed
    assert tempo.text() == f"{landed:.1f} BPM"


def test_the_same_tempo_typed_again_is_no_edit() -> None:
    window, _ = a_window()
    count = stacked(window)
    type_into(project_view(window).tempo, "120")
    assert stacked(window) == count
    assert project_view(window).tempo.text() == "120.0 BPM"


def test_the_signature_from_the_pane_is_one_undo_each_and_the_toolbar_follows() -> None:
    window, _ = a_window()
    document, view = window.document(), project_view(window)
    count = stacked(window)

    type_into(view.beats, "7")
    view.note.activated.emit(view.note.findText("8"))

    assert document.project.time_signature == (7, 8)
    assert stacked(window) == count + 2
    assert window._signature_chip.text() == "7/8"
    document.undo()
    assert document.project.time_signature == (7, 4)
    assert (view.beats.text(), view.note.currentText()) == ("7", "4")


def test_choosing_the_note_already_set_is_no_edit() -> None:
    window, _ = a_window()
    view = project_view(window)
    count = stacked(window)
    view.note.activated.emit(view.note.findText("4"))
    assert stacked(window) == count


def test_the_signatures_beats_stop_at_one_and_thirty_two() -> None:
    window, _ = a_window()
    type_into(project_view(window).beats, "40")
    assert window.document().project.time_signature == (32, 4)
    type_into(project_view(window).beats, "0")
    assert window.document().project.time_signature == (1, 4)


def test_the_note_offers_only_note_values() -> None:
    """D-104: 1, 2, 4, 8 or 16."""
    window, _ = a_window()
    note = project_view(window).note
    assert [note.itemText(i) for i in range(note.count())] == ["1", "2", "4", "8", "16"]


def test_the_toolbars_signature_menu_offers_the_common_ones() -> None:
    window, _ = a_window()
    document = window.document()
    menu = window.signature_menu()
    texts = [action.text() for action in menu.actions()]
    assert texts == ["{}/{}".format(*signature) for signature in COMMON_SIGNATURES]
    assert [a.text() for a in menu.actions() if a.isChecked()] == ["4/4"]
    count = stacked(window)

    [six_eight] = [a for a in menu.actions() if a.text() == "6/8"]
    six_eight.trigger()

    assert document.project.time_signature == (6, 8) and stacked(window) == count + 1
    view = project_view(window)
    assert (view.beats.text(), view.note.currentText()) == ("6", "8")


def test_a_tempo_change_moves_the_grid_and_no_clip() -> None:
    """D-52: the material stays where it is in time; the bars move over it."""
    window, grid = a_window()
    document = window.document()
    clip = grid[0][2]
    before = (clip.start, to_bar_beat(clip.start, 120.0, (4, 4)))

    type_into(project_view(window).tempo, "90")

    assert clip.start == before[0]
    assert to_bar_beat(clip.start, document.project.bpm, (4, 4)) != before[1]


def test_the_engines_fields_are_drawn_dead_and_name_m4() -> None:
    window, _ = a_window()
    view = project_view(window)
    for field in (view.hrtf, view.rolloff, view.master, view.limiter):
        assert not field.isEnabled()
        assert "M4" in field.toolTip()
    project = window.document().project
    assert view.hrtf.currentText() == project.hrtf.id
    assert view.limiter.isChecked() == project.master.limiter_on


def test_the_toolbars_tempo_and_signature_stay_out_of_the_focus_chain() -> None:
    """As the snap chip does, or the window opens with a ring around one."""
    window, _ = a_window()
    assert window._tempo.focusPolicy() is Qt.FocusPolicy.ClickFocus
    assert window._signature_chip.focusPolicy() is Qt.FocusPolicy.NoFocus


# --------------------------------------------------------------------------- #
# collapsing
# --------------------------------------------------------------------------- #


def test_collapsing_gives_the_room_to_the_pool_and_opening_takes_it_back() -> None:
    window, _ = a_window()
    window.resize(1500, 950)
    QApplication.processEvents()
    pane = window.parameters()
    splitter = pane.parentWidget()
    assert isinstance(splitter, QSplitter)
    pool, open_height = splitter.sizes()
    assert "▾" in pane.header().text()

    QTest.mouseClick(pane.header(), Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert pane.collapsed() and "▸" in pane.header().text()
    assert splitter.sizes()[1] <= pane.header().sizeHint().height()
    assert splitter.sizes()[0] > pool

    QTest.mouseClick(pane.header(), Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert not pane.collapsed()
    assert splitter.sizes()[1] == open_height
