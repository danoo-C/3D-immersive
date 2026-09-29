"""N-1, measured (D-136).

    python -m immersive.benchmark blocks [--block 512] [--count 3000] [--rounds 3]

**`blocks`** times the engine a block at a time, with no window and no
device. The HRTF set is the one the application ships, prepared at the
block asked for. Each arrangement is played in turn, round after round,
since timings on one machine drift from run to run. It reports the median,
the 99th percentile and the worst block, and how many blocks were over
budget, beside the machine's name. N-1 is met when 32 sources take a p99
under half the budget.

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
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from immersive.audio.device import DEFAULT_BLOCK
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m immersive.benchmark",
        description="N-1, measured (D-136).",
    )
    what = parser.add_subparsers(dest="what", required=True)
    timed = what.add_parser("blocks", help="each arrangement's block times")
    timed.add_argument("--block", type=int, default=DEFAULT_BLOCK)
    timed.add_argument("--count", type=int, default=3000)
    timed.add_argument("--rounds", type=int, default=3)
    options = parser.parse_args(argv)
    return run_blocks(options.block, options.count, options.rounds)


if __name__ == "__main__":
    raise SystemExit(main())
