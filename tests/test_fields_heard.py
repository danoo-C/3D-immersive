"""The pane's spatial fields, heard (M4 phase 7): a window playing through a
synthetic head, a value typed into the pane, and the blocks after it
listened to. Marked gui.

The head is `test_spatial`'s: a source to the right is louder on the right.
Its bank is prepared as the window prepares SADIE's, on a worker, with the
direction index at test size.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from PySide6.QtCore import QEventLoop, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from hearing import Tape
from immersive.app import build_application
from immersive.audio.device import Output
from immersive.audio.engine import POSITION, RING
from immersive.audio.hrtf import lookup
from immersive.audio.limiter import CEILING_DB
from immersive.audio.player import Player
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.media import Decoded
from immersive.core.io.peaks import build
from immersive.core.media_store import Prepared
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Pairing,
    Placement,
    Position,
    new_channel,
)
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import hrtf, theme
from immersive.ui.main_window import MainWindow, Unsaved
from immersive.ui.parameters.views import MODES, ChannelView, ProjectView
from standin import Backend, Stream
from test_dragging_sources import H, W, move, per_metre, press, release
from test_parameters import type_into
from test_spatial import head

pytestmark = pytest.mark.gui

BLOCK = 256
FRAMES = 4 * SAMPLE_RATE
Audio = npt.NDArray[np.float32]


@pytest.fixture(autouse=True)
def _application(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    build_application([])
    monkeypatch.setattr(lookup, "CELLS", 16)
    monkeypatch.setattr(lookup, "SAMPLES", 2)
    monkeypatch.setattr(hrtf, "builtin", lambda set_id: head())
    yield


def until(condition: object, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():  # type: ignore[operator]
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        assert time.monotonic() < deadline, "never happened"


@pytest.fixture
def window() -> Iterator[MainWindow]:
    """A window with an output and the synthetic head's bank prepared."""
    made = MainWindow(player=Player(Backend(), Output(None, BLOCK)))
    made._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    made.resize(1500, 950)
    made.show()
    made.prepare_hrtf()
    until(lambda: made.bank() is not None)
    yield made
    made.stop_work()
    made._hrtf._pool.waitForDone(20_000)
    made._player.close()  # type: ignore[union-attr]
    made.deleteLater()


def with_channel(
    window: MainWindow,
    value: float | tuple[float, float],
    *,
    sides: int = 1,
    where: Position | None = None,
    bypass: bool = False,
) -> Channel:
    """A channel playing a sample that holds `value` throughout, or a value
    for each side."""
    document = window.document()
    project = document.project
    n = len(project.media_pool)
    media = MediaFile(
        f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", SAMPLE_RATE, sides, FRAMES
    )
    audio = np.zeros((FRAMES, sides), dtype=np.float32)
    audio[:] = value
    window.store().keep(
        media.id,
        Prepared(Path(f"/{n}.wav"), Decoded(audio, SAMPLE_RATE), "", build(audio)),
    )
    document.push(AddMedia(project, [media]))
    document.push(AddChannel(project, new_channel(project, theme.active().channels)))
    channel = project.channels[-1]
    document.push(SetAttribute(channel, "position", where or Position(0.0, 1.0, 0.0)))
    if bypass:
        document.push(SetAttribute(channel, "hrtf_bypass", True))
    document.push(
        DropClips(project, channel, [Clip(f"k-0000000{n}", media.id, 0, 0, FRAMES)])
    )
    return channel


def stream(window: MainWindow) -> Stream:
    player = window._player
    assert player is not None
    [only] = player._backend.streams
    return only


def playing(window: MainWindow) -> Tape:
    window.play_pause()
    tape = Tape(stream(window))
    tape.play(4)
    return tape


def channel_view(window: MainWindow, channel: Channel) -> ChannelView:
    window.document().selection.select(Kind.CHANNELS, [channel])
    view = window.parameters().view()
    assert isinstance(view, ChannelView)
    return view


def project_view(window: MainWindow) -> ProjectView:
    window.document().selection.clear()
    view = window.parameters().view()
    assert isinstance(view, ProjectView)
    return view


def level(block: Audio) -> tuple[float, float]:
    """Each side's mean magnitude."""
    return float(np.abs(block[:, 0]).mean()), float(np.abs(block[:, 1]).mean())


# --------------------------------------------------------------------------- #


def test_a_position_typed_is_heard_from_there_from_the_next_block(
    window: MainWindow,
) -> None:
    channel = with_channel(window, 0.1)
    tape = playing(window)
    type_into(channel_view(window, channel).position[0], "1")
    tape.play(4)

    ahead_l, ahead_r = level(tape.heard(3, 1))
    moving_l, moving_r = level(tape.heard(4, 1))
    right_l, right_r = level(tape.heard(7, 1))
    assert ahead_l == pytest.approx(ahead_r, rel=1e-4), "straight ahead, even"
    assert moving_r > moving_l, "on its way from the next block"
    assert right_r > 1.5 * right_l, "and heard from the right"


def test_a_linked_right_side_typed_and_then_one_point_are_heard(
    window: MainWindow,
) -> None:
    """A stem with only its right side sounding, in a new channel's linked
    pair ahead: its right side typed to the right is heard there, since a
    pair is two sources, and made one point it is heard from the channel's
    position, where the typing moved the left (D-132)."""
    channel = with_channel(window, (0.0, 0.1), sides=2)
    tape = playing(window)
    view = channel_view(window, channel)
    type_into(view.right[0], "1")
    tape.play(4)
    assert channel.position.x == -1.0

    ahead_l, ahead_r = level(tape.heard(3, 1))
    right_l, right_r = level(tape.heard(7, 1))
    assert ahead_l == pytest.approx(ahead_r, rel=1e-4), "both sides ahead, even"
    assert right_r > 1.5 * right_l, "its right side heard from the right"

    view.mode.activated.emit(list(MODES).index(Pairing.POINT))
    tape.play(3)
    point_l, point_r = level(tape.heard(9, 1))
    assert point_l > 1.5 * point_r, "one point, at the left side's position"


def test_a_pan_typed_on_a_bypassed_channel_is_heard(window: MainWindow) -> None:
    channel = with_channel(window, 0.25, bypass=True)
    tape = playing(window)
    view = channel_view(window, channel)
    assert not view.pan.isHidden()
    type_into(view.pan, "-1")
    tape.play(3)
    np.testing.assert_allclose(tape.heard(3, 1), 0.25 * 0.5**0.5, rtol=1e-6)
    settled = tape.heard(5, 1)
    assert not settled[:, 1].any() and (settled[:, 0] == np.float32(0.25)).all()


def test_the_master_gain_typed_is_heard(window: MainWindow) -> None:
    with_channel(window, 0.1)
    tape = playing(window)
    type_into(project_view(window).master, "-6")
    tape.play(3)
    before, after = level(tape.heard(3, 1)), level(tape.heard(6, 1))
    for was, now in zip(before, after, strict=True):
        assert now / was == pytest.approx(10 ** (-6 / 20), rel=1e-4)


def test_the_rolloff_typed_is_heard(window: MainWindow) -> None:
    """At 2 m, rolloff 1 is half the level and rolloff 2 a quarter: a snapshot
    rebuilt, since rolloff reshapes what a block does."""
    with_channel(window, 0.1, where=Position(0.0, 2.0, 0.0))
    tape = playing(window)
    type_into(project_view(window).rolloff, "2")
    tape.play(3)
    before, after = level(tape.heard(3, 1)), level(tape.heard(6, 1))
    for was, now in zip(before, after, strict=True):
        assert now / was == pytest.approx(0.5, rel=1e-3)


def test_the_limiter_switched_off_is_heard(window: MainWindow) -> None:
    with_channel(window, 1.5, sides=2, bypass=True)
    tape = playing(window)
    ceiling = 10 ** (CEILING_DB / 20)
    assert float(np.abs(tape.heard(2, 2)).max()) <= ceiling
    project_view(window).limiter.click()
    assert not window.document().project.master.limiter_on
    tape.play(3)
    assert (tape.heard(6, 1) == np.float32(1.5)).all(), "past full scale, untouched"


def test_level_as_mixed_switched_off_is_heard(window: MainWindow) -> None:
    """Half a metre ahead: level as mixed plays it as at a metre; off, nearer
    is louder, by D-21's 6.02 dB for half the distance (D-131)."""
    with_channel(window, 0.1, where=Position(0.0, 0.5, 0.0))
    tape = playing(window)
    project_view(window).keep_level.click()
    assert not window.document().project.distance.keep_level
    tape.play(3)
    before, after = level(tape.heard(3, 1)), level(tape.heard(6, 1))
    for was, now in zip(before, after, strict=True):
        assert 20 * np.log10(now / was) == pytest.approx(6.02, abs=0.05)


# --------------------------------------------------------------------------- #
# dragged in the views, heard (M5 phase 2, D-144)
# --------------------------------------------------------------------------- #


def test_the_panes_fields_follow_the_drag(window: MainWindow) -> None:
    placed = with_channel(window, 0.25, where=Position(0.0, 1.0, 0.0))
    placed.placement = Placement()  # one point: the pane shows Position X
    window.document().selection.select(Kind.CHANNELS, [placed])
    top, _ = window.spatial_views()
    top.resize(W, H)
    per = per_metre(top)
    [icon] = [icon for icon in top.icons() if icon.channel is placed]

    start = press(top, icon.centre)
    move(top, start + QPoint(40, 0))

    view = window.parameters().view()
    assert isinstance(view, ChannelView)
    assert view.position[0].value() == pytest.approx(40 / per, abs=1e-3)
    assert placed.position.x == 0.0, "the pane shows it; the model has not moved"
    release(top, start + QPoint(40, 0))


def test_a_dragged_source_is_heard_moving_before_the_release(
    window: MainWindow,
) -> None:
    """While the transport plays, each movement reaches the engine at the
    next block, and there is no edit until the release."""
    placed = with_channel(window, 0.25, where=Position(0.0, 1.0, 0.0))
    placed.placement = Placement()
    tape = playing(window)
    top, _ = window.spatial_views()
    top.resize(W, H)
    per = per_metre(top)
    [icon] = [icon for icon in top.icons() if icon.channel is placed]
    edits = window.document().can_undo

    start = press(top, icon.centre)
    move(top, start + QPoint(60, 0))
    tape.play(2)

    engine = window._player.engine  # type: ignore[union-attr]
    index = window.document().project.channels.index(placed)
    heard = engine._current.positions[index, 0]
    assert heard[0] == pytest.approx(60 / per, abs=1e-3), "heard where it is dragged"
    assert placed.position.x == 0.0
    assert window.document().can_undo == edits, "no edit yet"

    sent = engine.sent()
    release(top, start + QPoint(60, 0))
    kinds = [float(engine._ring[n % RING, 0]) for n in range(sent, engine.sent())]
    tape.play(1)
    assert placed.position.x == pytest.approx(60 / per, abs=1e-3)
    assert POSITION not in kinds, (
        "the release sends no position: the engine is already there, and the "
        "old position is never sent back on the way"
    )


def test_a_dragged_source_dropped_by_esc_is_heard_where_it_was(
    window: MainWindow,
) -> None:
    placed = with_channel(window, 0.25, where=Position(0.0, 1.0, 0.0))
    placed.placement = Placement()
    tape = playing(window)
    top, _ = window.spatial_views()
    top.resize(W, H)
    [icon] = [icon for icon in top.icons() if icon.channel is placed]
    engine = window._player.engine  # type: ignore[union-attr]
    index = window.document().project.channels.index(placed)

    start = press(top, icon.centre)
    move(top, start + QPoint(60, 0))
    tape.play(2)
    assert engine._current.positions[index, 0, 0] > 0.5, "heard dragged"
    QTest.keyClick(top, Qt.Key.Key_Escape)
    release(top, start + QPoint(60, 0))
    tape.play(2)

    assert list(engine._current.positions[index, 0]) == [0.0, 1.0, 0.0]
    assert placed.position == Position(0.0, 1.0, 0.0)
