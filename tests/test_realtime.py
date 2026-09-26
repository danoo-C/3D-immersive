"""`process()` allocates nothing (05, *Realtime safety checklist*; D-106).

What "nothing" means in Python is D-106's: no memory kept from one block to
the next, and no numpy array made inside a block. Python makes small objects
on every call - a slice is a view, an integer past 256 is an object - and
those are a few dozen bytes each, gone at once. An array is not: a block's
worth of float32 is 8 KiB at 2048 frames, and a ufunc that broadcasts makes
17 KiB behind `out=`. So the line is 2 KiB, a quarter of one side of a
2048-frame block, and the blocks run here go through every path `process()`
has: fades implicit and explicit, clip gain, stereo and mono, a missing
sample, gains ramping and steady, a mute, a seek and a snapshot swap.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable, Iterator

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.engine import Engine
from immersive.audio.scheduler import Snapshot, build
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Fade, FadeShape, MediaFile, Project

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
    """Four channels: a mono loop cut into pieces with fades of both shapes,
    a stereo pad with clip gain, a mono channel whose sample is missing, and
    a channel left silent."""
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
        ],
    )
    store = {mono.id: sample(1, 1), stereo.id: sample(2, 2)}
    return project, store


@pytest.fixture
def traced() -> Iterator[None]:
    tracemalloc.start()
    try:
        yield
    finally:
        tracemalloc.stop()


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


def test_process_makes_no_array_and_keeps_nothing(traced: None) -> None:
    project, store = arrangement()
    engine = Engine(BLOCK)
    first = build(project, store.get)
    engine.install(first)
    project.channels[0].gain_db = -1.0
    second = build(project, store.get, first)
    held: list[Snapshot] = [first, second]

    def ui(n: int) -> None:
        """What the UI thread does meanwhile: gains, a mute, a seek, a swap."""
        generation = second.generation if engine.holds(second) else first.generation
        if n % 7 == 0:
            engine.send_gain(generation, 1, 0.25 + (n % 5) / 10)
        if n == 40:
            engine.send_gain(generation, 0, 0.0)
        if n == 45:
            engine.send_gain(generation, 0, 1.0)
        if n == 60:
            engine.seek(12_345)
        if n == 80:
            engine.install(second)

    # A turn of the UI thread's cycle before measuring: every path taken
    # once, and Python's freelists filled.
    warm = np.zeros((100, 2), dtype=np.int64)
    blocks = np.zeros((500, 2), dtype=np.int64)
    measured(engine, warm, lambda n: ui(n % 100))

    measured(engine, blocks, lambda n: ui(n % 100))

    kept = int(blocks[:, 1].sum())
    assert kept <= 0, f"500 blocks left {kept} bytes allocated"
    worst = int(blocks[:, 0].max())
    assert worst < LINE, f"a block raised the peak by {worst} bytes"
    assert held  # the UI thread's references, kept to the end
