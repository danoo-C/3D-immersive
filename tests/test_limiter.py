"""The master limiter (05, *The limiter*; D-54, D-123, D-124). The limiter
alone, block by block, and then in the engine: after the master gain, over
the audition, and delaying everything alike whether it is on or off."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest

from hearing import Tape
from immersive.audio.engine import Engine, Voice
from immersive.audio.limiter import (
    CEILING_DB,
    KNEE_DB,
    LOOKAHEAD,
    RELEASE,
    Limiter,
    reduction,
)
from immersive.audio.scheduler import build
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Master, MediaFile, Project
from immersive.core.time import SAMPLE_RATE

Audio = npt.NDArray[np.float32]
CEILING = 10 ** (CEILING_DB / 20)


def limited(
    left: npt.ArrayLike,
    right: npt.ArrayLike | None = None,
    *,
    block: int = 256,
    on: bool = True,
) -> Audio:
    """Both sides through a fresh limiter a block at a time: `(frames, 2)`,
    the last block padded with silence."""
    left = np.asarray(left, dtype=np.float32)
    right = left if right is None else np.asarray(right, dtype=np.float32)
    frames = -(-len(left) // block) * block
    sides = np.zeros((2, frames), dtype=np.float32)
    sides[0, : len(left)] = left
    sides[1, : len(right)] = right
    limiter = Limiter(block)
    switch = 1.0 if on else 0.0
    for start in range(0, frames, block):
        limiter.process(
            sides[0, start : start + block],
            sides[1, start : start + block],
            switch,
            switch,
        )
    return sides.T


def db(value: npt.ArrayLike) -> npt.NDArray[np.float64]:
    return 20.0 * np.log10(np.asarray(value, dtype=np.float64))


# --------------------------------------------------------------------------- #
# brickwall
# --------------------------------------------------------------------------- #


def hot_signals(frames: int) -> dict[str, Audio]:
    rng = np.random.default_rng(7)
    t = np.arange(frames) / SAMPLE_RATE
    first = np.zeros(frames, dtype=np.float32)
    first[4 * 2048] = 4.0  # the first sample of a block, at every size here
    last = np.zeros(frames, dtype=np.float32)
    last[4 * 2048 - 1] = 4.0  # and the last: its hold reaches into the next
    return {
        "noise to +12 dBFS": (rng.uniform(-4.0, 4.0, frames)).astype(np.float32),
        "a sine at +6 dBFS": (2.0 * np.sin(2 * np.pi * 441 * t)).astype(np.float32),
        "one sample, first in a block": first,
        "one sample, last in a block": last,
    }


@pytest.mark.parametrize("block", [256, 512, 2048])
@pytest.mark.parametrize(
    "signal",
    [
        "noise to +12 dBFS",
        "a sine at +6 dBFS",
        "one sample, first in a block",
        "one sample, last in a block",
    ],
)
def test_no_sample_passes_the_ceiling(block: int, signal: str) -> None:
    out = limited(hot_signals(16 * 2048)[signal], block=block)
    assert float(np.abs(out).max()) <= CEILING


def test_below_the_knee_the_output_is_the_input_72_samples_late() -> None:
    rng = np.random.default_rng(8)
    quiet = rng.uniform(-0.84, 0.84, 20 * 256).astype(np.float32)  # under -1.3 dBFS
    out = limited(quiet)
    assert LOOKAHEAD == 72
    assert not out[:LOOKAHEAD].any()
    np.testing.assert_array_equal(out[LOOKAHEAD:, 0], quiet[:-LOOKAHEAD])
    np.testing.assert_array_equal(out[LOOKAHEAD:, 1], quiet[:-LOOKAHEAD])


# --------------------------------------------------------------------------- #
# the curve, the link, the release, the attack
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("level", "turned_down"),
    [(-2.0, 0.0), (-1.3, 0.0), (-0.8, 0.0625), (-0.3, 0.25), (0.7, 1.0), (6.0, 6.3)],
)
def test_the_static_curve_below_in_and_above_the_knee(
    level: float, turned_down: float
) -> None:
    """A held level settles at the curve: nothing below -1.3 dBFS, a soft
    knee 2 dB wide, and the ceiling above +0.7 dBFS."""
    assert reduction(level) == pytest.approx(turned_down, abs=1e-4)
    held = np.full(40 * 256, 10 ** (level / 20), dtype=np.float32)
    out = limited(held)
    assert float(db(out[-256, 0])) == pytest.approx(level - turned_down, abs=1e-4)
    assert KNEE_DB == 2.0


@pytest.mark.parametrize("loud", [0, 1])
def test_a_peak_on_one_side_turns_both_down_alike(loud: int) -> None:
    frames = 8 * 256
    sides = np.full((2, frames), 0.25, dtype=np.float32)
    sides[loud, 1000] = 3.0
    out = limited(sides[0], sides[1])
    assert float(np.abs(out).max()) <= CEILING
    gains = out[LOOKAHEAD:].T / sides[:, :-LOOKAHEAD]
    quiet = 1 - loud
    assert gains[quiet].min() < 0.5, "the quiet side was turned down too"
    around = slice(900, 1100)
    np.testing.assert_allclose(gains[loud][around], gains[quiet][around])


def test_after_a_peak_the_reduction_falls_by_e_in_50_ms_across_blocks() -> None:
    frames = 48 * 256
    held = np.full(frames, 0.25, dtype=np.float32)
    held[500:600] = 3.0
    out = limited(held)[LOOKAHEAD:, 0].astype(np.float64)
    turned = -db(out / held[:-LOOKAHEAD])
    first = 600 + 2 * LOOKAHEAD + 200  # past the burst, its hold and its average
    later = first + round(RELEASE * SAMPLE_RATE)
    assert turned[first] > 1.0
    assert turned[later] / turned[first] == pytest.approx(math.exp(-1), rel=1e-3)


def test_the_reduction_begins_72_samples_before_its_peak() -> None:
    frames = 8 * 256
    held = np.full(frames, 0.25, dtype=np.float32)
    peak = 1000
    held[peak] = 3.0
    out = limited(held)[:, 0]
    # the peak comes out at `peak + 72`; the ramp down to it starts at `peak`
    np.testing.assert_array_equal(out[LOOKAHEAD:peak], held[: peak - LOOKAHEAD])
    assert out[peak] < held[peak - LOOKAHEAD]
    assert abs(float(out[peak + LOOKAHEAD])) <= CEILING
    ramp = out[peak : peak + LOOKAHEAD]
    assert (np.diff(ramp) < 0).all(), "a ramp down, not a step"


# --------------------------------------------------------------------------- #
# off, and switching
# --------------------------------------------------------------------------- #


def test_off_a_signal_past_full_scale_passes_untouched_and_as_late() -> None:
    hot = hot_signals(16 * 2048)["noise to +12 dBFS"][: 8 * 256]
    out = limited(hot, on=False)
    assert not out[:LOOKAHEAD].any()
    np.testing.assert_array_equal(out[LOOKAHEAD:, 0], hot[:-LOOKAHEAD])


def test_a_switch_fades_across_a_block() -> None:
    block = 256
    hot = np.full(block, 2.0, dtype=np.float32)
    limiter = Limiter(block)
    for _ in range(40):
        left, right = hot.copy(), hot.copy()
        limiter.process(left, right, 1.0, 1.0)
    settled = float(left[-1])
    assert settled == pytest.approx(CEILING, rel=1e-5)

    left, right = hot.copy(), hot.copy()
    limiter.process(left, right, 1.0, 0.0)
    steps = np.diff(left.astype(np.float64))
    assert (steps > 0).all() and steps.max() < 2 * (2.0 - settled) / block
    assert left[-1] == 2.0, "off by the block's last sample"


# --------------------------------------------------------------------------- #
# in the engine
# --------------------------------------------------------------------------- #


BLOCK = 256


def project_of(
    value: float, gain_db: float = 0.0, limiter_on: bool = True
) -> tuple[Project, dict[str, Decoded]]:
    frames = 48_000
    media = MediaFile("m-00000001", "/a.wav", "a.wav", 48_000, 2, frames)
    audio = np.full((frames, 2), value, dtype=np.float32)
    project = Project(
        media_pool=[media],
        channels=[
            Channel(
                "c-00000001",
                "C",
                "#A855F7",
                hrtf_bypass=True,
                clips=[Clip("k-00000001", media.id, 0, 0, frames)],
            )
        ],
        master=Master(gain_db=gain_db, limiter_on=limiter_on),
    )
    return project, {media.id: Decoded(audio, 48_000)}


def raw(engine: Engine, blocks: int) -> Audio:
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    played = []
    for _ in range(blocks):
        engine.process(out)
        played.append(out.copy())
    return np.concatenate(played)


@pytest.mark.parametrize("on", [True, False])
def test_the_engine_is_late_by_its_latency_with_the_limiter_on_or_off(on: bool) -> None:
    project, store = project_of(0.5, limiter_on=on)
    engine = Engine(BLOCK)
    engine.install(build(project, store.get))
    engine.set_playing(True)
    assert engine.latency == LOOKAHEAD
    out = raw(engine, 3)
    assert not out[: engine.latency].any()
    assert (out[engine.latency :] == np.float32(0.5)).all()


def test_master_gain_comes_before_the_limiter() -> None:
    """+12 dB of master gain on a half-scale channel is still under the
    ceiling: the limiter sees what the gain made."""
    project, store = project_of(0.5, gain_db=12.0)
    engine = Engine(BLOCK)
    engine.install(build(project, store.get))
    engine.set_playing(True)
    out = raw(engine, 20)
    assert float(np.abs(out).max()) <= CEILING
    assert float(out[-1, 0]) == pytest.approx(CEILING, rel=1e-5)


def test_the_audition_is_limited_too() -> None:
    engine = Engine(BLOCK)
    engine.audition(Voice(np.full((48_000, 1), 1.5, dtype=np.float32)))
    out = raw(engine, 20)
    assert float(np.abs(out).max()) <= CEILING
    assert float(out[-1, 0]) == pytest.approx(CEILING, rel=1e-5)


def test_the_master_meter_reads_what_the_limiter_lets_out() -> None:
    project, store = project_of(1.5)
    engine = Engine(BLOCK)
    engine.install(build(project, store.get))
    engine.set_playing(True)
    raw(engine, 20)
    left, right = engine.take_peaks()
    assert left <= CEILING and right <= CEILING
    [(_, channel_left, _)] = engine.take_channel_peaks()
    assert channel_left == pytest.approx(1.5), "the channel's own, before it"


def test_switching_the_limiter_in_the_engine_fades_and_moves_nothing_in_time() -> None:
    project, store = project_of(2.0)
    engine = Engine(BLOCK)
    snapshot = build(project, store.get)
    engine.install(snapshot)
    engine.set_playing(True)
    tape = Tape(engine)
    tape.play(20)
    engine.send_master(snapshot.generation, 1.0, False)
    tape.play(2)
    switching, off = tape.heard(20, 1)[:, 0], tape.heard(21, 1)[:, 0]
    assert (np.diff(switching.astype(np.float64)) >= 0).all()
    assert (off == np.float32(2.0)).all(), "past full scale, untouched, and in time"
