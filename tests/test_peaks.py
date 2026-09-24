"""Peaks: the pyramid, and the cache that keeps it. Headless (N-5).

The pyramid is checked against a brute-force oracle - a Python loop over
explicit slices of the audio, sharing no code with the vectorised build - so
that the two cannot be wrong the same way.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest

from immersive.core.io import peaks
from immersive.core.io.peaks import BUCKET, RATIO, Pyramid, build


def signal(frames: int, channels: int = 1, seed: int = 0) -> npt.NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, (frames, channels)).astype(np.float32)


def oracle(
    audio: npt.NDArray[np.float32], bucket: int
) -> tuple[list[list[float]], list[list[float]]]:
    """Min and max of each explicit slice, one bucket at a time."""
    lows, highs = [], []
    for start in range(0, len(audio), bucket):
        covered = audio[start : start + bucket]
        lows.append([float(covered[:, c].min()) for c in range(audio.shape[1])])
        highs.append([float(covered[:, c].max()) for c in range(audio.shape[1])])
    return lows, highs


def assert_matches_oracle(pyramid: Pyramid, audio: npt.NDArray[np.float32]) -> None:
    for level in pyramid.levels:
        lows, highs = oracle(audio, level.bucket)
        assert level.buckets == len(lows), f"level of {level.bucket}"
        np.testing.assert_array_equal(level.low, np.array(lows, dtype=np.float32))
        np.testing.assert_array_equal(level.high, np.array(highs, dtype=np.float32))


LENGTHS = [
    1,
    BUCKET - 1,
    BUCKET,
    BUCKET + 1,
    BUCKET * RATIO,
    BUCKET * RATIO**3 + 17,  # several levels' worth, and a remainder
    100_003,
]


@pytest.mark.parametrize("frames", LENGTHS)
def test_every_bucket_of_every_level_is_its_frames_min_and_max(frames: int) -> None:
    audio = signal(frames, seed=frames)

    assert_matches_oracle(build(audio), audio)


@pytest.mark.parametrize("frames", LENGTHS)
def test_the_last_level_is_the_whole_file(frames: int) -> None:
    audio = signal(frames, seed=frames + 1)

    top = build(audio).levels[-1]

    assert top.buckets == 1
    assert top.low[0, 0] == audio.min()
    assert top.high[0, 0] == audio.max()


def test_each_level_is_four_times_coarser(frames: int = 100_003) -> None:
    pyramid = build(signal(frames))

    buckets = [level.bucket for level in pyramid.levels]
    assert buckets == [BUCKET * RATIO**k for k in range(len(buckets))]
    assert len(buckets) == 1 + math.ceil(math.log(frames / BUCKET, RATIO))


def test_the_end_of_a_sample_is_not_drawn_as_silence() -> None:
    """The remainder is its own short bucket, not dropped."""
    audio = np.zeros((BUCKET + 3, 1), dtype=np.float32)
    audio[-1, 0] = 0.9

    level = build(audio).levels[0]

    assert level.buckets == 2
    assert level.high[-1, 0] == pytest.approx(0.9)


def test_stereo_keeps_a_pyramid_per_channel() -> None:
    audio = np.zeros((BUCKET * 8, 2), dtype=np.float32)
    audio[:, 0] = 0.25
    audio[:, 1] = -0.5

    pyramid = build(audio)

    assert pyramid.channels == 2
    for level in pyramid.levels:
        assert (level.high[:, 0] == 0.25).all()
        assert (level.low[:, 1] == -0.5).all()
    assert_matches_oracle(pyramid, audio)


def test_overs_survive() -> None:
    """A float file may hold 2.0 (phase 2), and the drawing must show it."""
    audio = np.array([[2.0], [-3.0]], dtype=np.float32)

    top = build(audio).levels[-1]

    assert (top.low[0, 0], top.high[0, 0]) == (-3.0, 2.0)


def test_the_levels_are_float32() -> None:
    for level in build(signal(5_000)).levels:
        assert level.low.dtype == level.high.dtype == np.float32


def test_nothing_has_no_peaks() -> None:
    """decode() refuses empty files, so this is a caller's mistake."""
    with pytest.raises(ValueError):
        build(np.zeros((0, 1), dtype=np.float32))


def test_the_constants_are_the_documented_ones() -> None:
    """Pinned: changing either is a cache format change."""
    assert (peaks.BUCKET, peaks.RATIO) == (256, 4)
