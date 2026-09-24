"""Audition: one sample, straight to the output (F-8).

Driven through a stand-in for `sounddevice` that implements only what its
documentation promises - the stream's arguments, the callback's signature,
`CallbackStop` - so nothing here needs PortAudio or a device. Whether the
real thing sounds right is a person's to say, on native Windows or Linux.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
import soundfile

import immersive
from immersive.app import build_application
from immersive.audio.audition import Audition
from immersive.audio.device import Output, load_backend
from immersive.core.time import SAMPLE_RATE
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity

BLOCK = 64


class CallbackStop(Exception):
    """sounddevice.CallbackStop's stand-in."""


class Stream:
    """sounddevice.OutputStream's stand-in: records how it was opened and lets
    a test run its callback one block at a time."""

    def __init__(self, backend: Backend, **settings: Any) -> None:
        self.settings = settings
        self.callback: Callable[..., None] = settings["callback"]
        self.finished: Callable[[], None] = settings["finished_callback"]
        self.active = False
        self.closed = False
        backend.streams.append(self)

    def start(self) -> None:
        self.active = True

    def close(self) -> None:
        self.closed = True
        self.active = False

    def block(self) -> npt.NDArray[np.float32]:
        """Run the callback once, as PortAudio would, and return what it wrote."""
        out = np.full((self.settings["blocksize"], 2), np.nan, dtype=np.float32)
        try:
            self.callback(out, self.settings["blocksize"], None, None)
        except CallbackStop:
            self.active = False
            self.finished()
        return out


class Backend:
    CallbackStop = CallbackStop

    def __init__(self, refuse: bool = False) -> None:
        self.streams: list[Stream] = []
        self.refuse = refuse

    def OutputStream(self, **settings: Any) -> Stream:
        if self.refuse:
            raise RuntimeError("Device unavailable")
        return Stream(self, **settings)


def ramp(frames: int, channels: int = 1) -> npt.NDArray[np.float32]:
    """Every frame different, so order and position are visible."""
    values = (np.arange(frames, dtype=np.float32) + 1) / (frames + 1)
    return np.ascontiguousarray(np.repeat(values[:, None], channels, axis=1))


@pytest.fixture
def backend() -> Backend:
    return Backend()


@pytest.fixture
def audition(backend: Backend) -> Audition:
    return Audition(backend, Output(device=None, block=BLOCK))


# --------------------------------------------------------------------------- #
# the stream
# --------------------------------------------------------------------------- #


def test_the_stream_is_opened_at_48k_and_nothing_else(
    backend: Backend, audition: Audition
) -> None:
    audition.play(ramp(10))

    [stream] = backend.streams
    assert stream.settings["samplerate"] == SAMPLE_RATE
    assert stream.settings["blocksize"] == BLOCK
    assert stream.settings["channels"] == 2
    assert stream.settings["dtype"] == "float32"
    assert stream.active


def test_the_flags_reach_the_stream(backend: Backend) -> None:
    Audition(backend, Output(device="Headphones", block=1024)).play(ramp(10))

    [stream] = backend.streams
    assert (stream.settings["device"], stream.settings["blocksize"]) == (
        "Headphones",
        1024,
    )


def test_the_frames_go_out_in_order(backend: Backend, audition: Audition) -> None:
    sample = ramp(BLOCK * 3, channels=2)
    audition.play(sample)
    stream = backend.streams[0]

    written = np.concatenate([stream.block() for _ in range(3)])

    np.testing.assert_array_equal(written, sample)


def test_mono_goes_to_both_ears(backend: Backend, audition: Audition) -> None:
    sample = ramp(BLOCK)
    audition.play(sample)

    out = backend.streams[0].block()

    np.testing.assert_array_equal(out[:, 0], sample[:, 0])
    np.testing.assert_array_equal(out[:, 1], sample[:, 0])


def test_after_the_last_frame_silence_and_the_stream_stops(
    backend: Backend, audition: Audition
) -> None:
    sample = ramp(BLOCK + 10)
    audition.play(sample)
    stream = backend.streams[0]
    stream.block()

    last = stream.block()

    np.testing.assert_array_equal(last[:10, 0], sample[BLOCK:, 0])
    assert (last[10:] == 0).all(), "silence, not whatever was in the buffer"
    assert not stream.active, "and the stream stopped"


def test_a_second_sample_replaces_the_first_from_its_first_frame(
    backend: Backend, audition: Audition
) -> None:
    audition.play(ramp(BLOCK * 10))
    stream = backend.streams[0]
    stream.block()
    stream.block()
    second = ramp(BLOCK * 2, channels=2) * -1

    audition.play(second)
    out = stream.block()

    np.testing.assert_array_equal(out, second[:BLOCK])
    assert len(backend.streams) == 1, "the running stream carries it"


def test_a_sample_after_the_last_one_ended_reopens(
    backend: Backend, audition: Audition
) -> None:
    audition.play(ramp(10))
    backend.streams[0].block()

    audition.play(ramp(10))

    assert len(backend.streams) == 2
    assert backend.streams[0].closed
    assert backend.streams[1].active


def test_a_device_that_will_not_open_is_reported(backend: Backend) -> None:
    said: list[str] = []
    audition = Audition(Backend(refuse=True), Output(None, BLOCK), report=said.append)

    audition.play(ramp(10))

    assert said == ["The output device would not open (Device unavailable)"]


def test_a_device_lost_mid_sample_is_reported(backend: Backend) -> None:
    """05: the stream stops, the failure is said, and reopening is the
    person's to do - not a silent move to the laptop speakers."""
    said: list[str] = []
    audition = Audition(backend, Output(None, BLOCK), report=said.append)
    audition.play(ramp(BLOCK * 10))
    stream = backend.streams[0]
    stream.block()

    stream.finished()  # PortAudio gave up: nobody raised CallbackStop

    assert said == ["The output device stopped - double-click a sample to try again"]


def test_the_end_of_a_sample_is_not_reported_as_a_lost_device(
    backend: Backend,
) -> None:
    said: list[str] = []
    audition = Audition(backend, Output(None, BLOCK), report=said.append)
    audition.play(ramp(10))

    backend.streams[0].block()

    assert said == []


# --------------------------------------------------------------------------- #
# the machine may have no audio stack at all
# --------------------------------------------------------------------------- #


def test_loading_the_backend_never_raises() -> None:
    """On this machine it may be the module or a sentence; never an exception."""
    loaded = load_backend()

    assert isinstance(loaded, str) or hasattr(loaded, "OutputStream")
    if isinstance(loaded, str):
        assert "libportaudio2" in loaded, "and it says what to install"


def test_nothing_imports_sounddevice_at_module_level() -> None:
    """It raises OSError at import without PortAudio - no application at all,
    rather than an application that says what to install."""
    package = Path(immersive.__file__).parent
    offenders = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.split(".")[0] == "sounddevice" for name in names):
                offenders.append(str(path.relative_to(package)))

    assert offenders == []


# --------------------------------------------------------------------------- #
# in the window
# --------------------------------------------------------------------------- #


@pytest.fixture
def heard(backend: Backend) -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow(audition=Audition(backend, Output(None, BLOCK)))
    yield made
    made.deleteLater()


def imported_sample(window: MainWindow, tmp_path: Path) -> str:
    import time

    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    path = tmp_path / "kick.wav"
    soundfile.write(path, ramp(4_000), SAMPLE_RATE, subtype="FLOAT")
    window.import_paths([path])
    deadline = time.monotonic() + 20
    while window.importing() and time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return window.document().project.media_pool[0].id


@pytest.mark.gui
def test_double_clicking_a_row_plays_it(
    heard: MainWindow, backend: Backend, tmp_path: Path
) -> None:
    media_id = imported_sample(heard, tmp_path)
    pool = heard.pool()
    index = pool.proxy.index(0, 0)
    assert index.data(pool_id_role()) == media_id

    pool.tree.doubleClicked.emit(index)

    [stream] = backend.streams
    out = stream.block()
    np.testing.assert_array_equal(out[:, 0], ramp(4_000)[:BLOCK, 0])


def pool_id_role() -> int:
    from immersive.ui.explorer.media_pool import ID_ROLE

    return int(ID_ROLE)


@pytest.mark.gui
def test_a_row_says_how_to_hear_it(heard: MainWindow, tmp_path: Path) -> None:
    imported_sample(heard, tmp_path)

    tip = heard.pool().proxy.index(0, 0).data(3)  # Qt.ToolTipRole

    assert tip.endswith("Double-click to hear it")


@pytest.mark.gui
def test_without_audio_the_window_still_opens_and_says_why(tmp_path: Path) -> None:
    build_application([])
    reason = "Audio output is unavailable (PortAudio not found) - install it"
    window = MainWindow(audition=None, unavailable=reason)
    imported_sample(window, tmp_path)

    tip = window.pool().proxy.index(0, 0).data(3)
    assert tip.endswith(f"Cannot be heard: {reason}")
    assert not window.audition_media(window.document().project.media_pool[0].id)
    window.deleteLater()


@pytest.mark.gui
def test_a_problem_from_the_audio_thread_becomes_a_notice(
    heard: MainWindow, backend: Backend
) -> None:
    from PySide6.QtWidgets import QApplication

    assert heard._audition is not None
    heard._audition.report("The output device stopped")
    QApplication.processEvents()

    [notice] = heard.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert notice.message == "The output device stopped"
