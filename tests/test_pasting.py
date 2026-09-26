"""Cut, copy and paste in the window (F-50, D-99, D-100). Marked gui.

The rules - what a paste lands on, the channels it makes, the ids it mints -
are `core`'s and tested in test_clipboard.py. What is held here is that the
window's three actions reach them with the right selection, channel and
playhead, and are enabled exactly when they can act.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips
from immersive.core.model import Clip, MediaFile, new_channel, validate
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.main_window import MainWindow, Unsaved

pytestmark = pytest.mark.gui

SECOND = SAMPLE_RATE
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10 * SECOND)
CTRL = Qt.KeyboardModifier.ControlModifier
CUT, COPY, PASTE = "Cu&t", "&Copy", "&Paste"


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def arrange(document: Document, lanes: int) -> list[list[Clip]]:
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


def window_with_clips(lanes: int = 3) -> tuple[MainWindow, list[list[Clip]]]:
    window = MainWindow()
    grid = arrange(window.document(), lanes)
    window.show()
    QApplication.processEvents()
    return window, grid


def action(window: MainWindow, text: str) -> QAction:
    [found] = [a for a in window.findChildren(QAction) if a.text() == text]
    return found


def spans_of(window: MainWindow, lane: int) -> list[tuple[int, int]]:
    return [(c.start, c.end) for c in window.document().project.channels[lane].clips]


def focus(window: MainWindow, lane: int) -> None:
    """What clicking a channel's header or one of its clips does."""
    window.timeline().view.focus(window.document().project.channels[lane])


def stacked(window: MainWindow) -> int:
    return len(window.document()._stack)


# --------------------------------------------------------------------------- #
# the three verbs
# --------------------------------------------------------------------------- #


def test_the_keys_are_the_keyboard_tables() -> None:
    window, _ = window_with_clips()
    assert [
        action(window, text).shortcut().toString() for text in (CUT, COPY, PASTE)
    ] == [
        "Ctrl+X",
        "Ctrl+C",
        "Ctrl+V",
    ]


def test_the_spelled_out_keys_are_what_the_standard_keys_would_have_been() -> None:
    """Why swapping "Ctrl+X" for `StandardKey.Cut` changes nothing here: an
    action's `setShortcut` takes a standard key's first binding, and for all
    three that is the table's key. They are spelled out for the table's
    sake (D-68), not to get another key."""
    window, _ = window_with_clips()
    for text, standard in (
        (CUT, QKeySequence.StandardKey.Cut),
        (COPY, QKeySequence.StandardKey.Copy),
        (PASTE, QKeySequence.StandardKey.Paste),
    ):
        assert action(window, text).shortcut() == QKeySequence(standard)


def test_a_paste_lands_at_the_playhead_on_the_focused_channel() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0], grid[0][1]])
    action(window, COPY).trigger()
    focus(window, 2)
    window.timeline().set_playhead(7 * SECOND)
    lane_0 = copy.deepcopy(document.project.channels[0])

    action(window, PASTE).trigger()

    assert spans_of(window, 2) == [
        (0, SECOND),
        (2 * SECOND, 3 * SECOND),
        (4 * SECOND, 5 * SECOND),
        (7 * SECOND, 8 * SECOND),
        (9 * SECOND, 10 * SECOND),
    ], "the two clips, keeping the second between them"
    assert document.project.channels[0] == lane_0, "the originals untouched"
    pasted = document.project.channels[2].clips[3:]
    assert document.selection.clips() == pasted
    assert {clip.id for clip in pasted}.isdisjoint({grid[0][0].id, grid[0][1].id})
    assert window.timeline().playhead() == 7 * SECOND, "the playhead stays"


def test_cut_is_one_command_and_a_paste_brings_the_clips_back() -> None:
    window, grid = window_with_clips()
    document = window.document()
    before = copy.deepcopy(document.project)
    document.selection.select(Kind.CLIPS, [grid[0][1], grid[1][1]])
    count = stacked(window)

    action(window, CUT).trigger()

    assert (
        spans_of(window, 0)
        == spans_of(window, 1)
        == [
            (0, SECOND),
            (4 * SECOND, 5 * SECOND),
        ]
    )
    assert stacked(window) == count + 1
    assert document.selection.kind is None

    focus(window, 0)
    window.timeline().set_playhead(6 * SECOND)
    action(window, PASTE).trigger()
    assert (
        spans_of(window, 0)[-1]
        == spans_of(window, 1)[-1]
        == (
            6 * SECOND,
            7 * SECOND,
        )
    )

    document.undo()
    document.undo()
    assert document.project == before


def test_clips_from_two_lanes_paste_down_from_the_focused_one_and_past_the_last() -> (
    None
):
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0], grid[1][0]])
    action(window, COPY).trigger()
    focus(window, 2)
    window.timeline().set_playhead(8 * SECOND)
    count = stacked(window)

    action(window, PASTE).trigger()

    assert len(document.project.channels) == 4
    assert spans_of(window, 2)[-1] == (8 * SECOND, 9 * SECOND)
    assert spans_of(window, 3) == [(8 * SECOND, 9 * SECOND)]
    assert stacked(window) == count + 1, "the channel and the clips, one edit"
    document.undo()
    assert len(document.project.channels) == 3
    assert spans_of(window, 2)[-1] == (4 * SECOND, 5 * SECOND)


def test_a_paste_over_a_clip_trims_it() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    action(window, COPY).trigger()
    focus(window, 1)
    window.timeline().set_playhead(2 * SECOND + SECOND // 2)

    action(window, PASTE).trigger()

    assert spans_of(window, 1) == [
        (0, SECOND),
        (2 * SECOND, 2 * SECOND + SECOND // 2),
        (2 * SECOND + SECOND // 2, 3 * SECOND + SECOND // 2),
        (4 * SECOND, 5 * SECOND),
    ]
    assert validate(document.project) == []


def test_with_no_channel_focused_it_lands_on_the_lane_it_came_from() -> None:
    """As after a rubber band, which focuses nothing."""
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[1][0]])
    action(window, COPY).trigger()
    window.timeline().set_playhead(6 * SECOND)

    action(window, PASTE).trigger()

    assert spans_of(window, 1)[-1] == (6 * SECOND, 7 * SECOND)
    assert spans_of(window, 0)[-1] == (4 * SECOND, 5 * SECOND)


def test_copy_is_not_an_edit() -> None:
    window, grid = window_with_clips()
    document = window.document()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    before, count = copy.deepcopy(document.project), stacked(window)

    action(window, COPY).trigger()

    assert document.project == before and stacked(window) == count
    assert document.selection.clips() == [grid[0][0]]


# --------------------------------------------------------------------------- #
# enabled exactly when they can act
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", [CUT, COPY])
def test_cut_and_copy_are_enabled_exactly_while_clips_are_selected(text: str) -> None:
    window, grid = window_with_clips()
    document = window.document()
    verb = action(window, text)

    assert not verb.isEnabled() and "Select a clip first." in verb.toolTip()
    assert "M3" not in verb.toolTip()
    document.selection.select(Kind.CHANNELS, [document.project.channels[0]])
    assert not verb.isEnabled()
    document.selection.select(Kind.MEDIA, document.project.media_pool)
    assert not verb.isEnabled()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    assert verb.isEnabled()
    assert "\n" not in verb.toolTip(), "no longer says why it is dead"


def test_paste_is_enabled_once_something_is_copied_whatever_is_selected() -> None:
    window, grid = window_with_clips()
    document = window.document()
    paste = action(window, PASTE)
    assert not paste.isEnabled() and "Cut or copy a clip first." in paste.toolTip()
    assert "M3" not in paste.toolTip()

    document.selection.select(Kind.CLIPS, [grid[0][0]])
    action(window, COPY).trigger()
    assert paste.isEnabled() and "\n" not in paste.toolTip()

    for select in (
        lambda: document.selection.select(Kind.CHANNELS, document.project.channels),
        lambda: document.selection.select(Kind.MEDIA, document.project.media_pool),
        document.selection.clear,
    ):
        select()
        assert paste.isEnabled()

    count = stacked(window)
    paste.trigger()
    assert stacked(window) == count + 1, "a paste with nothing selected is made"


def test_paste_is_disabled_once_an_undo_takes_the_copied_sample_away() -> None:
    window, grid = window_with_clips(lanes=1)
    document = window.document()
    paste = action(window, PASTE)
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    action(window, COPY).trigger()

    while document.project.media_pool:
        document.undo()

    assert not paste.isEnabled()
    assert "no longer in the pool" in paste.toolTip()
    count = stacked(window)
    window.paste_clips()
    assert stacked(window) == count

    document.redo()
    assert paste.isEnabled(), "the sample is back"


def test_new_empties_the_clipboard() -> None:
    window, grid = window_with_clips()
    window._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    window.document().selection.select(Kind.CLIPS, [grid[0][0]])
    action(window, COPY).trigger()

    assert window.new_project()

    assert not action(window, PASTE).isEnabled()
    assert not window.document().clipboard


# --------------------------------------------------------------------------- #
# the keys, where text is typed
# --------------------------------------------------------------------------- #


def claims(widget: object, key: Qt.Key) -> bool:
    override = QKeyEvent(QEvent.Type.ShortcutOverride, key, CTRL, "")
    override.ignore()
    QApplication.sendEvent(widget, override)  # type: ignore[arg-type]
    return override.isAccepted()


KEYS = [Qt.Key.Key_X, Qt.Key.Key_C, Qt.Key.Key_V]


@pytest.mark.parametrize("key", KEYS)
def test_the_rename_field_and_the_filter_keep_the_keys_for_their_text(
    key: Qt.Key,
) -> None:
    """A shortcut fires only when nothing focused claims its key first, and
    offscreen no window is active for one to fire in, so what can be held
    here is the claim, as phase 4 held Ctrl+A."""
    window, grid = window_with_clips()
    window.document().selection.select(Kind.CLIPS, [grid[0][0]])
    field = window.timeline().headers.headers()[0].rename()

    assert claims(field, key)
    assert claims(window.pool().filter, key)


@pytest.mark.parametrize("key", KEYS)
def test_the_pool_and_a_resting_gain_field_leave_the_keys_to_the_window(
    key: Qt.Key,
) -> None:
    window, _ = window_with_clips()
    gain = window.timeline().headers.headers()[0].gain
    assert gain.isReadOnly()

    assert not claims(window.pool().tree, key)
    assert not claims(gain, key)
