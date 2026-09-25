"""Editing clips in the window: dragging them, trimming them, the keys that
split, duplicate and delete, and choosing the snap. Marked gui."""

from __future__ import annotations

import copy
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips
from immersive.core.model import Clip, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import TOP, ClipItem
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.timeline.panel import TimelinePanel

pytestmark = pytest.mark.gui

#: 480 samples a pixel: a second is 100 px, and at 120 BPM a sixteenth,
#: 6 000 samples, is 12.5 px.
SCALE = 480.0
SECOND = SAMPLE_RATE
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10 * SECOND)
NONE = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier


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
            Clip(f"k-000{lane}{n}000", MEDIA.id, n * 2 * SECOND, 0, SECOND)
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


def at(lane: int, seconds: float) -> QPointF:
    """A point in the middle of lane `lane`, `seconds` into the timeline."""
    return QPointF(seconds * SECOND / SCALE, lane * LANE_HEIGHT + 30)


def mouse(
    panel: TimelinePanel,
    kind: QEvent.Type,
    point: QPointF,
    modifiers: Qt.KeyboardModifier = NONE,
    *,
    held: bool = True,
) -> None:
    left = Qt.MouseButton.LeftButton
    viewport = panel.view.viewport()
    pressed = (
        left
        if held and kind is not QEvent.Type.MouseButtonRelease
        else Qt.MouseButton.NoButton
    )
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            kind,
            point,
            viewport.mapToGlobal(point),
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
            pressed,
            modifiers,
        ),
    )


def drag(
    panel: TimelinePanel,
    start: QPointF,
    end: QPointF,
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
    panel: TimelinePanel, point: QPointF, modifiers: Qt.KeyboardModifier = NONE
) -> None:
    mouse(panel, QEvent.Type.MouseButtonPress, point, modifiers)
    mouse(panel, QEvent.Type.MouseButtonRelease, point, modifiers)


def where(panel: TimelinePanel, clip: Clip) -> tuple[int, int, int]:
    """The lane `clip` is on, its start and its end."""
    for lane, channel in enumerate(panel._document.project.channels):
        if any(held is clip for held in channel.clips):
            return lane, clip.start, clip.end
    raise AssertionError(f"{clip.id} is not in the project")


def edits(panel: TimelinePanel) -> int:
    """How many edits the document's stack holds."""
    return len(panel._document._stack)


def item_of(panel: TimelinePanel, clip: Clip) -> ClipItem:
    [item] = [item for item in panel.view.clip_items() if item.clip is clip]
    return item


def drawn(panel: TimelinePanel, clip: Clip) -> tuple[int, int, int]:
    """The lane `clip`'s item is drawn in, and the samples it spans."""
    item = item_of(panel, clip)
    start = round(item.pos().x() * SCALE)
    return item.lane, start, start + round(item.boundingRect().width() * SCALE)


# --------------------------------------------------------------------------- #
# moving
# --------------------------------------------------------------------------- #


def test_a_drag_moves_every_selected_clip_across_lanes_as_one_command() -> None:
    panel, grid = paneled()
    document = panel._document
    for clip in (grid[0][0], grid[0][1], grid[1][0]):
        document.selection.add(Kind.CLIPS, [clip])
    before, pushed = copy.deepcopy(document.project), edits(panel)

    drag(panel, at(0, 2.5), at(1, 3.5))  # a lane down, a second on

    assert where(panel, grid[0][0]) == (1, SECOND, 2 * SECOND)
    assert where(panel, grid[0][1]) == (1, 3 * SECOND, 4 * SECOND)
    assert where(panel, grid[1][0]) == (2, SECOND, 2 * SECOND)
    assert document.selection.clips() == [grid[0][0], grid[0][1], grid[1][0]]
    assert edits(panel) == pushed + 1, "one command, however far it was dragged"
    document.undo()
    assert document.project == before


def test_a_drag_onto_a_neighbour_trims_it() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))

    drag(panel, at(0, 0.5), at(0, 2.0))  # 0-1 s to 1.5-2.5 s, over 2-3 s

    assert where(panel, grid[0][0]) == (0, 1.5 * SECOND, 2.5 * SECOND)
    assert where(panel, grid[0][1]) == (0, 2.5 * SECOND, 3 * SECOND)


def test_a_drag_is_drawn_where_the_release_will_put_it() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    before = copy.deepcopy(panel._document.project)

    drag(panel, at(0, 0.5), at(2, 1.2), release=False)

    assert panel.view.dragging()
    assert panel._document.project == before, "nothing is edited until the release"
    shown = drawn(panel, grid[0][0])
    lanes = panel._document.project.channels
    assert item_of(panel, grid[0][0]).colour == lanes[2].color != lanes[0].color
    mouse(panel, QEvent.Type.MouseButtonRelease, at(2, 1.2))
    assert where(panel, grid[0][0]) == shown
    assert not panel.view.dragging()


def test_a_drag_snaps_and_alt_does_not() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    drag(panel, at(0, 0.5), at(0, 1.03))  # 0.53 s: 25 440 snaps to 24 000
    assert grid[0][0].start == 24_000

    drag(panel, at(0, 0.8), at(0, 1.33), ALT)
    assert grid[0][0].start == 24_000 + round(0.53 * SECOND)


def test_a_drag_that_snaps_back_to_where_it_began_pushes_nothing() -> None:
    panel, _ = paneled()
    click(panel, at(0, 0.5))
    pushed = edits(panel)
    drag(panel, at(0, 0.5), at(0, 0.5) + QPointF(3, 3))
    assert edits(panel) == pushed


def test_escape_during_a_drag_puts_everything_back_and_edits_nothing() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    before, pushed = copy.deepcopy(panel._document.project), edits(panel)

    drag(panel, at(0, 0.5), at(1, 1.5), release=False)
    QTest.keyClick(panel.view, Qt.Key.Key_Escape)
    mouse(panel, QEvent.Type.MouseButtonRelease, at(1, 1.5))

    assert panel._document.project == before
    assert edits(panel) == pushed
    assert drawn(panel, grid[0][0]) == (0, 0, SECOND)
    assert panel._document.selection.clips() == [grid[0][0]], "Esc kept the selection"


def test_a_clip_ctrl_pressed_out_of_the_selection_drags_nothing() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))
    click(panel, at(1, 0.5), CTRL)
    pushed = edits(panel)

    drag(panel, at(0, 0.5), at(0, 1.5), CTRL)  # toggles it out, then moves

    assert panel._document.selection.clips() == [grid[1][0]]
    assert where(panel, grid[1][0]) == (1, 0, SECOND), "what is still selected stays"
    assert edits(panel) == pushed


# --------------------------------------------------------------------------- #
# trimming
# --------------------------------------------------------------------------- #


def edge(lane: int, seconds: float, inside: float) -> QPointF:
    """A point `inside` pixels in from an edge at `seconds`: positive to the
    right of it, negative to the left."""
    return QPointF(seconds * SECOND / SCALE + inside, lane * LANE_HEIGHT + TOP + 20)


def test_dragging_an_end_trims_the_clip_and_stops_at_its_neighbour() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))

    drag(panel, edge(0, 1, -2), edge(0, 5, -2))

    assert where(panel, grid[0][0]) == (0, 0, 2 * SECOND), "stopped at 2 s"
    assert grid[0][0].offset == 0


def test_dragging_a_start_trims_the_clip_and_keeps_its_samples_in_place() -> None:
    panel, grid = paneled()
    click(panel, at(1, 2.5))

    drag(panel, edge(1, 2, 2), edge(1, 2.5, 2))

    clip = grid[1][1]
    assert where(panel, clip) == (1, 2.5 * SECOND, 3 * SECOND)
    assert clip.offset == 0.5 * SECOND, "what is left plays what it played"


def test_a_trim_is_drawn_while_it_is_dragged() -> None:
    panel, grid = paneled()
    click(panel, at(0, 0.5))

    drag(panel, edge(0, 1, -2), edge(0, 1.5, -2), release=False)

    assert drawn(panel, grid[0][0]) == (0, 0, 1.5 * SECOND)
    assert grid[0][0].end == SECOND


def test_the_pointer_shows_an_edge_before_the_press() -> None:
    panel, _ = paneled()
    viewport = panel.view.viewport()

    mouse(panel, QEvent.Type.MouseMove, edge(0, 1, -2), held=False)
    assert viewport.cursor().shape() is Qt.CursorShape.SizeHorCursor
    mouse(panel, QEvent.Type.MouseMove, at(0, 0.5), held=False)
    assert viewport.cursor().shape() is Qt.CursorShape.ArrowCursor
