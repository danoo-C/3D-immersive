"""N-1, measured (D-136), and the switch interval under load (D-137).

    python -m immersive.benchmark blocks [--block 512] [--count 3000] [--rounds 3]
    python -m immersive.benchmark contention [--seconds 8] [--rounds 3] [--one-wait]
    python -m immersive.benchmark live [--device NAME] [--block 512] [--seconds 60]
                                       [--load playing|scrolling|repainting|dragging]
    python -m immersive.benchmark views [--count 200]

**`blocks`** times the engine a block at a time, with no window and no
device. The HRTF set is the one the application ships, prepared at the
block asked for. Each arrangement is played in turn, round after round,
since timings on one machine drift from run to run. It reports the median,
the 99th percentile and the worst block, and how many blocks were over
budget, beside the machine's name. N-1 is met when 32 sources take a p99
under half the budget.

**`contention`** plays 32 sources in the application's window through a
**stand-in stream**: a thread that calls the engine's callback on a clock of
its own, as PortAudio does, and counts the blocks that were late. The UI
thread meanwhile plays (its own tick), scrolls the timeline, repaints the
whole window without pause, or drags a source round the head in the top
view as a hand does (M5 phase 5). Each load runs at CPython's 5 ms switch interval
and at D-39's 1 ms, in turn, round after round. `--one-wait` puts in the
engine's place a sleep as long as its median block: an engine that waits
for the GIL once a block, which is what D-39 assumed the engine was.

**`live`** is the count phase 11 takes on the listening machine: the same
window on the real output, chosen as the application chooses it, 32 sources
moving for a minute, and the engine's own xrun count at the end, which is
what PortAudio reported. The window is on screen, and a person may use it
meanwhile; `--load` scrolls or repaints it without one.

**`views`** times each spatial view's repaint with 32 sources placed, as
points and as linked pairs: the top, the front, the bypass strip, the 3D
view on its own tab, and the whole window beside them.

**A source is a slot**: a channel placed as a pair is two (D-132), and each
costs the FFT what a point does. Every arrangement is the finished graph.
Level as mixed is on and the limiter is on, and one bypassed stereo
channel plays beside the sources. It is not a source, because it never
enters the FFT (05, *It is cheaper*). Every source moves every block, on
an orbit of its own, and one in eight orbits inside the centre (D-130).

In the package, beside `app.py`, rather than in `tests/` or `spikes/`:
N-1 is a claim about the machine it runs on, and the listening machine has
only the application installed.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from immersive.audio.device import DEFAULT_BLOCK, Output
from immersive.audio.engine import Engine
from immersive.audio.hrtf.bank import Bank
from immersive.audio.scheduler import Snapshot, build
from immersive.core.io.loudness import measure
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    HrtfRef,
    MediaFile,
    Pairing,
    Placement,
    Position,
    Project,
)
from immersive.core.time import SAMPLE_RATE

#: N-1's line: 32 sources take a p99 under this share of the budget.
HALF: Final = 0.5

#: Blocks played before any is timed: the first blocks after an install
#: take up the snapshot, and the first of anything fills numpy's caches.
WARM: Final = 100

#: How long the sources' sample is. It repeats, so its length is only its
#: memory: 8 s of stereo float32 is 3 MB.
SAMPLE_SECONDS: Final = 8

#: Nearer than this, a source is inside the centre (the model's default
#: minimum distance, D-130), and one in eight orbits there.
CENTRE: Final = 0.1

#: How far round its orbit a source goes each block: a turn in about 8 s at
#: 512 frames. The engine looks every source up every block whether it
#: moved or not, so the speed is for the ear, not the cost.
STEP: Final = 2.0 * math.pi / 750

#: The golden angle, so no two sources start at the same place.
SPREAD: Final = math.pi * (3.0 - math.sqrt(5.0))

#: The arrangements `blocks` measures: channels, and whether each is a pair.
SHAPES: Final = ((1, False), (8, False), (16, False), (32, False), (32, True))

MEDIA_ID: Final = "m-0000be00"

#: What the UI thread does while `contention` listens: plays, scrolls the
#: timeline, repaints the whole window without pause, or drags a source.
LOADS: Final = ("playing", "scrolling", "repainting", "dragging")

#: CPython's default switch interval, and D-39's.
INTERVALS: Final = (0.005, 0.001)

#: How often the UI thread moves the sources in the window: the window's
#: own tick rate (main_window.TICK_HZ), named here to keep this module
#: clear of Qt.
MOVES_HZ: Final = 30

#: How far the timeline scrolls each 16 ms while `scrolling`: a hand on the
#: scroll bar.
SCROLL_PX: Final = 7
SCROLL_MS: Final = 16

#: How the pointer goes while `dragging`: round a circle this many metres
#: about the head in the top view, once in this many seconds, moving each
#: `DRAG_MS` - a hand on the mouse.
DRAG_REACH_M: Final = 2.0
DRAG_TURN_S: Final = 4.0
DRAG_MS: Final = 16

#: The views `views` times, in the order it prints them.
VIEWS: Final = ("top", "front", "strip", "3d", "window")


def budget(block: int) -> float:
    """How long a block of `block` frames lasts at the project rate, in
    seconds: what the device plays while the next is made."""
    return block / SAMPLE_RATE


@dataclass(frozen=True)
class Timings:
    """How long each timed block took, in seconds, and the budget it had."""

    times: npt.NDArray[np.float64]
    budget: float

    @property
    def p50(self) -> float:
        return float(np.percentile(self.times, 50))

    @property
    def p99(self) -> float:
        return float(np.percentile(self.times, 99))

    @property
    def worst(self) -> float:
        return float(self.times.max())

    @property
    def over(self) -> int:
        """How many blocks took longer than the block lasts."""
        return int(np.count_nonzero(self.times > self.budget))

    def within(self, fraction: float) -> bool:
        """Whether the 99th percentile is under `fraction` of the budget."""
        return self.p99 < fraction * self.budget


def place(index: int, block: int) -> tuple[float, float, float]:
    """Where source `index` is at block `block`, metres: an orbit of its own
    radius and height, and one source in eight inside the centre."""
    angle = index * SPREAD + block * STEP
    reach = CENTRE if index % 8 == 0 else 1.0 + 0.25 * (index % 4)
    height = 0.3 * reach * ((index % 3) - 1)
    return reach * math.sin(angle), reach * math.cos(angle), height


def sample(seconds: float = SAMPLE_SECONDS) -> Decoded:
    """Stereo noise at a mixed stem's level, with the spectra a pair's
    loudness is read from, as a decode measures them (D-133)."""
    rng = np.random.default_rng(0)
    audio = (0.05 * rng.standard_normal((round(seconds * SAMPLE_RATE), 2))).astype(
        np.float32
    )
    audio.flags.writeable = False
    spectra = measure(audio)
    return Decoded(audio, SAMPLE_RATE, spectra.fold, spectra)


def arrangement(channels: int, paired: bool, decoded: Decoded) -> Project:
    """`channels` channels playing `decoded`, each one point or a linked
    pair, and one bypassed stereo channel beside them."""
    frames = decoded.frames
    media = MediaFile(
        MEDIA_ID, "/benchmark.wav", "benchmark.wav", SAMPLE_RATE, 2, frames
    )
    mode = Pairing.LINKED if paired else Pairing.POINT

    def channel(n: int, **settings: object) -> Channel:
        return Channel(
            f"c-0000{n:04x}",
            f"Source {n + 1}",
            "#A855F7",
            clips=[Clip(f"k-0000{n:04x}", media.id, 0, 0, frames)],
            **settings,  # type: ignore[arg-type]
        )

    sources = [
        channel(n, position=Position(*place(n, 0)), placement=Placement(mode=mode))
        for n in range(channels)
    ]
    project = Project(
        media_pool=[media],
        channels=[*sources, channel(channels, hrtf_bypass=True)],
        hrtf=HrtfRef(),
    )
    project.distance.keep_level = True
    project.master.gain_db = 0.0
    project.master.limiter_on = True
    return project


class Arrangement:
    """An arrangement playing through an engine of its own, a block at a
    time, every source moved before each block."""

    def __init__(
        self, bank: Bank, channels: int, paired: bool, decoded: Decoded | None = None
    ) -> None:
        decoded = decoded if decoded is not None else sample()
        self.channels = channels
        self.paired = paired
        self.project = arrangement(channels, paired, decoded)
        self.engine = Engine(bank.block)
        self.snapshot: Snapshot = build(
            self.project, {MEDIA_ID: decoded}.get, None, bank
        )
        self.engine.install(self.snapshot)
        self.engine.set_repeat(decoded.frames, True)
        self.engine.set_playing(True)
        self._out = np.zeros((bank.block, 2), dtype=np.float32)
        self._block = 0

    @property
    def sources(self) -> int:
        """Slots in the FFT: a pair is two."""
        space = self.snapshot.space
        return space.count if space is not None else 0

    def move(self) -> None:
        """Every source to where it is this block, through the ring, as the
        UI thread sends a position; a pair's right side mirrors its left in
        X, as a new channel's does (D-134)."""
        engine = self.engine
        generation = self.snapshot.generation
        for index in range(self.channels):
            x, y, z = place(index, self._block)
            engine.send_position(generation, index, x, y, z)
            if self.paired:
                engine.send_position(generation, index, -x, y, z, 1)

    def play(self, count: int) -> list[float]:
        """Play `count` blocks, each after its sources have moved, and how
        long each took, seconds. Only `process` is timed."""
        engine, out = self.engine, self._out
        times = []
        for _ in range(count):
            self.move()
            began = time.perf_counter()
            engine.process(out)
            times.append(time.perf_counter() - began)
            self._block += 1
        return times


def blocks(bank: Bank, channels: int, paired: bool, count: int) -> Timings:
    """`count` blocks of one arrangement, timed after `WARM` untimed."""
    playing = Arrangement(bank, channels, paired)
    playing.play(WARM)
    return Timings(np.array(playing.play(count)), budget(bank.block))


# ------------------------------------------------------ the stand-in stream


class Clock:
    """A device's clock, as the stand-in stream keeps it (D-137).

    Block `n` is to start `n` blocks after the clock's origin, and is due
    one block after that: the tightest stream a device can open, so a block
    missed here is missed on any device. A late block is one miss, and the
    clock is set again from when it finished, as a device plays on after an
    underrun. Without that, one long stall would be counted again in every
    block after it.
    """

    def __init__(self, period: float, origin: float) -> None:
        self.period = period
        self._origin = origin
        self.blocks = 0
        self.missed = 0
        #: Each block's time from when it was due to start until it was
        #: done: the wait to be woken, every wait for the GIL, and the block.
        self.times: list[float] = []
        #: How late each block's callback began.
        self.woken: list[float] = []
        #: The switch interval the audio thread ran under, read by it.
        self.interval = 0.0

    def due(self) -> float:
        """When the next block is to start."""
        return self._origin + self.blocks * self.period

    def done(self, started: float, finished: float) -> bool:
        """The next block began at `started` and finished at `finished`:
        whether it was missed."""
        due = self.due()
        self.times.append(finished - due)
        self.woken.append(started - due)
        self.blocks += 1
        if finished - due <= self.period:
            return False
        self.missed += 1
        self._origin = finished - self.blocks * self.period
        return True


class Stream:
    """`sounddevice.OutputStream`'s stand-in. It calls its callback on a
    clock of its own, from a thread of its own, as PortAudio does. The
    engine meets there what it meets on a device, the waits for the GIL
    included, and nothing is played."""

    def __init__(self, status: Any = None, **settings: Any) -> None:
        self.block = int(settings["blocksize"])
        self.callback: Callable[..., None] = settings["callback"]
        #: What PortAudio says of each block. The stand-in says nothing.
        self.status = status
        self.clock = Clock(budget(self.block), 0.0)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="stand-in audio", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        """Stop after the block under way. The clock is whole once this
        returns."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _run(self) -> None:
        out = np.zeros((self.block, 2), dtype=np.float32)
        clock = self.clock = Clock(self.clock.period, time.perf_counter())
        clock.interval = sys.getswitchinterval()
        while not self._stop.is_set():
            wait = clock.due() - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            started = time.perf_counter()
            self.callback(out, self.block, None, self.status)
            clock.done(started, time.perf_counter())


class Backend:
    """The stand-in's `sounddevice`: only what the player opens a stream
    with, and every stream it opened."""

    def __init__(self, status: Any = None) -> None:
        self.streams: list[Stream] = []
        self.status = status

    def OutputStream(self, **settings: Any) -> Stream:
        stream = Stream(self.status, **settings)
        self.streams.append(stream)
        return stream


@dataclass(frozen=True)
class Lap:
    """One load at one switch interval: what the stand-in stream saw."""

    load: str
    #: The interval the audio thread read, not the one asked for.
    interval: float
    missed: int
    #: Each block from when it was due to start until it was done.
    timings: Timings


def contention(
    seconds: float,
    rounds: int,
    channels: int = 32,
    *,
    one_wait: bool = False,
    block: int = DEFAULT_BLOCK,
    loads: Sequence[str] = LOADS,
) -> list[Lap]:
    """Each load at each interval, `seconds` long, `rounds` times over, in
    turn: the window playing `channels` moving sources through a stand-in
    stream. The switch interval is put back after."""
    from immersive.app import build_application
    from immersive.audio.player import Player
    from immersive.ui.main_window import MainWindow

    build_application([])
    backend = Backend()
    player = Player(backend, Output(None, block))
    window = MainWindow(player=player)
    window.show()
    before = sys.getswitchinterval()
    engine = player.engine
    try:
        window.prepare_hrtf()
        _until(lambda: window.bank() is not None)
        bank = window.bank()
        assert bank is not None
        decoded = sample(seconds + 2.0)
        _arrange(window, channels, decoded)
        if one_wait:
            _one_wait(engine, blocks(bank, channels, False, 200).p50)
        moving = _moving(engine, channels)
        # A lap not counted first: the window's first seconds of playing a
        # project it has just built are heavier than any after, and would
        # land on whichever interval came first.
        _lap(window, player, "playing", seconds)
        laps = []
        for turn in range(rounds):
            for load in loads:
                # Each round the other interval first, so neither is always
                # the one that follows a change of load.
                for interval in INTERVALS[:: -1 if turn % 2 else 1]:
                    sys.setswitchinterval(interval)
                    _lap(window, player, load, seconds)
                    clock = backend.streams[-1].clock
                    laps.append(
                        Lap(
                            load,
                            clock.interval,
                            clock.missed,
                            Timings(np.array(clock.times), budget(block)),
                        )
                    )
        moving.stop()
        return laps
    finally:
        sys.setswitchinterval(before)
        engine.__dict__.pop("process", None)
        player.close()
        window.stop_work()
        window.deleteLater()


@dataclass(frozen=True)
class Heard:
    """What `live` counted."""

    #: The engine's own count: what the stream reported as underflows.
    xruns: int
    blocks: int


def live(
    backend: Any, output: Output, seconds: float, load: str, channels: int = 32
) -> Heard:
    """The application's window playing `channels` moving sources through
    `backend` for `seconds` under `load`, and the xruns the engine counted.
    The window is shown, for whoever is at the machine."""
    from immersive.app import build_application
    from immersive.audio.player import Player
    from immersive.ui.main_window import MainWindow

    build_application([])
    player = Player(backend, output)
    window = MainWindow(player=player)
    window.show()
    engine = player.engine
    try:
        window.prepare_hrtf()
        _until(lambda: window.bank() is not None)
        _arrange(window, channels, sample(seconds + 2.0))
        moving = _moving(engine, channels)
        _lap(window, player, load, seconds)
        moving.stop()
        return Heard(engine.xruns, engine.playhead // output.block)
    finally:
        player.close()
        window.stop_work()
        window.deleteLater()


def _lap(window: Any, player: Any, load: str, seconds: float) -> None:
    """From the start, playing under `load` for `seconds`; then the stream
    closed, so its clock is whole and the next lap opens a new one."""
    window.seek(0)
    window.play_pause()
    _load(window, load, seconds)
    window.play_pause()
    player.close()


def _until(condition: Callable[[], bool], timeout: float = 60.0) -> None:
    """Turn the event loop until `condition` holds."""
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + timeout
    while not condition():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if time.monotonic() > deadline:
            raise TimeoutError("the HRTF set was not prepared")


def _arrange(
    window: Any, channels: int, decoded: Decoded, *, paired: bool = False
) -> None:
    """The arrangement, pushed into the window's project as edits, its
    sample in the window's store as an import leaves one."""
    from immersive.core.edits import AddChannel, AddMedia
    from immersive.core.io.peaks import build as pyramid
    from immersive.core.media_store import Prepared

    arranged = arrangement(channels, paired, decoded)
    [media] = arranged.media_pool
    window.store().keep(
        media.id, Prepared(Path(media.path), decoded, "", pyramid(decoded.audio))
    )
    document = window.document()
    project = document.project
    document.push(AddMedia(project, [media]))
    for channel in arranged.channels:
        document.push(AddChannel(project, channel))


def _one_wait(engine: Engine, seconds: float) -> None:
    """Put in the engine's place a sleep as long as its block: an engine
    that waits for the GIL once a block. `contention` takes it out."""

    def process(out: npt.NDArray[np.float32]) -> None:
        time.sleep(seconds)

    engine.process = process  # type: ignore[method-assign]


def _moving(engine: Engine, channels: int) -> Any:
    """A timer on the UI thread, the ring's one producer, moving every
    source `MOVES_HZ` times a second along its orbit."""
    from PySide6.QtCore import QTimer

    per_move = round(SAMPLE_RATE / MOVES_HZ / engine.block)
    at = [0]

    def move() -> None:
        generation = engine.generation
        for index in range(channels):
            engine.send_position(generation, index, *place(index, at[0]))
        at[0] += per_move

    timer = QTimer()
    timer.setInterval(1000 // MOVES_HZ)
    timer.timeout.connect(move)
    timer.start()
    return timer


def _load(window: Any, load: str, seconds: float) -> None:
    """What the UI thread does for `seconds`."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    if load == "repainting":
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            window.repaint()
            QApplication.processEvents()
        return
    dragging = _drag(window) if load == "dragging" else None
    scrolling = None
    if load == "scrolling":
        axis = window.timeline().axis
        step = [SCROLL_PX]

        def scroll() -> None:
            # Back the other way at either end, so it never stops moving.
            was = axis.offset
            axis.scroll_by(step[0])
            if axis.offset == was:
                step[0] = -step[0]
                axis.scroll_by(step[0])

        scrolling = QTimer()
        scrolling.setInterval(SCROLL_MS)
        scrolling.timeout.connect(scroll)
        scrolling.start()
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()
    if scrolling is not None:
        scrolling.stop()
    if dragging is not None:
        dragging.stop()


class _Drag:
    """A hand dragging a source in the top view until `stop()`."""

    def __init__(self, timer: Any, release: Callable[[], None]) -> None:
        self._timer = timer
        self._release = release

    def stop(self) -> None:
        self._timer.stop()
        self._release()


def _drag(window: Any) -> _Drag:
    """Press on the second source's icon in the top view - the first is
    inside the centre - and move the pointer each `DRAG_MS` round a circle
    `DRAG_REACH_M` about the head, through the view's own mouse handling:
    `Placing`, the feed, both views and the pane."""
    from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    top, _ = window.spatial_views()
    second = window.document().project.channels[1]
    [grabbed] = [icon for icon in top.icons() if icon.channel is second]
    head = top.point_of(Position())
    reach = DRAG_REACH_M * (top.point_of(Position(1.0, 0.0, 0.0)).x() - head.x())
    left = Qt.MouseButton.LeftButton
    at = [grabbed.centre]

    def send(kind: QEvent.Type, button: Qt.MouseButton, held: Qt.MouseButton) -> None:
        event = QMouseEvent(
            kind,
            at[0],
            top.mapToGlobal(at[0]),
            button,
            held,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(top, event)

    began = time.monotonic()

    def move() -> None:
        turned = 2.0 * math.pi * (time.monotonic() - began) / DRAG_TURN_S
        at[0] = head + QPointF(reach * math.sin(turned), -reach * math.cos(turned))
        send(QEvent.Type.MouseMove, Qt.MouseButton.NoButton, left)

    send(QEvent.Type.MouseButtonPress, left, left)
    timer = QTimer()
    timer.setInterval(DRAG_MS)
    timer.timeout.connect(move)
    timer.start()
    return _Drag(
        timer,
        lambda: send(QEvent.Type.MouseButtonRelease, left, Qt.MouseButton.NoButton),
    )


@dataclass(frozen=True)
class Painted:
    """One view's repaints: how long each took, and how many paint events
    it got, which is as many as it was timed for only if it was shown."""

    times: npt.NDArray[np.float64]
    paints: int

    def at(self, fraction: float) -> float:
        return float(np.quantile(self.times, fraction))


def views(
    count: int, channels: int = 32, *, paired: bool = False
) -> dict[str, Painted]:
    """Each of `VIEWS` repainted `count` times, synchronously, in the window
    with `channels` sources placed: points, or linked pairs. The 3D view
    is timed on its own tab, since a hidden widget paints nothing."""
    from PySide6.QtWidgets import QApplication, QTabWidget

    from immersive.app import build_application
    from immersive.ui.main_window import MainWindow

    build_application([])
    window = MainWindow()
    window.show()
    try:
        _arrange(window, channels, sample(2.0), paired=paired)
        QApplication.processEvents()
        top, front = window.spatial_views()
        [workspace] = window.findChildren(QTabWidget)
        widgets = {
            "top": top,
            "front": front,
            "strip": window.bypass_strip(),
            "3d": window.view3d(),
            "window": window,
        }
        timed: dict[str, Painted] = {}
        for name in VIEWS:
            workspace.setCurrentIndex(1 if name == "3d" else 0)
            QApplication.processEvents()
            timed[name] = _repaints(widgets[name], count)
        return timed
    finally:
        window.stop_work()
        window.deleteLater()


def machine() -> str:
    """The machine's name, its processor, its system, Python and numpy."""
    return " · ".join(
        (
            platform.node(),
            _processor(),
            f"{platform.system()} {platform.release()}",
            f"Python {platform.python_version()}",
            f"numpy {np.__version__}",
        )
    )


def _processor() -> str:
    """The processor's marketing name where the system says it, which
    `platform.processor()` does on none of them."""
    try:
        if sys.platform.startswith("linux"):
            info = Path("/proc/cpuinfo").read_text(encoding="utf-8")
            for line in info.splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        elif sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0])
        elif sys.platform == "darwin":
            return subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or platform.machine()


# ------------------------------------------------------------ the command


def _bank(block: int) -> Bank | str:
    """The shipped set's bank at `block`, from the cache when it is there,
    or why it could not be had."""
    from immersive.audio.hrtf.bank import prepare
    from immersive.audio.hrtf.sofa import HrirSet, builtin

    loaded = builtin(HrtfRef().id)
    if not isinstance(loaded, HrirSet):
        return str(loaded)
    prepared = prepare(loaded, block)
    return prepared if isinstance(prepared, Bank) else str(prepared)


def _title() -> str:
    """The shipped set, as the pane names it."""
    from immersive.assets.hrtf import SETS

    return SETS[HrtfRef().id].title


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:7.2f}"


def run_blocks(block: int, count: int, rounds: int) -> int:
    """The table, and 0 when N-1 is met."""
    bank = _bank(block)
    if not isinstance(bank, Bank):
        print(f"The HRTF set could not be prepared: {bank}")
        return 2
    decoded = sample()
    playing = [Arrangement(bank, n, paired, decoded) for n, paired in SHAPES]
    for each in playing:
        each.play(WARM)
    times: list[list[float]] = [[] for _ in playing]
    share = max(count // rounds, 1)
    for _ in range(rounds):
        for each, into in zip(playing, times, strict=True):
            into.extend(each.play(share))
    limit = budget(block)
    print(machine())
    print(
        f"{_title()} at {block} frames: a block lasts {limit * 1000:.2f} ms. "
        f"{share * rounds} blocks each, in {rounds} rounds."
    )
    print()
    print("sources  as                  p50      p99    worst   over budget")
    measured = []
    for each, into in zip(playing, times, strict=True):
        timings = Timings(np.array(into), limit)
        measured.append((each, timings))
        shape = f"{each.channels} {'linked pairs' if each.paired else 'points'}"
        if each.channels == 1:
            shape = "1 point"
        print(
            f"{each.sources:7}  {shape:16} {_ms(timings.p50)}  {_ms(timings.p99)}"
            f"  {_ms(timings.worst)}   {timings.over}"
        )
    [thirty_two] = [t for each, t in measured if each.sources == 32 and not each.paired]
    met = thirty_two.within(HALF)
    print()
    print(
        f"N-1 {'met' if met else 'NOT met'}: 32 sources take a p99 of "
        f"{thirty_two.p99 * 1000:.2f} ms, {thirty_two.p99 / limit:.0%} of the "
        f"budget, where the line is {HALF:.0%}."
    )
    return 0 if met else 1


def run_contention(seconds: float, rounds: int, one_wait: bool) -> int:
    """The switch interval's table: misses at each interval, each load."""
    # Offscreen unless asked otherwise: the same window on every machine,
    # and nothing drawn on anyone's screen for a minute.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    laps = contention(seconds, rounds, one_wait=one_wait)
    limit = budget(DEFAULT_BLOCK)
    print(machine())
    engine = "a sleep as long as its median block" if one_wait else "the engine"
    print(
        f"{_title()} at {DEFAULT_BLOCK} frames, 32 moving sources through "
        f"{engine}, and a stand-in stream: each block due {limit * 1000:.2f} ms "
        f"after it starts. {rounds} round{'s' if rounds != 1 else ''} of "
        f"{seconds:g} s, taken in turn, after one not counted."
    )
    print()
    print("load        interval  blocks  missed  by round        p50      p99    worst")
    for load in LOADS:
        for interval in INTERVALS:
            mine = [
                lap
                for lap in laps
                if lap.load == load and math.isclose(lap.interval, interval)
            ]
            times = np.concatenate([lap.timings.times for lap in mine])
            timings = Timings(times, limit)
            by_round = ", ".join(str(lap.missed) for lap in mine)
            print(
                f"{load:11} {interval * 1000:4g} ms  {len(times):6}  "
                f"{sum(lap.missed for lap in mine):6}  {by_round:12} "
                f"{_ms(timings.p50)}  {_ms(timings.p99)}  {_ms(timings.worst)}"
            )
    return 0


def _repaints(widget: Any, count: int) -> Painted:
    """`widget` repainted `count` times, each timed, its paint events
    counted."""
    from PySide6.QtCore import QEvent, QObject

    class Counter(QObject):
        paints = 0

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if watched is widget and event.type() == QEvent.Type.Paint:
                self.paints += 1
            return False

    counter = Counter()
    widget.installEventFilter(counter)
    times = []
    for _ in range(count):
        began = time.perf_counter()
        widget.repaint()
        times.append(time.perf_counter() - began)
    widget.removeEventFilter(counter)
    return Painted(np.array(times), counter.paints)


def run_views(count: int) -> int:
    """Each view's repaint, with 32 sources as points and as pairs."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    points = views(count)
    pairs = views(count, paired=True)
    print(machine())
    print(
        f"{_title()}: each view repainted {count} times in the window at its "
        "first size, 32 sources placed as points and as linked pairs, and one "
        "bypassed. A frame at 60 Hz is 16.7 ms."
    )
    print()
    print("view         points p50      p99    worst   pairs p50      p99    worst")
    for name in VIEWS:
        row = [name.ljust(10)]
        for timed in (points[name], pairs[name]):
            if timed.paints != count:
                row.append(f"  painted {timed.paints} of {count}".ljust(31))
                continue
            row.append(
                f"  {_ms(timed.at(0.5))}  {_ms(timed.at(0.99))}  "
                f"{_ms(float(timed.times.max()))}"
            )
        print("".join(row))
    return 0


def run_live(device: str | None, block: str | None, seconds: float, load: str) -> int:
    """The live count, on the output the application would use: 0 when the
    engine counted no xrun."""
    from immersive.app import SWITCH_INTERVAL
    from immersive.audio.device import load_backend, settle

    backend = load_backend()
    if isinstance(backend, str):
        print(backend)
        return 2
    settled = settle(backend, device, block)
    for problem in settled.problems:
        print(problem)
    if not settled.usable:
        return 2
    output = settled.output
    facts = backend.query_devices(output.device, kind="output")
    api = backend.query_hostapis(facts["hostapi"])["name"]
    # As a launch sets it (D-39): this is the application, measured.
    sys.setswitchinterval(SWITCH_INTERVAL)
    heard = live(backend, output, seconds, load)
    print(machine())
    print(
        f"{facts['name']} ({api}), {output.block} frames, PortAudio's latency "
        f"{facts['default_high_output_latency'] * 1000:.0f} ms"
    )
    print(
        f"32 moving sources, {seconds:g} s {load}: {heard.xruns} xruns in "
        f"{heard.blocks} blocks"
    )
    return 0 if heard.xruns == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m immersive.benchmark",
        description="N-1, measured (D-136), and the switch interval (D-137).",
    )
    what = parser.add_subparsers(dest="what", required=True)
    timed = what.add_parser("blocks", help="each arrangement's block times")
    timed.add_argument("--block", type=int, default=DEFAULT_BLOCK)
    timed.add_argument("--count", type=int, default=3000)
    timed.add_argument("--rounds", type=int, default=3)
    loaded = what.add_parser(
        "contention", help="missed blocks with the window loaded, at each interval"
    )
    loaded.add_argument("--seconds", type=float, default=8.0)
    loaded.add_argument("--rounds", type=int, default=3)
    loaded.add_argument("--one-wait", action="store_true")
    played = what.add_parser(
        "live", help="xruns on the real output, the window shown (phase 11)"
    )
    played.add_argument("--device", help="as the application takes it")
    played.add_argument("--block", help="as the application takes it")
    played.add_argument("--seconds", type=float, default=60.0)
    played.add_argument("--load", choices=LOADS, default="playing")
    painted = what.add_parser("views", help="each spatial view's repaint (M5)")
    painted.add_argument("--count", type=int, default=200)
    options = parser.parse_args(argv)
    if options.what == "live":
        return run_live(options.device, options.block, options.seconds, options.load)
    if options.what == "views":
        return run_views(options.count)
    if options.what == "contention":
        return run_contention(options.seconds, options.rounds, options.one_wait)
    return run_blocks(options.block, options.count, options.rounds)


if __name__ == "__main__":
    raise SystemExit(main())
