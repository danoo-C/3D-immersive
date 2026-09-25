"""Editing clips in the window: dragging them, trimming them, the keys that
split, duplicate and delete, and choosing the snap. Marked gui."""

from __future__ import annotations

import copy
import hashlib
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt
from PySide6.QtGui import QAction, QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips
from immersive.core.model import Channel, Clip, MediaFile, SnapSetting, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE, Division
from immersive.ui import theme
from immersive.ui.main_window import MainWindow
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


# --------------------------------------------------------------------------- #
# the keys
# --------------------------------------------------------------------------- #


def window_with_clips() -> tuple[MainWindow, list[list[Clip]]]:
    window = MainWindow()
    grid = arrange(window.document(), lanes=2)
    window.show()
    QApplication.processEvents()
    return window, grid


def action(window: MainWindow, text: str) -> QAction:
    [found] = [a for a in window.findChildren(QAction) if a.text() == text]
    return found


SPLIT, DUPLICATE, DELETE = "&Split at Playhead", "&Duplicate", "De&lete"


def spans_of(window: MainWindow, lane: int) -> list[tuple[int, int]]:
    return [(c.start, c.end) for c in window.document().project.channels[lane].clips]


def test_s_splits_every_selected_clip_under_the_playhead_as_one_edit() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0], grid[1][0], grid[0][1]])
    window.timeline().set_playhead(SECOND // 2)
    before, stacked = copy.deepcopy(document.project), len(document._stack)

    action(window, SPLIT).trigger()

    half = SECOND // 2
    assert spans_of(window, 0)[:3] == [
        (0, half),
        (half, SECOND),
        (2 * SECOND, 3 * SECOND),
    ]
    assert spans_of(window, 1)[:2] == [(0, half), (half, SECOND)]
    tails = [document.project.channels[n].clips[1] for n in (0, 1)]
    assert document.selection.clips() == [grid[0][0], grid[1][0], grid[0][1], *tails]
    assert len(document._stack) == stacked + 1
    document.undo()
    assert document.project == before


def test_s_with_the_playhead_outside_every_selected_clip_does_nothing() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    window.timeline().set_playhead(SECOND + 1)
    stacked = len(document._stack)
    action(window, SPLIT).trigger()
    assert len(document._stack) == stacked


def test_ctrl_d_copies_the_selection_after_itself_and_carries_the_run_on() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    duplicate = action(window, DUPLICATE)
    assert duplicate.shortcut().toString() == "Ctrl+D"

    duplicate.trigger()
    [first] = document.selection.clips()
    assert (first.start, first.end) == (SECOND, 2 * SECOND)
    duplicate.trigger()
    [second] = document.selection.clips()
    assert (second.start, second.end) == (2 * SECOND, 3 * SECOND)

    assert spans_of(window, 0) == [
        (0, SECOND),
        (SECOND, 2 * SECOND),
        (2 * SECOND, 3 * SECOND),
        (4 * SECOND, 5 * SECOND),
    ], "the second copy landed on the clip at 2 s, as a drop would"


def test_delete_removes_every_selected_clip_as_one_edit() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][1], grid[1][2]])
    before, stacked = copy.deepcopy(document.project), len(document._stack)

    action(window, DELETE).trigger()

    assert spans_of(window, 0) == [(0, SECOND), (4 * SECOND, 5 * SECOND)]
    assert spans_of(window, 1) == [(0, SECOND), (2 * SECOND, 3 * SECOND)]
    assert document.selection.kind is None
    assert len(document._stack) == stacked + 1
    document.undo()
    assert document.project == before


@pytest.mark.parametrize("text", [SPLIT, DUPLICATE, DELETE])
def test_the_clip_verbs_are_enabled_exactly_while_clips_are_selected(text: str) -> None:
    window, grid = window_with_clips()
    document = window.document()
    verb = action(window, text)

    assert not verb.isEnabled() and "Select a clip first." in verb.toolTip()
    document.selection.select(Kind.CHANNELS, [document.project.channels[0]])
    assert not verb.isEnabled()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    assert verb.isEnabled()
    assert "\n" not in verb.toolTip(), "no longer says why it is dead"


@pytest.mark.parametrize(
    ("key", "modifiers"),
    [(Qt.Key.Key_S, NONE), (Qt.Key.Key_Delete, NONE), (Qt.Key.Key_D, CTRL)],
)
def test_the_rename_field_keeps_the_verbs_keys_for_itself(
    key: Qt.Key, modifiers: Qt.KeyboardModifier
) -> None:
    """As phase 4 held `Ctrl+A`: what can be held offscreen is the claim."""
    window, grid = window_with_clips()
    window.document().selection.select(Kind.CLIPS, [grid[0][0]])
    field = window.timeline().headers.headers()[0].rename()
    override = QKeyEvent(
        QEvent.Type.ShortcutOverride, key, modifiers, "s" if key is Qt.Key.Key_S else ""
    )
    override.ignore()

    QApplication.sendEvent(field, override)

    if key is Qt.Key.Key_D:
        # Ctrl+D is not a line edit's; it reaches the window, which is right:
        # nothing is selected in a name being typed that Ctrl+D would copy.
        assert not override.isAccepted()
    else:
        assert override.isAccepted()


# --------------------------------------------------------------------------- #
# F-14: the source is never touched
# --------------------------------------------------------------------------- #


def finish(window: MainWindow, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while window.importing():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError("the import did not finish")
    QApplication.processEvents()


def test_no_sample_is_written_through_a_session_of_every_edit(tmp_path: Path) -> None:
    paths = []
    for n in range(2):
        path = tmp_path / f"s{n}.wav"
        audio = np.random.default_rng(n).uniform(-0.5, 0.5, 2 * SECOND)
        soundfile.write(path, audio.astype(np.float32), SAMPLE_RATE, subtype="FLOAT")
        paths.append(path)
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    window = MainWindow()
    window.show()
    assert window.import_paths(paths)
    finish(window)
    document = window.document()
    pool = document.project.media_pool
    for media in pool:
        document.push(
            AddChannel(document.project, new_channel(document.project, ["#123456"]))
        )
        channel = document.project.channels[-1]
        clip = Clip(
            f"k-0000000{len(document.project.channels)}", media.id, 0, 0, media.frames
        )
        document.push(DropClips(document.project, channel, [clip]))
    panel = window.timeline()
    panel.view.axis.zoom_about(0, SCALE / panel.view.axis.scale)
    assert panel.view.axis.scale == pytest.approx(SCALE)
    QApplication.processEvents()

    clips = [channel.clips[0] for channel in document.project.channels]
    document.selection.select(Kind.CLIPS, clips)
    drag(panel, at(0, 1.0), at(1, 1.5))
    drag(panel, edge(1, clips[0].end / SECOND, -2), edge(1, 1.2, -2))
    panel.set_playhead(round(0.8 * SECOND))
    for text in (SPLIT, DUPLICATE, DELETE):
        document.selection.select(
            Kind.CLIPS, [c for ch in document.project.channels for c in ch.clips]
        )
        action(window, text).trigger()
    # the import, two channels, two clips, a drag, a trim and the three verbs
    assert len(document._stack) == 10
    while document.undo():
        pass
    while document.redo():
        pass
    document.save_as(tmp_path / "session.3dim")

    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    } == hashes


# --------------------------------------------------------------------------- #
# choosing the snap
# --------------------------------------------------------------------------- #


def pick(menu_of: Callable[[], QMenu], text: str) -> None:
    """Fill a menu as opening it would, and choose `text` from it."""
    [chosen] = [a for a in menu_of().actions() if a.text().startswith(text)]
    chosen.trigger()


def checked(menu_of: Callable[[], QMenu]) -> list[str]:
    return [a.text() for a in menu_of().actions() if a.isChecked()]


def override_of(channel: Channel) -> SnapSetting | None:
    return channel.snap_override


def test_the_chip_offers_every_division_triplet_and_off() -> None:
    window, _ = window_with_clips()
    texts = [a.text() for a in window.snap_menu().actions() if a.text()]
    assert texts == ["Off", "1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "Triplet"]
    assert checked(window.snap_menu) == ["1/16"]


def test_each_choice_from_the_chip_is_one_command_and_the_chip_says_so() -> None:
    window, _ = window_with_clips()
    document = window.document()
    stacked = len(document._stack)
    chip = window.findChild(QToolButton, "SnapChip")
    assert chip is not None

    pick(window.snap_menu, "1/8")
    assert document.project.snap == SnapSetting(True, Division.EIGHTH, False)
    pick(window.snap_menu, "Triplet")
    assert chip.text() == "Snap 1/8T"
    pick(window.snap_menu, "Off")
    assert document.project.snap == SnapSetting(False, Division.EIGHTH, True)
    assert (chip.text(), checked(window.snap_menu)) == ("Snap off", ["Off", "Triplet"])
    pick(window.snap_menu, "1/4")
    assert document.project.snap == SnapSetting(True, Division.QUARTER, True)
    assert len(document._stack) == stacked + 4

    pick(window.snap_menu, "1/4")
    assert len(document._stack) == stacked + 4, "the setting it already has"
    document.undo()
    assert chip.text() == "Snap off"


def test_a_header_sets_and_clears_its_channels_override() -> None:
    window, _ = window_with_clips()
    document = window.document()
    header = window.timeline().headers.headers()[0]
    channel = header.channel
    assert checked(header.snap_menu) == ["Follow Project  (Snap 1/16)"]

    pick(header.snap_menu, "1/32")
    assert override_of(channel) == SnapSetting(True, Division.THIRTY_SECOND, False)
    assert document.project.snap == SnapSetting(), "the project's is untouched"
    assert (header.snap.text(), header.snap.property("overriding")) == ("1/32", True)
    assert checked(header.snap_menu) == ["1/32"]

    pick(header.snap_menu, "Off")
    assert override_of(channel) == SnapSetting(False, Division.THIRTY_SECOND, False)
    assert header.snap.text() == "off"

    pick(header.snap_menu, "Follow Project")
    assert override_of(channel) is None
    assert (header.snap.text(), header.snap.property("overriding")) == ("snap", False)
    document.undo()
    assert header.snap.text() == "off"


def windowed() -> tuple[MainWindow, TimelinePanel, list[list[Clip]]]:
    window, grid = window_with_clips()
    panel = window.timeline()
    panel.view.axis.zoom_about(0, SCALE / panel.view.axis.scale)
    assert panel.view.axis.scale == pytest.approx(SCALE)
    QApplication.processEvents()
    return window, panel, grid


def test_a_drag_snaps_by_what_the_chip_and_the_header_chose() -> None:
    window, panel, grid = windowed()
    clip = grid[0][0]
    window.document().selection.select(Kind.CLIPS, [clip])

    drag(panel, at(0, 0.5), at(0, 0.8))  # 0.3 s is 14 400: a sixteenth is 12 000
    assert clip.start == 12_000
    pick(window.snap_menu, "1/4")
    drag(panel, at(0, 0.75), at(0, 1.05))  # 26 400: a quarter is 24 000
    assert clip.start == 24_000
    pick(panel.headers.headers()[0].snap_menu, "Off")
    drag(panel, at(0, 1.0), at(0, 1.3))
    assert clip.start == 24_000 + 14_400, "this channel no longer snaps"


def test_both_menus_are_filled_as_they_open() -> None:
    """The tests above fill each menu by calling for it; this is what makes
    opening it do the same."""
    window, _ = window_with_clips()
    chip = window.findChild(QToolButton, "SnapChip")
    indicator = window.timeline().headers.headers()[0].snap
    for button in (chip, indicator):
        assert button is not None
        menu = button.menu()
        assert menu is not None and not menu.actions()
        menu.aboutToShow.emit()
        assert "Triplet" in [a.text() for a in menu.actions()]
