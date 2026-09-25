"""Selecting in the window: clicks on clips, the band, headers, the pool, and
the keys that act on the selection. Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QAction, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips
from immersive.core.model import Clip, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.main_window import MainWindow
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import TOP
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.timeline.panel import TimelinePanel

pytestmark = pytest.mark.gui

#: 480 samples a pixel: a second is 100 px.
SCALE = 480.0
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10 * SAMPLE_RATE)
NONE = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def arrange(document: Document, lanes: int = 3) -> list[list[Clip]]:
    """`lanes` channels, each with clips a second long at 0, 2 and 4 s."""
    document.push(AddMedia(document.project, [MEDIA]))
    grid = []
    for lane in range(lanes):
        project = document.project
        document.push(
            AddChannel(project, new_channel(project, theme.active().channels))
        )
        clips = [
            Clip(f"k-000{lane}{n}000", MEDIA.id, n * 2 * SAMPLE_RATE, 0, SAMPLE_RATE)
            for n in range(3)
        ]
        document.push(
            DropClips(document.project, document.project.channels[lane], clips)
        )
        grid.append(clips)
    return grid


def paneled(lanes: int = 3) -> tuple[TimelinePanel, list[list[Clip]]]:
    document = Document()
    grid = arrange(document, lanes)
    panel = TimelinePanel(document, TimeAxis(SCALE))
    panel.resize(1200, 400)
    panel.set_playhead(10**9)
    panel.show()
    QApplication.processEvents()
    return panel, grid


def at(clip_lane: int, seconds: float) -> QPointF:
    """A point inside lane `clip_lane`, `seconds` into the timeline."""
    return QPointF(seconds * SAMPLE_RATE / SCALE, clip_lane * LANE_HEIGHT + 30)


def mouse(
    panel: TimelinePanel,
    kind: QEvent.Type,
    point: QPointF,
    modifiers: Qt.KeyboardModifier = NONE,
) -> None:
    left = Qt.MouseButton.LeftButton
    viewport = panel.view.viewport()
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            kind,
            point,
            viewport.mapToGlobal(point),
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseButtonRelease else left,
            modifiers,
        ),
    )


def click(
    panel: TimelinePanel, point: QPointF, modifiers: Qt.KeyboardModifier = NONE
) -> None:
    mouse(panel, QEvent.Type.MouseButtonPress, point, modifiers)
    mouse(panel, QEvent.Type.MouseButtonRelease, point, modifiers)


def selected(panel: TimelinePanel) -> list[Clip]:
    return panel._document.selection.clips()


# --------------------------------------------------------------------------- #
# clicking clips
# --------------------------------------------------------------------------- #


def test_a_click_selects_a_clip_alone() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    click(panel, at(1, 2.5))

    assert selected(panel) == [grid[1][1]]


def test_ctrl_click_toggles_a_clip_in_and_out() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    click(panel, at(2, 4.5), CTRL)
    assert selected(panel) == [grid[0][0], grid[2][2]]

    click(panel, at(0, 0.5), CTRL)
    assert selected(panel) == [grid[2][2]]


def test_shift_click_selects_the_range_from_the_anchor_replacing_the_rest() -> None:
    panel, grid = paneled()
    click(panel, at(2, 0.5))  # something that will be replaced
    click(panel, at(0, 2.5), CTRL)  # the anchor, added: lane 0, 2 s
    assert len(selected(panel)) == 2
    click(panel, at(1, 4.5), SHIFT)

    assert selected(panel) == [grid[0][1], grid[0][2], grid[1][1], grid[1][2]]


def test_ctrl_shift_click_adds_the_range() -> None:
    panel, grid = paneled()
    click(panel, at(2, 0.5))
    click(panel, at(0, 2.5), CTRL)  # anchor, added
    click(panel, at(0, 4.5), CTRL | SHIFT)

    assert selected(panel) == [grid[2][0], grid[0][1], grid[0][2]]


def test_a_press_on_a_selected_clip_waits_for_the_release() -> None:
    """Phase 5 drags every selected clip from a press on any of them, so the
    press must not narrow the selection; a release that never moved does."""
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    click(panel, at(1, 0.5), CTRL)
    both = [grid[0][0], grid[1][0]]

    mouse(panel, QEvent.Type.MouseButtonPress, at(0, 0.5))
    assert selected(panel) == both
    mouse(panel, QEvent.Type.MouseMove, at(0, 0.9))  # a drag
    mouse(panel, QEvent.Type.MouseButtonRelease, at(0, 0.9))
    assert selected(panel) == both, "a drag leaves them all selected"

    click(panel, at(0, 0.5))
    assert selected(panel) == [grid[0][0]]


def test_a_click_on_empty_lane_space_clears_and_ctrl_keeps() -> None:
    panel, _ = paneled()
    click(panel, at(0, 0.5))
    click(panel, at(0, 1.5), CTRL)  # between clips
    assert len(selected(panel)) == 1

    click(panel, at(0, 1.5))
    assert selected(panel) == []


def test_a_selected_clip_wears_a_border_and_an_unselected_one_does_not() -> None:
    panel, _ = paneled()
    click(panel, at(0, 0.5))
    image: QImage = panel.view.viewport().grab().toImage()
    border = theme.group_color("clip", "selected.border").upper()
    y = TOP + LANE_HEIGHT // 2

    def edge(x: int, lane: int = 0) -> str:
        return image.pixelColor(x, lane * LANE_HEIGHT + y).name().upper()

    assert edge(1) == border, "selected: its left border"
    assert edge(98) == border, "and its right"
    assert edge(1, lane=1) != border, "unselected"


# --------------------------------------------------------------------------- #
# Ctrl+A, and Esc
# --------------------------------------------------------------------------- #


def test_select_all_takes_the_focused_channel_then_everything() -> None:
    panel, grid = paneled()
    click(panel, at(1, 2.5))  # lane 1 is now focused

    panel.view.select_all()
    assert selected(panel) == grid[1]
    panel.view.select_all()
    assert len(selected(panel)) == 9


def test_select_all_with_nothing_focused_takes_everything() -> None:
    panel, _ = paneled()
    panel.view.select_all()
    assert len(selected(panel)) == 9


def window_with_clips() -> tuple[MainWindow, list[list[Clip]]]:
    window = MainWindow()
    grid = arrange(window.document(), lanes=2)
    window.show()
    QApplication.processEvents()
    return window, grid


def test_edit_select_all_and_escape_in_the_window() -> None:
    window, _ = window_with_clips()
    [select_all] = [
        a for a in window.findChildren(QAction) if a.text() == "Select &All"
    ]
    assert select_all.shortcut().toString() == "Ctrl+A"

    select_all.trigger()
    assert len(window.document().selection.clips()) == 6
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.document().selection.kind is None


def test_escape_in_the_rename_field_cancels_the_rename_and_not_the_selection() -> None:
    window, grid = window_with_clips()
    window.document().selection.select(Kind.CLIPS, [grid[0][0]])
    field = window.timeline().headers.headers()[0].rename()

    QTest.keyClick(field, Qt.Key.Key_Escape)

    assert window.document().selection.clips() == [grid[0][0]]
    assert window.timeline().headers.headers()[0].renaming() is None
