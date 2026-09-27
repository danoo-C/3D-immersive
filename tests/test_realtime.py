"""`process()` allocates nothing (05, *Realtime safety checklist*; D-106).

What "nothing" means in Python is D-106's: no memory kept from one block to
the next, and no numpy array made inside a block. Python makes small objects
on every call - a slice is a view, an integer past 256 is an object - and
those are a few dozen bytes each, gone at once. An array is not: a block's
worth of float32 is 8 KiB at 2048 frames, and a ufunc that broadcasts makes
17 KiB behind `out=`. So the line is 2 KiB, a quarter of one side of a
2048-frame block, and the blocks run here go through every path `process()`
has: fades implicit and explicit, clip gain, stereo and mono, a missing
sample, gains ramping and steady, a mute, a seek and a snapshot swap, a
loop wrapping inside blocks and one shorter than a block, the project
repeating from its end (D-111), an audition voice replaced by another and
then stopped, each falling to silence (D-115), and the transport stopped and
started.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt

from immersive.audio.dsp import balance, pan_law
from immersive.audio.engine import Engine, Voice
from immersive.audio.scheduler import Snapshot, build, even
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    Fade,
    FadeShape,
    Master,
    MediaFile,
    Project,
)

BLOCK = 2048
#: What no block may raise traced memory's peak by (D-106).
LINE = 2048
FRAMES = 48_000 * 4


def sample(channels: int, seed: int) -> Decoded:
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.5, 0.5, (FRAMES, channels)).astype(np.float32)
    audio.flags.writeable = False
    return Decoded(audio, 48_000)


def arrangement() -> tuple[Project, dict[str, Decoded]]:
    """Six channels: a mono loop cut into pieces with fades of both shapes,
    a stereo pad with clip gain, a mono channel whose sample is missing, a
    channel left silent, and a mono and a stereo channel bypassed and panned
    (D-125). The master is 12 dB up, so the limiter works on every block."""
    mono = MediaFile("m-00000001", "/m.wav", "m.wav", 48_000, 1, FRAMES)
    stereo = MediaFile("m-00000002", "/s.wav", "s.wav", 48_000, 2, FRAMES)
    gone = MediaFile("m-00000003", "/g.wav", "g.wav", 48_000, 1, FRAMES)
    pieces = [
        Clip(
            f"k-000001{n:02x}",
            mono.id,
            n * 7_000,
            n * 1_500,
            6_000,
            fade_in=Fade(n * 100, FadeShape.EQUAL_POWER if n % 2 else FadeShape.LINEAR),
            fade_out=Fade((n % 3) * 250),
        )
        for n in range(20)
    ]
    project = Project(
        media_pool=[mono, stereo, gone],
        channels=[
            Channel("c-00000001", "Loop", "#A855F7", clips=pieces),
            Channel(
                "c-00000002",
                "Pad",
                "#22D3EE",
                gain_db=-3.0,
                clips=[
                    Clip(
                        "k-00000201",
                        stereo.id,
                        1_000,
                        500,
                        FRAMES - 500,
                        gain_db=-6.0,
                        fade_in=Fade(4_000, FadeShape.EQUAL_POWER),
                    )
                ],
            ),
            Channel(
                "c-00000003",
                "Gone",
                "#F59E0B",
                clips=[Clip("k-00000301", gone.id, 0, 0, FRAMES)],
            ),
            Channel("c-00000004", "Empty", "#34D399"),
            Channel(
                "c-00000005",
                "Bypassed mono",
                "#F472B6",
                hrtf_bypass=True,
                pan=-0.4,
                clips=[Clip("k-00000501", mono.id, 0, 0, FRAMES)],
            ),
            Channel(
                "c-00000006",
                "Bypassed stereo",
                "#60A5FA",
                hrtf_bypass=True,
                pan=0.7,
                clips=[Clip("k-00000601", stereo.id, 0, 0, FRAMES)],
            ),
        ],
        master=Master(gain_db=12.0),
    )
    store = {mono.id: sample(1, 1), stereo.id: sample(2, 2)}
    return project, store


def measured(
    engine: Engine, blocks: npt.NDArray[np.int64], between: Callable[[int], None]
) -> None:
    """Run a block per row of `blocks`, calling `between(n)` - the UI
    thread's part - outside what is measured, and write into each row how
    far that block raised the peak and how much it left allocated.

    The measuring keeps nothing of its own. Every reading goes straight into
    an array made beforehand: an integer a reading returns, kept in a local,
    is made after the reading measured, and the first block would count it
    as its own - 64 bytes, found with a `process()` that did nothing.
    """
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    before = np.zeros(1, dtype=np.int64)
    after = np.zeros(2, dtype=np.int64)
    for n in range(blocks.shape[0]):
        between(n)
        before[0] = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        engine.process(out)
        after[0], after[1] = tracemalloc.get_traced_memory()
        blocks[n, 0] = after[1] - before[0]
        blocks[n, 1] = after[0] - before[0]


def run() -> tuple[int, int]:
    """Every path through `process()` for 500 blocks: what they left
    allocated between them, and the most any one raised the peak by."""
    project, store = arrangement()
    engine = Engine(BLOCK)
    # The ring's counts past 256 first, where an integer becomes an object
    # of its own and keeps 32 bytes, once: in block 1 028 when only gains
    # and the transport were sent, and in block 466 with pan and the master
    # too, which is inside what is counted.
    for _ in range(300):
        engine.set_repeat(0, False)
    engine.drain()
    first = build(project, store.get)
    engine.install(first)
    engine.set_playing(True)
    project.channels[0].gain_db = -1.0
    second = build(project, store.get, first)
    held: list[Snapshot] = [first, second]
    voices = [Voice(store["m-00000001"].audio), Voice(store["m-00000002"].audio)]

    def ui(n: int) -> None:
        """What the UI thread does meanwhile: gains, a mute, a seek, a swap,
        loops, auditions, a repeat, pan, the master's gain and its limiter
        switched off and on."""
        generation = second.generation if engine.holds(second) else first.generation
        engine.take_peaks()
        engine.take_channel_peaks()  # the meters' frame, outside what is measured
        if n % 7 == 0:
            engine.send_gain(generation, 1, even(0.25 + (n % 5) / 10))
        if n == 40:
            engine.send_gain(generation, 0, even(0.0))
        if n == 45:
            engine.send_gain(generation, 0, even(1.0))
        if n % 11 == 0:
            pan = -1.0 + (n % 21) / 10
            engine.send_gain(generation, 4, (*pan_law(pan), *balance(pan)))
            engine.send_gain(generation, 5, (*pan_law(-pan), *balance(-pan)))
        if n % 13 == 0:
            engine.send_master(generation, 2.0 + (n % 3), True)
        if n == 65:
            engine.send_master(generation, 4.0, False)  # the switch fading off
        if n == 67:
            engine.send_master(generation, 4.0, True)
        if n == 60:
            engine.seek(12_345)
        if n == 80:
            engine.install(second)
        if n == 20:
            engine.set_loop(40_000, 40_000 + 3_000, True)  # wraps inside blocks
        if n == 30:
            engine.audition(voices[0])
        if n == 35:
            engine.audition(voices[1])  # and one replacing it, the first falling
        if n == 38:
            engine.audition(None)  # stopped: falling to silence (D-115)
        if n == 50:
            engine.set_loop(40_000, 40_100, True)  # shorter than a block
        if n == 70:
            engine.set_loop(0, 0, False)
        if n == 72:  # the playhead wraps back to 0 in block 80, mid-block
            engine.set_repeat(12_345 + 20 * BLOCK + 100, True)
        if n == 85:
            engine.set_repeat(0, False)
        if n == 90:
            engine.set_playing(False)  # stopped, still auditioning
        if n == 95:
            engine.set_playing(True)

    # A turn of the UI thread's cycle before what is counted: every path
    # taken once, and the freelists filled. In the same call as the 500
    # blocks, not one of its own: `measured` makes arrays of its own, and
    # with a warm-up called apart the first repeat wrapping mid-block kept
    # 32 bytes - once per call, never again in 2 000 blocks.
    #
    blocks = np.zeros((600, 2), dtype=np.int64)
    measured(engine, blocks, lambda n: ui(n % 100))
    counted = blocks[100:]

    assert held and voices  # the UI thread's references, kept to the end
    return int(counted[:, 1].sum()), int(counted[:, 0].max())


def run_spatial() -> tuple[int, int]:
    """The spatial path (M4): 32 channels, every one moving by a `POSITION`
    every block - N-1's load - through a synthetic head's bank, with one
    bypassed channel beside them. One orbits inside the centre (D-130), and
    the level is kept as mixed (D-131). The same measure as `run`."""
    import tempfile

    from immersive.audio.hrtf import lookup
    from immersive.audio.hrtf.bank import Bank, prepare
    from immersive.core.model import Position
    from test_spatial import head

    # The index at test size: `setattr`, since they are `Final` constants.
    setattr(lookup, "CELLS", 16)  # noqa: B010
    setattr(lookup, "SAMPLES", 2)  # noqa: B010
    with tempfile.TemporaryDirectory() as cache:
        bank = prepare(head(), BLOCK, Path(cache))
    assert isinstance(bank, Bank)

    source = MediaFile("m-00000001", "/m.wav", "m.wav", 48_000, 2, FRAMES)
    store = {source.id: sample(2, 3)}
    channels = [
        Channel(
            f"c-{n:08x}",
            f"S{n}",
            "#A855F7",
            hrtf_bypass=n == 32,
            gain_db=-12.0,
            position=Position(1.0, 1.0, 0.0),
            clips=[Clip(f"k-{n:08x}", source.id, n * 100, 0, FRAMES - n * 100)],
        )
        for n in range(33)
    ]
    project = Project(media_pool=[source], channels=channels)
    snapshot = build(project, store.get, None, bank)
    engine = Engine(BLOCK)
    engine.install(snapshot)
    engine.set_playing(True)
    generation = snapshot.generation
    turns = np.linspace(0.0, 2.0 * np.pi, 33)

    def ui(n: int) -> None:
        """Every source a little further round, and now and then a seek."""
        engine.take_peaks()
        engine.take_channel_peaks()
        for channel in range(32):
            angle = float(turns[channel]) + n * 0.07
            # Channel 0 orbits inside the centre, a tenth of the way out, so
            # its filter fades part way to flat every block (D-130).
            reach = 0.1 if channel == 0 else 1.0
            engine.send_position(
                generation,
                channel,
                reach * math.sin(angle),
                reach * math.cos(angle),
                reach * 0.3,
            )
        if n == 50:
            engine.seek(24_000)

    # Two turns of the cycle before counting, not one: CPython's float
    # freelist grows to its high-water mark in block 132 - 32 bytes, once
    # in 800 blocks, never again - and a leak would repeat every turn.
    blocks = np.zeros((400, 2), dtype=np.int64)
    measured(engine, blocks, lambda n: ui(n % 100))
    counted = blocks[200:]
    return int(counted[:, 1].sum()), int(counted[:, 0].max())


def test_process_makes_no_array_and_keeps_nothing() -> None:
    """Measured in an interpreter of its own. `tracemalloc` counts every
    thread's allocations, and a pytest-xdist worker has a thread of its own
    passing messages: one run in six, it allocated during a block and the
    test blamed `process()` for 1 698 bytes. Nothing else runs in a fresh
    interpreter, so what is measured there is the engine's."""
    done = subprocess.run(
        [sys.executable, str(Path(__file__))],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    kept, worst = json.loads(done.stdout)
    assert kept <= 0, f"500 blocks left {kept} bytes allocated"
    assert worst < LINE, f"a block raised the peak by {worst} bytes"


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    spatial = sys.argv[1:] == ["spatial"]
    tracemalloc.start()
    print(json.dumps(run_spatial() if spatial else run()))


def test_the_spatial_path_makes_no_array_and_keeps_nothing() -> None:
    """32 moving sources through the HRTF, measured as the flat path is."""
    done = subprocess.run(
        [sys.executable, str(Path(__file__)), "spatial"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    kept, worst = json.loads(done.stdout)
    assert kept <= 0, f"200 blocks left {kept} bytes allocated"
    assert worst < LINE, f"a block raised the peak by {worst} bytes"
