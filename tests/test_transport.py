"""The window as a transport (F-20, F-52; D-107 to D-110): the keys and the
buttons, the playhead drawn from the engine, the page turning, the readout,
looping, the xrun count and a device that goes - all through the stand-in
stream, asserted on what it is given. Marked gui."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile
from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt
from PySide6.QtGui import QAction, QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from immersive.app import build_application
from immersive.audio.device import Output
from immersive.audio.player import LOST, Player
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.media import Decoded
from immersive.core.io.peaks import build
from immersive.core.media_store import Prepared
from immersive.core.model import Clip, LoopRegion, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.main_window import MainWindow, Unsaved
from immersive.ui.timeline.grid import Unit
from standin import Backend, Status, Stream

pytestmark = pytest.mark.gui

BLOCK = 256
FRAMES = SAMPLE_RATE * 20
Audio = npt.NDArray[np.float32]


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def numbered(frames: int = FRAMES) -> Audio:
    """Every frame its own value, so where playback is shows in the output."""
    values = (np.arange(frames, dtype=np.float32) + 1) / (1 << 22)
    audio: Audio = np.ascontiguousarray(values[:, None], dtype=np.float32)
    audio.flags.writeable = False
    return audio


@pytest.fixture
def backend() -> Backend:
    return Backend()


@pytest.fixture
def window(backend: Backend) -> Iterator[MainWindow]:
    """A window with an output, playing one channel: a whole numbered sample
    from 0, so what the stand-in is given says where playback is."""
    made = MainWindow(player=Player(backend, Output(None, BLOCK)))
    made._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    document = made.document()
    media = MediaFile("m-00000001", "/n.wav", "n.wav", SAMPLE_RATE, 1, FRAMES)
    audio = numbered()
    made.store().keep(
        media.id,
        Prepared(Path("/n.wav"), Decoded(audio, SAMPLE_RATE), "", build(audio)),
    )
    document.push(AddMedia(document.project, [media]))
    document.push(
        AddChannel(
            document.project, new_channel(document.project, theme.active().channels)
        )
    )
    clip = Clip("k-00000001", media.id, 0, 0, FRAMES)
    document.push(DropClips(document.project, document.project.channels[0], [clip]))
    made.resize(1500, 950)
    made.show()
    QApplication.processEvents()
    yield made
    made._player.close()  # type: ignore[union-attr]
    made.deleteLater()


def action(window: MainWindow, text: str) -> QAction:
    [found] = [a for a in window.findChildren(QAction) if a.text() == text]
    return found


PLAY, STOP, START, LOOP = "&Play / Pause", "&Stop", "&Return to Start", "Toggle &Loop"


def stream(backend: Backend) -> Stream:
    [only] = backend.streams
    return only


def heard(backend: Backend, blocks: int = 1) -> Audio:
    """The left side of the next `blocks` blocks the stand-in is given."""
    return np.concatenate([stream(backend).block()[:, 0] for _ in range(blocks)])


def at(sample: int, count: int = BLOCK) -> Audio:
    return numbered()[sample : sample + count, 0]


# --------------------------------------------------------------------------- #
# the keys
# --------------------------------------------------------------------------- #


def test_the_keys_are_the_keyboard_tables(window: MainWindow) -> None:
    keys = [
        action(window, text).shortcut().toString() for text in (PLAY, STOP, START, LOOP)
    ]
    assert keys == ["Space", "Esc", "Return", "L"]


def test_space_plays_from_the_playhead_and_pauses_where_it_is(
    window: MainWindow, backend: Backend
) -> None:
    window.seek(10_000)
    action(window, PLAY).trigger()

    assert np.array_equal(heard(backend), at(10_000))
    assert np.array_equal(heard(backend), at(10_000 + BLOCK))
    assert window.playing()

    action(window, PLAY).trigger()
    assert not heard(backend).any() and not window.playing()
    window.tick()
    assert window.timeline().playhead() == 10_000 + 2 * BLOCK, "paused where it was"


def test_stop_goes_back_to_where_playback_started(
    window: MainWindow, backend: Backend
) -> None:
    window.seek(10_000)
    action(window, PLAY).trigger()
    heard(backend, 3)

    action(window, STOP).trigger()

    assert window.timeline().playhead() == 10_000 and not window.playing()
    assert not heard(backend).any()
    window.tick()
    assert window.timeline().playhead() == 10_000
    action(window, PLAY).trigger()
    assert np.array_equal(heard(backend), at(10_000))


def test_esc_while_stopped_clears_the_selection(window: MainWindow) -> None:
    document = window.document()
    document.selection.select(Kind.CLIPS, document.project.channels[0].clips)
    action(window, STOP).trigger()
    assert document.selection.kind is None


def test_enter_returns_to_zero_playing_or_not(
    window: MainWindow, backend: Backend
) -> None:
    window.seek(10_000)
    action(window, START).trigger()
    assert window.timeline().playhead() == 0

    window.seek(10_000)
    action(window, PLAY).trigger()
    heard(backend, 2)
    action(window, START).trigger()
    assert np.array_equal(heard(backend), at(0)), "and plays on from there"
    action(window, STOP).trigger()
    assert window.timeline().playhead() == 0, "where Stop now goes back to"


def test_the_transport_keys_leave_text_being_typed_alone(window: MainWindow) -> None:
    """A line edit claims Space and L as text; a field that commits or
    cancels also claims Enter and Esc, which a line edit leaves to the
    window."""
    rename = window.timeline().headers.headers()[0].rename()
    gain = window.timeline().headers.headers()[0].gain
    gain.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    gain.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert not gain.isReadOnly(), "open for typing"
    for field in (rename, gain):
        for key, text in (
            (Qt.Key.Key_Space, " "),
            (Qt.Key.Key_L, "l"),
            (Qt.Key.Key_Return, "\r"),
            (Qt.Key.Key_Escape, ""),
        ):
            assert claims(field, key, text), (type(field).__name__, key)


def claims(widget: QWidget, key: Qt.Key, text: str = "") -> bool:
    override = QKeyEvent(
        QEvent.Type.ShortcutOverride, key, Qt.KeyboardModifier.NoModifier, text
    )
    override.ignore()
    QApplication.sendEvent(widget, override)
    return override.isAccepted()


def test_esc_during_a_drag_is_the_drags(window: MainWindow) -> None:
    view = window.timeline().view
    assert not claims(view, Qt.Key.Key_Escape), "Stop's, with no drag"
    clip = window.document().project.channels[0].clips[0]
    window.document().selection.select(Kind.CLIPS, [clip])
    for kind, held in (
        (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseMove, Qt.MouseButton.LeftButton),
    ):
        point = QPointF(300 if kind is QEvent.Type.MouseMove else 200, 30)
        QApplication.sendEvent(
            view.viewport(),
            QMouseEvent(
                kind,
                point,
                view.viewport().mapToGlobal(point),
                Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else held,
                held,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    assert view.dragging() and claims(view, Qt.Key.Key_Escape)


# --------------------------------------------------------------------------- #
# the playhead
# --------------------------------------------------------------------------- #


def test_the_drawn_playhead_is_where_the_engine_last_said(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend, 4)
    window.tick()
    assert window.timeline().playhead() == 4 * BLOCK
    assert window.timeline().view._playhead == 4 * BLOCK


def test_a_seek_is_not_undone_by_a_tick_before_the_engine_has_it(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend, 4)
    window.seek(100_000)
    window.tick()
    assert window.timeline().playhead() == 100_000, "not the engine's old place"
    heard(backend)
    window.tick()
    assert window.timeline().playhead() == 100_000 + BLOCK


def test_clicking_the_ruler_during_playback_seeks_there(
    window: MainWindow, backend: Backend
) -> None:
    window.document().project.snap.enabled = False
    action(window, PLAY).trigger()
    heard(backend)
    ruler = window.timeline().ruler
    x = 400
    for kind, held in (
        (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(
            ruler,
            QMouseEvent(
                kind,
                QPointF(x, 5),
                ruler.mapToGlobal(QPointF(x, 5)),
                Qt.MouseButton.LeftButton,
                held,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    target = round(window.timeline().axis.sample_at(x))
    assert np.array_equal(heard(backend), at(target))


def test_the_page_turns_when_the_playhead_leaves_the_view(
    window: MainWindow, backend: Backend
) -> None:
    axis = window.timeline().axis
    first, last = axis.visible()
    window.seek(round(last) + 10_000)
    action(window, PLAY).trigger()
    heard(backend)
    window.tick()
    first, last = axis.visible()
    playhead = window.timeline().playhead()
    assert first <= playhead < last
    assert axis.x_of(playhead) == pytest.approx(axis.width / 10, abs=2)


def test_the_page_stays_put_while_stopped(window: MainWindow) -> None:
    axis = window.timeline().axis
    before = axis.offset
    window.seek(round(axis.visible()[1]) + 10_000)
    window.tick()
    assert axis.offset == before


# --------------------------------------------------------------------------- #
# the readout
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("typed", "sample"), [("3.1.000", 2 * 96_000), ("0:01.5", 72_000)]
)
def test_a_position_typed_in_the_readout_moves_the_playhead(
    window: MainWindow, backend: Backend, typed: str, sample: int
) -> None:
    readout = window._position
    readout.committed.emit(readout._format.parse(typed))
    assert window.timeline().playhead() == sample
    action(window, PLAY).trigger()
    assert np.array_equal(heard(backend), at(sample))


def test_the_readout_shows_the_playhead_in_the_rulers_unit(
    window: MainWindow, backend: Backend
) -> None:
    window.seek(96_000)
    assert window._position.text() == "2.1.000"
    window.set_ruler_unit(Unit.TIME)
    assert window._position.text() == "0:02.000"
    action(window, PLAY).trigger()
    heard(backend)
    window.tick()
    assert window._position.text() == "0:02.005"


# --------------------------------------------------------------------------- #
# looping
# --------------------------------------------------------------------------- #


def test_loop_needs_a_region_and_says_so(window: MainWindow) -> None:
    loop = action(window, LOOP)
    assert not loop.isEnabled() and "Draw a loop region" in loop.toolTip()
    document = window.document()
    document.push(SetAttribute(document.project, "loop", LoopRegion(1_000, 5_000)))
    assert loop.isEnabled() and "\n" not in loop.toolTip()
    assert not loop.isChecked(), "a region does not start looping by itself"


def test_with_looping_on_playback_goes_round_the_region(
    window: MainWindow, backend: Backend
) -> None:
    document = window.document()
    document.push(SetAttribute(document.project, "loop", LoopRegion(10_000, 10_300)))
    action(window, LOOP).trigger()
    window.seek(10_000)
    action(window, PLAY).trigger()
    got = heard(backend, 6)
    assert np.array_equal(got, np.tile(at(10_000, 300), 6)[: got.shape[0]])


def test_a_region_drawn_in_the_ruler_turns_looping_on(window: MainWindow) -> None:
    window.timeline()._draw_loop(1_000, 5_000)
    assert action(window, LOOP).isChecked()
    assert window.timeline().ruler._looping


def test_undo_of_the_region_turns_looping_off(window: MainWindow) -> None:
    window.timeline()._draw_loop(1_000, 5_000)
    window.document().undo()
    loop = action(window, LOOP)
    assert not loop.isChecked() and not loop.isEnabled()


def test_a_project_opens_with_looping_off(window: MainWindow) -> None:
    window.timeline()._draw_loop(1_000, 5_000)
    window.new_project()
    assert not action(window, LOOP).isChecked()


# --------------------------------------------------------------------------- #
# what else is heard
# --------------------------------------------------------------------------- #


def test_an_edit_during_playback_is_heard_at_the_next_block(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend)
    document = window.document()
    document.push(SetAttribute(document.project.channels[0], "mute", True))
    heard(backend)  # the ramp
    assert not heard(backend).any()


def test_a_double_click_during_playback_is_heard_over_it(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend)
    window.audition_media("m-00000001")
    got = heard(backend)
    assert np.allclose(got, at(BLOCK) + at(0)), "the arrangement and the sample"
    assert len(backend.streams) == 1


# --------------------------------------------------------------------------- #
# xruns, and a device that goes
# --------------------------------------------------------------------------- #


def test_the_xrun_count_is_quiet_at_none_and_an_error_after_one(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend)
    window.tick()
    assert window._xruns.text() == "xruns 0"
    assert (
        QColor(theme.color("text.disabled")).name()
        in window._xruns.styleSheet().lower()
    )

    stream(backend).block(Status(output_underflow=True))
    window.tick()

    assert window._xruns.text() == "xruns 1"
    assert QColor(theme.color("error")).name() in window._xruns.styleSheet().lower()


def test_a_device_lost_stops_holds_the_playhead_and_posts_one_notice(
    window: MainWindow, backend: Backend
) -> None:
    action(window, PLAY).trigger()
    heard(backend, 3)
    window.tick()
    stream(backend).lose()

    window.tick()
    window.tick()

    assert not window.playing()
    assert window.timeline().playhead() == 3 * BLOCK
    [notice] = window.notices().newest_first()
    assert notice.message == LOST


# --------------------------------------------------------------------------- #
# nothing says M3
# --------------------------------------------------------------------------- #


def test_no_tooltip_in_the_window_names_m3(window: MainWindow) -> None:
    tips = [a.toolTip() for a in window.findChildren(QAction)]
    tips += [w.toolTip() for w in window.findChildren(QWidget)]
    assert not [tip for tip in tips if "M3" in tip]


def test_without_an_output_the_transport_says_why(tmp_path: Path) -> None:
    bare = MainWindow(player=None, unavailable="PortAudio is not installed")
    for text in (PLAY, STOP, START, LOOP):
        found = action(bare, text)
        assert not found.isEnabled()
        assert "Cannot be heard: PortAudio is not installed" in found.toolTip()
    bare.deleteLater()


def test_a_project_opened_from_a_file_with_a_region_opens_not_looping(
    window: MainWindow, tmp_path: Path
) -> None:
    window.timeline()._draw_loop(1_000, 5_000)
    assert action(window, LOOP).isChecked()
    window.document().save_as(tmp_path / "a.3dim")

    assert window.open_project(tmp_path / "a.3dim")

    assert window.document().project.loop == LoopRegion(1_000, 5_000)
    assert not action(window, LOOP).isChecked() and action(window, LOOP).isEnabled()


def test_a_project_opened_from_disk_plays_once_its_samples_have_loaded(
    backend: Backend, tmp_path: Path
) -> None:
    """Opening places the clips before the samples are decoded; the feed is
    told again when they are."""
    wav = tmp_path / "n.wav"
    soundfile.write(wav, numbered(SAMPLE_RATE)[:, 0], SAMPLE_RATE, subtype="FLOAT")
    made = MainWindow(player=Player(backend, Output(None, BLOCK)))
    made._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    made.import_paths([wav])
    finish(made)
    document = made.document()
    media = document.project.media_pool[0]
    document.push(
        AddChannel(
            document.project, new_channel(document.project, theme.active().channels)
        )
    )
    document.push(
        DropClips(
            document.project,
            document.project.channels[0],
            [Clip("k-00000001", media.id, 0, 0, media.frames)],
        )
    )
    document.save_as(tmp_path / "a.3dim")
    made._player.close()  # type: ignore[union-attr]
    made.deleteLater()

    # A window that has never decoded it, as after a restart.
    fresh = Backend()
    opened = MainWindow(player=Player(fresh, Output(None, BLOCK)))
    opened.open_project(tmp_path / "a.3dim")
    finish(opened)
    action(opened, PLAY).trigger()

    assert np.array_equal(heard(fresh), numbered(SAMPLE_RATE)[:BLOCK, 0])
    opened._player.close()  # type: ignore[union-attr]
    opened.deleteLater()


def finish(window: MainWindow, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while window.importing():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError("the samples did not finish loading")
    QApplication.processEvents()
