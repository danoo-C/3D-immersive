"""Selecting in the window: clicks on clips, the band, headers, the pool, and
the keys that act on the selection. Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QItemSelectionModel, QPointF, Qt
from PySide6.QtGui import QAction, QImage, QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.media_store import MediaStore
from immersive.core.model import Clip, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.explorer.media_pool import ID_ROLE, MediaPool
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


def test_the_rename_field_claims_ctrl_a_before_select_all_can() -> None:
    """A shortcut fires only when nothing focused claims its key first, and
    offscreen no window is active for one to fire in - so what is held here
    is the claim: with a name being edited, Ctrl+A is the field's."""
    window, grid = window_with_clips()
    window.document().selection.select(Kind.CLIPS, [grid[0][0]])
    field = window.timeline().headers.headers()[0].rename()
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_A, CTRL)
    override.ignore()

    QApplication.sendEvent(field, override)
    QTest.keyClick(field, Qt.Key.Key_A, CTRL)

    assert override.isAccepted()
    assert field.selectedText() == field.text() != ""
    assert window.document().selection.clips() == [grid[0][0]]


# --------------------------------------------------------------------------- #
# the rubber band
# --------------------------------------------------------------------------- #


def band(
    panel: TimelinePanel,
    start: QPointF,
    end: QPointF,
    modifiers: Qt.KeyboardModifier = NONE,
    *,
    release: bool = True,
) -> None:
    mouse(panel, QEvent.Type.MouseButtonPress, start, modifiers)
    middle = (start + end) / 2
    mouse(panel, QEvent.Type.MouseMove, middle, modifiers)
    mouse(panel, QEvent.Type.MouseMove, end, modifiers)
    if release:
        mouse(panel, QEvent.Type.MouseButtonRelease, end, modifiers)


def test_a_band_across_two_lanes_selects_what_it_touches_and_nothing_else() -> None:
    panel, grid = paneled()
    # From empty space before lane 0's 2 s clip, into lane 1's 2 s clip.
    band(panel, at(0, 1.5), at(1, 2.2))

    assert selected(panel) == [grid[0][1], grid[1][1]]
    assert panel.view.band() is None, "gone after the release"


def test_a_band_that_touches_nothing_clears() -> None:
    panel, _ = paneled()
    click(panel, at(0, 0.5))
    band(panel, at(0, 1.1), at(1, 1.9))
    assert selected(panel) == []


def test_ctrl_band_adds_to_what_was_selected() -> None:
    panel, grid = paneled()
    click(panel, at(2, 4.5))
    band(panel, at(0, 1.5), at(1, 2.2), CTRL)

    assert selected(panel) == [grid[2][2], grid[0][1], grid[1][1]]


def test_the_band_is_drawn_while_it_is_dragged() -> None:
    panel, _ = paneled()
    band(panel, at(0, 1.2), at(2, 1.8), release=False)

    drawn = panel.view.band()
    assert drawn is not None and drawn.width() > 50
    image = panel.view.viewport().grab().toImage()
    outline = theme.group_color("timeline", "band").upper()
    x = round(drawn.left())
    assert outline in {
        image.pixelColor(x, y).name().upper()
        for y in range(LANE_HEIGHT, 2 * LANE_HEIGHT)
    }
    mouse(panel, QEvent.Type.MouseButtonRelease, at(2, 1.8))


def test_a_drag_from_a_clip_is_not_a_band() -> None:
    """Phase 5 moves clips from a drag that starts on one."""
    panel, grid = paneled()
    band(panel, at(0, 0.5), at(1, 2.5))
    assert panel.view.band() is None
    assert selected(panel) == [grid[0][0]]


# --------------------------------------------------------------------------- #
# channels
# --------------------------------------------------------------------------- #


def header_click(
    panel: TimelinePanel, index: int, modifiers: Qt.KeyboardModifier = NONE
) -> None:
    header = panel.headers.headers()[index]
    point = QPointF(60, 12)  # on the name, which leaves clicks to the header
    left = Qt.MouseButton.LeftButton
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            header,
            QMouseEvent(
                kind,
                point,
                header.mapToGlobal(point),
                left,
                left
                if kind is QEvent.Type.MouseButtonPress
                else Qt.MouseButton.NoButton,
                modifiers,
            ),
        )


def channels(panel: TimelinePanel) -> list[int]:
    project = panel._document.project
    return [project.channels.index(c) for c in panel._document.selection.channels()]


def test_a_header_click_selects_its_channel_as_a_clip_click_would() -> None:
    panel, _ = paneled(lanes=4)
    header_click(panel, 1)
    assert channels(panel) == [1]
    header_click(panel, 3, CTRL)
    assert channels(panel) == [1, 3]
    header_click(panel, 1, CTRL)
    assert channels(panel) == [3]
    header_click(panel, 0)
    header_click(panel, 3, CTRL)
    header_click(panel, 2, SHIFT)
    assert channels(panel) == [2, 3], "Shift replaces, from the last one clicked"
    header_click(panel, 0, CTRL | SHIFT)
    assert channels(panel) == [2, 3, 0, 1], "Ctrl+Shift adds the range"


def test_selecting_a_channel_clears_the_clips_and_the_reverse() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    header_click(panel, 2)
    assert selected(panel) == [] and channels(panel) == [2]

    click(panel, at(1, 2.5))
    assert channels(panel) == [] and selected(panel) == [grid[1][1]]
    assert panel.headers.headers()[2].property("selected") is False


def test_a_header_dragged_is_reordered_and_not_selected() -> None:
    panel, _ = paneled()
    header = panel.headers.headers()[0]
    left = Qt.MouseButton.LeftButton
    grabbed = QPointF(60, 12)
    for kind, point, held in (
        (QEvent.Type.MouseButtonPress, grabbed, left),
        (QEvent.Type.MouseMove, grabbed + QPointF(0, 70), left),
        (QEvent.Type.MouseButtonRelease, grabbed, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(
            header,
            QMouseEvent(
                kind,
                point,
                header.mapToGlobal(point),
                Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
                held,
                NONE,
            ),
        )
    assert panel._document.project.channels[1] is header.channel
    assert channels(panel) == []


def test_a_selected_header_wears_a_bar_as_well_as_a_colour() -> None:
    panel, _ = paneled()
    header_click(panel, 1)
    selected_header, other = panel.headers.headers()[1], panel.headers.headers()[0]
    marker = theme.group_color("channel", "selected.marker").upper()

    assert selected_header.property("selected") is True
    assert selected_header.grab().toImage().pixelColor(1, 30).name().upper() == marker
    assert other.grab().toImage().pixelColor(1, 30).name().upper() != marker


# --------------------------------------------------------------------------- #
# B
# --------------------------------------------------------------------------- #


def test_b_bypasses_every_selected_channel_as_one_edit() -> None:
    window, _ = window_with_clips()
    document = window.document()
    first, second = document.project.channels
    [bypass] = [
        a for a in window.findChildren(QAction) if a.text().startswith("Toggle HRTF")
    ]
    assert not bypass.isEnabled(), "nothing selected, nothing to toggle"
    assert "Select a channel" in bypass.toolTip()

    document.push(SetAttribute(second, "hrtf_bypass", True))
    document.selection.select(Kind.CHANNELS, [first, second])
    assert bypass.isEnabled() and "M3" not in bypass.toolTip()

    bypass.trigger()
    assert (first.hrtf_bypass, second.hrtf_bypass) == (True, True), "any off: all on"
    bypass.trigger()
    assert (first.hrtf_bypass, second.hrtf_bypass) == (False, False), "all on: all off"
    document.undo()
    assert (first.hrtf_bypass, second.hrtf_bypass) == (True, True), "one edit"

    document.selection.select(Kind.CLIPS, [first.clips[0]])
    assert not bypass.isEnabled()


# --------------------------------------------------------------------------- #
# the pool's rows
# --------------------------------------------------------------------------- #


def pooled() -> tuple[MediaPool, TimelinePanel, list[list[Clip]]]:
    panel, grid = paneled()
    pool = MediaPool(panel._document, MediaStore())
    pool.resize(300, 300)
    pool.show()
    return pool, panel, grid


def pool_selected(pool: MediaPool) -> set[str]:
    model = pool.tree.selectionModel()
    return {index.data(ID_ROLE) for index in model.selectedRows(0)}


def pick_row(pool: MediaPool) -> None:
    [row] = [
        pool.proxy.index(r, 0)
        for r in range(pool.proxy.rowCount())
        if pool.proxy.index(r, 0).data(ID_ROLE) == MEDIA.id
    ]
    pool.tree.selectionModel().select(
        row,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )


def test_a_pool_row_is_the_media_selection_and_clears_the_clips() -> None:
    pool, panel, _ = pooled()
    click(panel, at(0, 0.5))

    pick_row(pool)

    selection = panel._document.selection
    assert selection.kind is Kind.MEDIA
    assert selection.media() == panel._document.project.media_pool
    assert selected(panel) == []


def test_a_clip_clicked_clears_the_pools_row() -> None:
    pool, panel, _ = pooled()
    pick_row(pool)
    assert pool_selected(pool) == {MEDIA.id}

    click(panel, at(0, 0.5))

    assert pool_selected(pool) == set()


def test_the_pool_keeps_its_row_selected_across_a_rebuild() -> None:
    pool, panel, _ = pooled()
    pick_row(pool)
    document = panel._document

    document.push(
        AddChannel(document.project, new_channel(document.project, ["#123456"]))
    )

    assert pool_selected(pool) == {MEDIA.id}
    assert document.selection.kind is Kind.MEDIA


def test_a_media_selection_made_elsewhere_shows_in_the_pool() -> None:
    pool, panel, _ = pooled()
    document = panel._document
    document.selection.select(Kind.MEDIA, document.project.media_pool)
    assert pool_selected(pool) == {MEDIA.id}
