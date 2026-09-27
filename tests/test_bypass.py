"""A bypassed channel's pan, and the master's gain (05, *HRTF bypass*, *Pan
law*, *The master bus*; D-125, D-126). Headless: the engine block by block.

A mono clip and a stereo clip are panned by different laws, and one channel
can hold both, so the tests here place them by kind.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hearing import Tape, listen
from immersive.audio.dsp import balance, pan_law
from immersive.audio.engine import Engine
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.scheduler import Snapshot, build, gains
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Master, MediaFile, Project

Audio = npt.NDArray[np.float32]
BLOCK = 256
FRAMES = 16 * BLOCK


@pytest.fixture(scope="module")
def bank() -> Iterator[Bank]:
    from test_spatial import head

    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    with tempfile.TemporaryDirectory() as cache:
        made = prepare(head(), BLOCK, Path(cache))
        assert isinstance(made, Bank)
        yield made
    patch.undo()


def noise(sides: int, seed: int, frames: int = FRAMES) -> Audio:
    """Quiet enough that nothing downstream turns it down."""
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.4, 0.4, (frames, sides)).astype(np.float32)
    audio.flags.writeable = False
    return audio


def with_clips(
    *samples: Audio, bypass: bool = True, pan: float = 0.0
) -> tuple[Project, dict[str, Decoded]]:
    """One channel playing each sample from 0, together."""
    project = Project()
    store: dict[str, Decoded] = {}
    clips = []
    for n, audio in enumerate(samples):
        media = MediaFile(
            f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", 48_000, audio.shape[1], len(audio)
        )
        project.media_pool.append(media)
        store[media.id] = Decoded(audio, 48_000)
        clips.append(Clip(f"k-0000000{n}", media.id, 0, 0, len(audio)))
    project.channels.append(
        Channel("c-00000001", "C", "#A855F7", hrtf_bypass=bypass, pan=pan, clips=clips)
    )
    return project, store


def started(
    project: Project, store: dict[str, Decoded], bank: Bank | None = None
) -> tuple[Engine, Snapshot]:
    engine = Engine(BLOCK)
    snapshot = build(project, store.get, None, bank)
    engine.install(snapshot)
    engine.set_playing(True)
    return engine, snapshot


def db(value: float) -> float:
    return 20.0 * math.log10(value)


# --------------------------------------------------------------------------- #
# the pan law and the balance
# --------------------------------------------------------------------------- #


def test_a_bypassed_stereo_channel_at_centre_is_its_samples_bit_for_bit(
    bank: Bank,
) -> None:
    """With a bank, so the channel could have been placed: it never met a
    transform, or it would not be exact."""
    audio = noise(2, 1)
    engine, snapshot = started(*with_clips(audio), bank)
    assert snapshot.slots == (-1,)
    np.testing.assert_array_equal(listen(engine, 8), audio[: 8 * BLOCK])


def test_a_mono_bypassed_channel_hard_left_is_silent_on_the_right() -> None:
    audio = noise(1, 2)
    engine, _ = started(*with_clips(audio, pan=-1.0))
    out = listen(engine, 4)
    np.testing.assert_array_equal(out[:, 0], audio[: 4 * BLOCK, 0])
    assert not out[:, 1].any()


def test_a_mono_bypassed_channel_at_centre_is_3_01_db_down_on_each_side() -> None:
    audio = noise(1, 3)
    engine, _ = started(*with_clips(audio))
    out = listen(engine, 4).astype(np.float64)
    source = audio[: 4 * BLOCK, 0].astype(np.float64)
    for side in (0, 1):
        ratio = float(np.sqrt(np.mean(out[:, side] ** 2) / np.mean(source**2)))
        assert db(ratio) == pytest.approx(-3.0103, abs=1e-4)
    np.testing.assert_array_equal(out[:, 0], out[:, 1])


def test_a_channel_holding_mono_and_stereo_clips_pans_each_by_its_own_law() -> None:
    mono, stereo = noise(1, 4), noise(2, 5)
    engine, _ = started(*with_clips(mono, stereo, pan=0.5))
    out = listen(engine, 4).astype(np.float64)
    frames = 4 * BLOCK
    (mono_l, mono_r), (left, right) = pan_law(0.5), balance(0.5)
    m = mono[:frames, 0].astype(np.float64)
    expected_l = m * mono_l + stereo[:frames, 0] * left
    expected_r = m * mono_r + stereo[:frames, 1] * right
    np.testing.assert_allclose(out[:, 0], expected_l, atol=1e-6)
    np.testing.assert_allclose(out[:, 1], expected_r, atol=1e-6)
    assert right == 1.0, "the balance leaves the side panned towards alone"


def test_a_pan_change_ramps_across_one_block() -> None:
    held = np.full((FRAMES, 1), 0.5, dtype=np.float32)
    project, store = with_clips(held)
    engine, snapshot = started(project, store)
    tape = Tape(engine)
    tape.play()
    project.channels[0].pan = -1.0
    engine.send_gain(snapshot.generation, 0, gains(project)[0])
    tape.play(2)
    right = tape.heard(1, 2)[:, 1].astype(np.float64)
    centre = 0.5 * math.sin(math.pi / 4)
    steps = np.diff(np.concatenate([[centre], right[:BLOCK]]))
    np.testing.assert_allclose(steps, -centre / BLOCK, atol=1e-6)
    assert right[BLOCK - 1] == 0.0, "the block's last sample lands on it"
    assert not right[BLOCK:].any()


def test_pan_does_nothing_to_a_channel_that_is_not_bypassed() -> None:
    audio = noise(1, 6)
    project, store = with_clips(audio, bypass=False, pan=-1.0)
    assert gains(project) == [(1.0, 1.0, 1.0, 1.0)]
    engine, _ = started(project, store)
    out = listen(engine, 4)
    np.testing.assert_array_equal(out[:, 0], audio[: 4 * BLOCK, 0])
    np.testing.assert_array_equal(out[:, 1], audio[: 4 * BLOCK, 0])


# --------------------------------------------------------------------------- #
# the master gain
# --------------------------------------------------------------------------- #


def test_the_master_gain_ramps_the_whole_bus_across_one_block() -> None:
    held = np.full((FRAMES, 2), 0.5, dtype=np.float32)
    project, store = with_clips(held)
    engine, snapshot = started(project, store)
    tape = Tape(engine)
    tape.play()
    assert engine.send_master(snapshot.generation, 0.5, True)
    tape.play(2)
    out = tape.heard(1, 2).astype(np.float64)
    expected = 0.5 * (1.0 - 0.5 * np.arange(1, BLOCK + 1) / BLOCK)
    np.testing.assert_allclose(out[:BLOCK, 0], expected, atol=1e-6)
    np.testing.assert_allclose(out[:BLOCK, 1], expected, atol=1e-6)
    assert (out[BLOCK:] == np.float32(0.25)).all()


def test_the_snapshot_carries_the_master_and_a_stale_command_is_dropped() -> None:
    held = np.full((FRAMES, 2), 0.5, dtype=np.float32)
    project, store = with_clips(held)
    project.master = Master(gain_db=-6.0206, limiter_on=True)
    engine, snapshot = started(project, store)
    engine.send_master(snapshot.generation + 1, 2.0, True)  # stale: dropped
    out = listen(engine, 2)
    assert snapshot.master.tolist() == [pytest.approx(0.5, abs=1e-5), 1.0]
    np.testing.assert_allclose(out, 0.25, atol=1e-5)  # from the first sample
