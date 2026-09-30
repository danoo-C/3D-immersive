"""The engine's block, compiled (M4 phase 12, D-138, D-140): each kernel is
the Python it replaced, `reference_engine`, compared exactly where the two
do the same float32 operations in the same order."""

from __future__ import annotations

import numpy as np
import pytest

import reference_engine
from immersive.audio.limiter import LOOKAHEAD, Limiter
from immersive.audio.scheduler import MONO, build, fill
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, MediaFile, Project
from test_realtime import arrangement

SIZE = 2048


def test_fill_equals_the_reference_everywhere() -> None:
    """Every lane of the zero-allocation arrangement: fades of both shapes,
    clip gain, mono and stereo, a missing sample, clips cut at both ends.
    Read at every 311th sample, a whole block, a piece and a single sample
    at a time. Rows a fill leaves alone are left alone by both."""
    project, store = arrangement()
    snapshot = build(project, store.get)
    rows = np.zeros((6, SIZE), dtype=np.float32)
    for lane in snapshot.lanes:
        for t in range(-SIZE, project.length + SIZE, 311):
            for size in (SIZE, 300, 1):
                rows.fill(np.nan)
                kernel = [rows[n, :size] for n in (0, 1, 2)]
                python = [rows[n, :size] for n in (3, 4, 5)]
                wrote = fill(lane, t, *kernel)
                assert wrote == reference_engine.fill(lane, t, *python)
                np.testing.assert_array_equal(rows[0:3], rows[3:6])


def test_a_clip_past_its_samples_end_plays_silence_there() -> None:
    """A sample is read by address, and an address is not bounds-checked
    (D-140), so a read stops at the sample's own end: a clip that claims
    more than its file has plays what there is, then silence."""
    media = MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 1, 1000)
    audio = np.full((500, 1), 0.25, dtype=np.float32)
    clip = Clip("k-00000001", media.id, 0, 0, 1000)
    channel = Channel("c-00000001", "C", "#A855F7", clips=[clip])
    project = Project(media_pool=[media], channels=[channel])
    snapshot = build(project, {media.id: Decoded(audio, 48_000)}.get)
    left, right, mono = (np.full(SIZE, np.nan, dtype=np.float32) for _ in range(3))

    assert fill(snapshot.lanes[0], 0, left, right, mono) == MONO
    assert (mono[:500] == 0.25).all()
    assert (mono[500:] == 0.0).all()


@pytest.mark.parametrize("block", [512, LOOKAHEAD - 8])
def test_the_limiter_equals_the_reference(block: int) -> None:
    """Loud stretches it must turn down and quiet ones it must leave, with
    the switch held on, faded off, held off and faded back on (D-126); and
    a block shorter than the lookahead, which the rows' moves must survive.
    The reduction goes through `log10` and `10 **` in float64, whose last
    bits may differ between numpy and numba, so the two agree to float32
    rounding rather than exactly."""
    rng = np.random.default_rng(7)
    compiled, python = Limiter(block), reference_engine.Limiter(block)
    switch = [1.0] * 20 + [0.0] * 10 + [1.0] * 30
    for n in range(len(switch) - 1):
        loud = 3.0 if (n // 7) % 2 == 0 else 0.3
        signal = (loud * rng.standard_normal((2, block))).astype(np.float32)
        mine, theirs = signal.copy(), signal.copy()
        compiled.process(mine[0], mine[1], switch[n], switch[n + 1])
        python.process(theirs[0], theirs[1], switch[n], switch[n + 1])
        np.testing.assert_allclose(mine, theirs, rtol=2e-6, atol=1e-7)
