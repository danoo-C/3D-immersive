"""The meters in the window: the master's in the status bar, each channel's
in its header, fed by the window's tick (F-54, F-60, D-117). Marked gui."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.audio.device import Output
from immersive.audio.player import Player
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.media import Decoded
from immersive.core.io.peaks import build
from immersive.core.media_store import Prepared
from immersive.core.model import Clip, MediaFile, new_channel
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.main_window import MainWindow, Unsaved
from immersive.ui.metering import FLOOR, to_db
from immersive.ui.notices import Severity
from immersive.ui.timeline.headers import ChannelHeader
from standin import Backend, Stream

pytestmark = pytest.mark.gui

BLOCK = 256
FRAMES = SAMPLE_RATE * 10


class Clock:
    def __init__(self) -> None:
        self.now = 50.0

    def __call__(self) -> float:
        return self.now


def steady(value: float) -> Decoded:
    audio = np.full((FRAMES, 1), value, dtype=np.float32)
    audio.flags.writeable = False
    return Decoded(audio, SAMPLE_RATE)


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def arranged(*values: float) -> MainWindow:
    """A window with an output and a channel per value, each playing a whole
    sample that holds that value."""
    window = MainWindow(player=Player(Backend(), Output(None, BLOCK)))
    window._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    document = window.document()
    for n, value in enumerate(values):
        media = MediaFile(
            f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", SAMPLE_RATE, 1, FRAMES
        )
        decoded = steady(value)
        window.store().keep(
            media.id, Prepared(Path(f"/{n}.wav"), decoded, "", build(decoded.audio))
        )
        document.push(AddMedia(document.project, [media]))
        channel = new_channel(document.project, theme.active().channels)
        document.push(AddChannel(document.project, channel))
        clip = Clip(f"k-0000000{n}", media.id, 0, 0, FRAMES)
        document.push(DropClips(document.project, channel, [clip]))
    window.resize(1500, 950)
    window.show()
    QApplication.processEvents()
    return window


def stream(window: MainWindow) -> Stream:
    player = window._player
    assert player is not None
    [only] = player._backend.streams
    return only


def played(window: MainWindow, blocks: int = 4) -> None:
    """Play `blocks` blocks through the stand-in, then the window's frame."""
    if not window.playing():
        window.play_pause()
    for _ in range(blocks):
        stream(window).block()
    window.tick()


def headers(window: MainWindow) -> list[ChannelHeader]:
    return window.timeline().headers.headers()


def test_the_master_meter_sits_between_the_xruns_and_the_notice_count() -> None:
    window = arranged()
    window.notices().add(Severity.INFO, "shown, so the count is")
    QApplication.processEvents()
    assert window._notice_count.isVisible()
    xruns = window._xruns.geometry().x()
    meter = window.meter().geometry().x()
    notices = window._notice_count.geometry().x()
    assert xruns < meter < notices
    window.deleteLater()


def test_a_known_level_reaches_the_master_and_its_channel() -> None:
    window = arranged(0.25)
    played(window)
    assert window.meter().ballistics.levels == pytest.approx([to_db(0.25)] * 2)
    [header] = headers(window)
    assert header.meter.ballistics.levels == pytest.approx([to_db(0.25)] * 2)
    window.deleteLater()


def test_a_channel_meter_is_after_its_gain_and_a_muted_one_shows_nothing() -> None:
    window = arranged(0.25, 0.5)
    document = window.document()
    first, second = document.project.channels
    document.push(SetAttribute(first, "gain_db", -6.0))
    document.push(SetAttribute(second, "mute", True))
    played(window, blocks=8)  # past the gain's ramp

    loud, quiet = headers(window)
    gained = float(np.float32(0.25) * np.float32(10 ** (-6.0 / 20)))
    assert loud.meter.ballistics.levels[0] == pytest.approx(to_db(gained), abs=0.01)
    assert quiet.meter.ballistics.levels == [FLOOR, FLOOR]
    window.deleteLater()


def test_past_full_scale_lights_only_the_masters_clip_light() -> None:
    window = arranged(1.5)
    played(window)
    [header] = headers(window)
    assert window.meter().clipped()
    assert header.meter.light() is None and not header.meter.clipped()
    light = window.meter().light()
    assert light is not None
    window.meter().clear()
    assert not window.meter().clipped()
    window.deleteLater()


def test_stopped_every_meter_falls() -> None:
    window = arranged(0.25)
    played(window)
    [header] = headers(window)
    clock = Clock()
    for meter in (window.meter(), header.meter):
        meter.ballistics._clock = clock
        meter.ballistics._last = clock.now

    window.stop()
    clock.now += 1.0
    stream(window).block()
    window.tick()

    for meter in (window.meter(), header.meter):
        assert meter.ballistics.levels[0] == pytest.approx(to_db(0.25) - 24.0, abs=0.01)
    window.deleteLater()


def test_every_header_is_fed_every_frame_played_or_not() -> None:
    """So a meter never freezes at a level: a header the playing snapshot
    does not hold - a channel just added - is fed silence, and falls."""
    window = arranged(0.25)
    played(window)
    document = window.document()
    document.push(
        AddChannel(
            document.project, new_channel(document.project, theme.active().channels)
        )
    )
    fed: list[str] = []
    for header in headers(window):

        def spy(
            left: float,
            right: float,
            header: ChannelHeader = header,
            original: Callable[[float, float], None] = header.meter.feed,
        ) -> None:
            fed.append(header.channel.id)
            original(left, right)

        header.meter.feed = spy  # type: ignore[method-assign]

    window.tick()

    assert sorted(fed) == sorted(channel.id for channel in document.project.channels)
    window.deleteLater()
