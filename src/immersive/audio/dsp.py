"""Arithmetic on blocks: gains, fade tables, and the ramp a gain change is
spread across.

Device-free and Qt-free. What happens inside `process()` is only ever a
multiply or an add into a buffer that already exists; this module makes
the tables those multiplies read, and it makes them on the UI thread.

**A fade is sampled from `FadeShape.gain`**, the function the clip draws
its curve from. A fade-in `L` samples long is `gain(k / L)` at its `k`th
sample, so it starts silent and the sample after it is whole; a fade-out
is the same table backwards, so it ends silent. `fade_curve` computes a
whole table at once, and a test holds it to `FadeShape.gain` sample for
sample, so there is still one definition of a shape.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import numpy.typing as npt

from immersive.core.model import FadeShape

Samples = npt.NDArray[np.float32]

#: D-42: the fade given to an edge that is not its file's own start or end.
IMPLICIT_FADE = 32


def db_to_gain(db: float) -> float:
    """Decibels as a factor: 0 dB is exactly 1, and -6 dB about a half."""
    return 1.0 if db == 0 else float(10.0 ** (db / 20.0))


def fade_curve(shape: FadeShape, positions: npt.NDArray[np.float64]) -> Samples:
    """`shape.gain` at every one of `positions`, 0 to 1, as float32."""
    t = np.clip(positions, 0.0, 1.0)
    if shape is FadeShape.EQUAL_POWER:
        t = np.sin(t * (np.pi / 2))
    return t.astype(np.float32)


@lru_cache(maxsize=256)
def fade_in(shape: FadeShape, length: int) -> Samples:
    """A fade-in's gains, sample by sample: `gain(k / length)`.

    Shared between every clip with the same fade, so it is read-only; a
    clip that wrote to it would be changing all of them.
    """
    table = fade_curve(shape, np.arange(length, dtype=np.float64) / length)
    table.flags.writeable = False
    return table


@lru_cache(maxsize=256)
def fade_out(shape: FadeShape, length: int) -> Samples:
    """A fade-out's gains: the fade-in's, backwards, ending silent."""
    table = np.ascontiguousarray(fade_in(shape, length)[::-1])
    table.flags.writeable = False
    return table


def ramp_steps(block: int) -> Samples:
    """How far through a ramp each sample of a block is: `1/block` to 1, so
    the block's last sample is at the new gain and its first has already
    moved from the old one."""
    return (np.arange(1, block + 1, dtype=np.float64) / block).astype(np.float32)
