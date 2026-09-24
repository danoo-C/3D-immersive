"""Waveform peaks: a min/max pyramid, and the cache that keeps it (F-9, D-59).

Level 0 summarises every `BUCKET` frames; each level above summarises `RATIO`
buckets of the one below, up to a level of one bucket that is the whole
file's minimum and maximum. A drawing reads the coarsest level that still has
a bucket or two per pixel: a 120-pixel thumbnail of five minutes of stereo
reads 55 buckets, not fourteen million frames.

Per channel and in float32. Float sources keep their overs (phase 2 of M2),
and a pyramid in a narrower integer type would clip exactly those.

These numbers are for drawing, not listening. Finer than `BUCKET` is M3's
problem at deep zoom, where it can read the audio itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

#: Frames per bucket at the finest level.
BUCKET: Final = 256

#: Buckets of one level per bucket of the level above.
RATIO: Final = 4

Audio = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Level:
    """One level: the lowest and highest sample in each bucket, per channel.

    `low` and `high` are `(buckets, channels)`. The last bucket covers
    whatever frames are left, which may be fewer than `bucket`.
    """

    bucket: int
    low: Audio
    high: Audio

    @property
    def buckets(self) -> int:
        return int(self.low.shape[0])


@dataclass(frozen=True)
class Pyramid:
    """Every level of one sample's peaks, finest first."""

    frames: int
    channels: int
    levels: tuple[Level, ...]


def build(audio: Audio) -> Pyramid:
    """Summarise `audio`, `(frames, channels)`, into a pyramid.

    Each level is built from the one below rather than from the audio, which
    is what makes the whole pyramid cost little more than its finest level -
    the min of four minima is the minimum of what they covered.
    """
    frames, channels = (int(size) for size in audio.shape)
    if frames == 0:
        raise ValueError("there are no peaks of nothing; decode refuses empty files")

    low, high = _reduce(audio, audio, BUCKET)
    levels = [Level(BUCKET, low, high)]
    while levels[-1].buckets > 1:
        below = levels[-1]
        low, high = _reduce(below.low, below.high, RATIO)
        levels.append(Level(below.bucket * RATIO, low, high))
    return Pyramid(frames, channels, tuple(levels))


def _reduce(low: Audio, high: Audio, group: int) -> tuple[Audio, Audio]:
    """Minimum of `low` and maximum of `high` over each run of `group` rows.

    The rows left over make one last, shorter group rather than being
    dropped - dropping them would draw the end of every sample as silence.
    """
    rows = int(low.shape[0])
    whole = rows // group
    lows: list[Audio] = []
    highs: list[Audio] = []
    if whole:
        shape = (whole, group, low.shape[1])
        lows.append(low[: whole * group].reshape(shape).min(axis=1))
        highs.append(high[: whole * group].reshape(shape).max(axis=1))
    if rows % group:
        lows.append(low[whole * group :].min(axis=0, keepdims=True))
        highs.append(high[whole * group :].max(axis=0, keepdims=True))
    return (
        np.ascontiguousarray(np.concatenate(lows), dtype=np.float32),
        np.ascontiguousarray(np.concatenate(highs), dtype=np.float32),
    )
