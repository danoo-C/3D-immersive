"""The ruler's three gestures (D-109): drag the playhead, draw a loop region,
click to seek - each snapping by the project's setting, and the region drawn
(D-108). Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips
from immersive.core.model import Clip, LoopRegion, MediaFile, SnapSetting, new_channel
from immersive.core.time import SAMPLE_RATE, Division
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.panel import TimelinePanel

pytestmark = pytest.mark.gui

#: 480 samples a pixel: a second is 100 px, and at 120 BPM a quarter note -
#: the grid below - is 24 000 samples, 50 px.
SCALE = 480.0
QUARTER = 24_000
NONE = Qt.KeyboardModifier.NoModifier
ALT = Qt.KeyboardModifier.AltModifier


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def paneled(scale: float = SCALE) -> tuple[TimelinePanel, list[int], list[int]]:
    """A panel snapping to quarter notes, with what it seeks and how many
    loops it says were drawn."""
    document = Document()
    document.project.snap = SnapSetting(division=Division.QUARTER)
    panel = TimelinePanel(document, TimeAxis(scale))
    panel.resize(1200, 300)
    panel.show()
    QApplication.processEvents()
    sought: list[int] = []
    drawn: list[int] = []
    panel.sought.connect(sought.append)
    panel.loop_drawn.connect(lambda: drawn.append(1))
    return panel, sought, drawn


def mouse(
    panel: TimelinePanel,
    kind: QEvent.Type,
    x: float,
    modifiers: Qt.KeyboardModifier = NONE,
) -> None:
    point = QPointF(x, 10)
    left = Qt.MouseButton.LeftButton
    QApplication.sendEvent(
        panel.ruler,
        QMouseEvent(
            kind,
            point,
            panel.ruler.mapToGlobal(point),
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseButtonRelease else left,
            modifiers,
        ),
    )


def drag(
    panel: TimelinePanel,
    start: float,
    end: float,
    modifiers: Qt.KeyboardModifier = NONE,
    *,
    release: bool = True,
) -> None:
    mouse(panel, QEvent.Type.MouseButtonPress, start, modifiers)
    mouse(panel, QEvent.Type.MouseMove, (start + end) / 2, modifiers)
    mouse(panel, QEvent.Type.MouseMove, end, modifiers)
    if release:
        mouse(panel, QEvent.Type.MouseButtonRelease, end, modifiers)


def click(
    panel: TimelinePanel, x: float, modifiers: Qt.KeyboardModifier = NONE
) -> None:
    mouse(panel, QEvent.Type.MouseButtonPress, x, modifiers)
    mouse(panel, QEvent.Type.MouseButtonRelease, x, modifiers)


def edits(panel: TimelinePanel) -> int:
    return len(panel._document._stack)


# --------------------------------------------------------------------------- #
# the three gestures
# --------------------------------------------------------------------------- #


def test_a_click_seeks_to_the_nearest_grid_line() -> None:
    panel, sought, drawn = paneled()
    click(panel, 162)  # 77 760 samples: nearest quarter is 72 000
    assert sought == [3 * QUARTER] and panel.playhead() == 3 * QUARTER
    assert drawn == [] and panel._document.project.loop is None


def test_alt_places_exactly() -> None:
    panel, sought, _ = paneled()
    click(panel, 162, ALT)
    assert sought == [162 * 480]


def test_dragging_the_playhead_moves_it_and_draws_no_loop() -> None:
    panel, sought, drawn = paneled()
    panel.set_playhead(2 * QUARTER)  # x = 100
    count = edits(panel)

    drag(panel, 102, 251)  # taken within 5 px of it

    assert panel.playhead() == 5 * QUARTER
    assert sought[-1] == 5 * QUARTER and len(sought) >= 2, "as it goes"
    assert panel._document.project.loop is None and drawn == []
    assert edits(panel) == count, "moving the playhead is not an edit"


def test_drawing_a_loop_moves_no_playhead_and_is_one_undo() -> None:
    panel, sought, drawn = paneled()
    panel.set_playhead(QUARTER)
    count = edits(panel)

    drag(panel, 148, 402)

    assert panel._document.project.loop == LoopRegion(3 * QUARTER, 8 * QUARTER)
    assert panel.playhead() == QUARTER and sought == []
    assert drawn == [1] and edits(panel) == count + 1
    panel._document.undo()
    assert panel._document.project.loop is None


def test_a_loop_drawn_right_to_left_is_the_same_loop() -> None:
    panel, _, _ = paneled()
    drag(panel, 402, 148)
    assert panel._document.project.loop == LoopRegion(3 * QUARTER, 8 * QUARTER)


def test_a_region_is_shown_dashed_while_it_is_drawn() -> None:
    panel, _, _ = paneled()
    drag(panel, 148, 402, release=False)
    assert panel.ruler.drawing() == (3 * QUARTER, 8 * QUARTER)
    assert panel._document.project.loop is None, "nothing until the release"
    mouse(panel, QEvent.Type.MouseButtonRelease, 402)
    assert panel.ruler.drawing() is None


def test_a_loop_too_short_is_not_drawn() -> None:
    """At a sample a pixel and with Alt, a drag of 30 px is 30 samples, under
    D-108's 64."""
    panel, _, drawn = paneled(scale=1.0)
    count = edits(panel)
    drag(panel, 100, 130, ALT)
    assert panel._document.project.loop is None and drawn == []
    assert edits(panel) == count


def test_the_loop_snaps_to_clip_edges_too() -> None:
    """An edge 1 000 samples past a grid line is nearer than the line."""
    panel, _, _ = paneled()
    document = panel._document
    media = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, SAMPLE_RATE * 60)
    document.push(AddMedia(document.project, [media]))
    document.push(
        AddChannel(
            document.project, new_channel(document.project, theme.active().channels)
        )
    )
    clip = Clip("k-00000001", media.id, 2 * QUARTER + 1_000, 0, 5 * QUARTER)
    document.push(DropClips(document.project, document.project.channels[0], [clip]))

    drag(panel, 104, 358)

    assert document.project.loop == LoopRegion(clip.start, clip.end)


def test_the_pointer_shows_the_playhead_can_be_taken() -> None:
    panel, _, _ = paneled()
    panel.set_playhead(2 * QUARTER)
    mouse(panel, QEvent.Type.MouseMove, 103)
    assert panel.ruler.cursor().shape() is Qt.CursorShape.SizeHorCursor
    mouse(panel, QEvent.Type.MouseMove, 300)
    assert panel.ruler.cursor().shape() is not Qt.CursorShape.SizeHorCursor


# --------------------------------------------------------------------------- #
# drawn
# --------------------------------------------------------------------------- #


def colour_in(panel: TimelinePanel, widget: str, x: int, y: int) -> QColor:
    target = panel.ruler if widget == "ruler" else panel.view.viewport()
    return QColor(target.grab().toImage().pixelColor(x, y))


def test_the_region_is_filled_while_looping_and_outlined_while_not() -> None:
    panel, _, _ = paneled()
    panel._document.project.loop = LoopRegion(2 * QUARTER, 6 * QUARTER)  # 100-300 px
    panel.ruler.update()
    background = QColor(theme.group_color("ruler", "background"))
    region = QColor(theme.group_color("timeline", "loop.region"))

    assert colour_in(panel, "ruler", 200, 3) == background, "off: inside is bare"
    assert colour_in(panel, "ruler", 100, 3) == region, "off: an outline"

    panel.set_looping(True)
    inside = colour_in(panel, "ruler", 200, 3)
    assert inside != background and inside.red() > background.red()


def test_the_lanes_show_the_region_only_while_looping() -> None:
    panel, _, _ = paneled()
    panel._document.project.loop = LoopRegion(2 * QUARTER, 6 * QUARTER)
    panel.view.viewport().update()
    between_lines = 225
    before = colour_in(panel, "view", between_lines, 40)
    panel.set_looping(True)
    assert colour_in(panel, "view", between_lines, 40) != before
    assert colour_in(panel, "view", 362, 40) == colour_in(panel, "view", 387, 40)


def test_a_press_just_past_the_playheads_reach_draws_a_loop() -> None:
    panel, sought, _ = paneled()
    panel.set_playhead(2 * QUARTER)  # x = 100
    drag(panel, 107, 402)
    assert panel.playhead() == 2 * QUARTER and sought == []
    assert panel._document.project.loop == LoopRegion(2 * QUARTER, 8 * QUARTER)


def test_drawing_the_same_region_again_is_no_edit() -> None:
    panel, _, drawn = paneled()
    drag(panel, 148, 402)
    count = edits(panel)
    drag(panel, 152, 398)
    assert edits(panel) == count and drawn == [1, 1], "still turns looping on"


def test_the_ruler_snaps_by_the_project_not_by_a_channels_override() -> None:
    """The ruler belongs to no channel (D-109)."""
    panel, sought, _ = paneled()
    document = panel._document
    document.push(
        AddChannel(
            document.project, new_channel(document.project, theme.active().channels)
        )
    )
    document.project.channels[0].snap_override = SnapSetting(division=Division.WHOLE)
    click(panel, 162)
    assert sought == [3 * QUARTER]
