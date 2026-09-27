"""The spatial path (05, *Per-block processing*): each non-bypassed channel
heard from where it is. Headless.

A synthetic head stands in for SADIE II D1: 400 directions, each ear's
response a smooth pulse delayed by 30·x samples on the far side and louder
on the near side, so front, left and right can be told apart by
measurement. The bank is prepared once per module, with the direction
index at test size.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.engine import Engine
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.hrtf.sofa import HrirSet
from immersive.audio.scheduler import build
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, MediaFile, Position, Project

BLOCK = 256
TAPS = 128
Audio = npt.NDArray[np.float32]


def fibonacci(count: int) -> npt.NDArray[np.float64]:
    index = np.arange(count) + 0.5
    z = 1.0 - 2.0 * index / count
    azimuth = np.pi * (1.0 + 5.0**0.5) * index
    ring = np.sqrt(1.0 - z * z)
    return np.column_stack([ring * np.cos(azimuth), ring * np.sin(azimuth), z])


def pulse(at: float) -> npt.NDArray[np.float64]:
    base = np.zeros(TAPS)
    base[:9] = np.hanning(11)[1:10]
    k = np.arange(TAPS // 2 + 1)
    return np.fft.irfft(
        np.fft.rfft(base) * np.exp(-2j * np.pi * k * (at - 4.0) / TAPS), n=TAPS
    )


def head() -> HrirSet:
    """A source at +X reaches the right ear first and louder, as a head's."""
    directions = fibonacci(400)
    x = directions[:, 0]
    responses = np.stack(
        [
            [
                (1.0 - 0.4 * xi) * pulse(20 + 15 * (1 + xi)),
                (1.0 + 0.4 * xi) * pulse(20 + 15 * (1 - xi)),
            ]
            for xi in x
        ]
    ).astype(np.float32)
    return HrirSet(
        title="synthetic head",
        licence="",
        database="",
        directions=directions,
        responses=responses,
        delays=np.zeros((400, 2)),
        source_rate=48_000,
        gain=1.0,
        hash="sha256:" + "5e" * 32,
    )


@pytest.fixture(scope="module")
def bank() -> Iterator[Bank]:
    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    with tempfile.TemporaryDirectory() as cache:
        made = prepare(head(), BLOCK, Path(cache))
        assert isinstance(made, Bank)
        yield made
    patch.undo()


# --------------------------------------------------------------------------- #
# a project, played
# --------------------------------------------------------------------------- #


def empty() -> tuple[Project, dict[str, Decoded]]:
    return Project(), {}


def channel_with(
    project: Project,
    store: dict[str, Decoded],
    audio: npt.NDArray[np.float64],
    where: tuple[float, float, float],
    *,
    bypass: bool = False,
) -> Channel:
    n = len(project.channels)
    media = MediaFile(
        f"m-{n:08x}", f"/{n}.wav", f"{n}.wav", 48_000, audio.ndim, len(audio)
    )
    samples = audio.astype(np.float32).reshape(len(audio), -1)
    store[media.id] = Decoded(np.ascontiguousarray(samples), 48_000)
    project.media_pool.append(media)
    channel = Channel(
        f"c-{n:08x}",
        f"C{n}",
        "#A855F7",
        hrtf_bypass=bypass,
        position=Position(*where),
        clips=[Clip(f"k-{n:08x}", media.id, 0, 0, len(audio))],
    )
    project.channels.append(channel)
    return channel


def played(
    project: Project, store: dict[str, Decoded], bank: Bank | None, blocks: int
) -> Audio:
    """`blocks` blocks of the engine playing `project` from 0: `(n, 2)`."""
    engine = Engine(BLOCK)
    engine.install(build(project, store.get, None, bank))
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    rendered = []
    for _ in range(blocks):
        engine.process(out)
        rendered.append(out.copy())
    return np.concatenate(rendered)


def impulse(frames: int = 4 * BLOCK, at: int = 0) -> npt.NDArray[np.float64]:
    out = np.zeros(frames)
    out[at] = 1.0
    return out


def first_arrival(side: npt.NDArray[np.float32]) -> float:
    return float(np.argmax(np.abs(side) > 0.05 * np.abs(side).max()))


# --------------------------------------------------------------------------- #
# what is heard
# --------------------------------------------------------------------------- #


def test_an_impulse_at_a_measured_direction_is_that_directions_pair(bank: Bank) -> None:
    """Its minimum-phase pair, with the ITD on the far ear, to float32."""
    vertex = int(np.argmax(bank.directions[:, 0]))  # the most +X measurement
    direction = tuple(float(v) for v in bank.directions[vertex])
    project, store = empty()
    channel_with(project, store, impulse(), direction)  # type: ignore[arg-type]

    heard = played(project, store, bank, 3)

    itd = float(bank.itd[vertex])
    assert itd > 10.0, "a source on the right: the left ear is far"
    ramp = np.exp(-2j * np.pi * np.arange(bank.nfft // 2 + 1) * itd / bank.nfft)
    expected_left = np.fft.irfft(bank.filters[vertex, 0] * ramp, n=bank.nfft)
    expected_right = np.fft.irfft(bank.filters[vertex, 1], n=bank.nfft)
    length = bank.nfft
    np.testing.assert_allclose(heard[:length, 0], expected_left, atol=2e-6)
    np.testing.assert_allclose(heard[:length, 1], expected_right, atol=2e-6)


def level_db(side: npt.NDArray[np.float32]) -> float:
    return float(10 * np.log10(np.sum(side.astype(np.float64) ** 2)))


def test_ahead_both_ears_hear_alike_and_either_side_is_heard_there(bank: Bank) -> None:
    """Alike, not identical: straight ahead blends three measurements of a
    sphere that is not mirror-symmetric, so the ears differ by 1e-4."""
    ears = {}
    for name, where in (
        ("front", (0.0, 1.0, 0.0)),
        ("right", (1.0, 0.0, 0.0)),
        ("left", (-1.0, 0.0, 0.0)),
    ):
        project, store = empty()
        channel_with(project, store, impulse(), where)
        ears[name] = played(project, store, bank, 3)

    front = ears["front"]
    assert level_db(front[:, 0]) == pytest.approx(level_db(front[:, 1]), abs=0.05)
    assert first_arrival(front[:, 0]) == pytest.approx(
        first_arrival(front[:, 1]), abs=1
    )
    for near, far, name in ((1, 0, "right"), (0, 1, "left")):
        heard = ears[name]
        assert level_db(heard[:, near]) > level_db(heard[:, far]) + 3.0, name
        assert first_arrival(heard[:, near]) + 20 < first_arrival(heard[:, far]), name


@pytest.mark.parametrize("rolloff", [1.0, 2.0])
def test_distance_follows_its_law_and_stops_at_the_minimum(
    bank: Bank, rolloff: float
) -> None:
    def level(distance: float) -> float:
        project, store = empty()
        project.distance.rolloff = rolloff
        channel_with(project, store, impulse(), (0.0, distance, 0.0))
        return float(np.sqrt(np.mean(played(project, store, bank, 3) ** 2)))

    halved = 20 * np.log10(level(1.0) / level(2.0))
    assert halved == pytest.approx(rolloff * 6.0206, abs=0.01)
    assert level(0.1) == pytest.approx(level(0.2)), "inside min_distance, no louder"


def test_four_channels_together_are_the_four_alone_added(bank: Bank) -> None:
    """Summed in the frequency domain: linear, so it must be exact."""
    rng = np.random.default_rng(2)
    placed = [(0.3, 0.9, 0.1), (-0.8, 0.2, 0.5), (0.1, -0.7, -0.6), (0.9, 0.1, 0.0)]
    signals = [rng.uniform(-0.3, 0.3, 4 * BLOCK) for _ in placed]

    together_project, together_store = empty()
    for audio, where in zip(signals, placed, strict=True):
        channel_with(together_project, together_store, audio, where)
    together = played(together_project, together_store, bank, 4)

    alone = np.zeros_like(together)
    for audio, where in zip(signals, placed, strict=True):
        project, store = empty()
        channel_with(project, store, audio, where)
        alone += played(project, store, bank, 4)
    np.testing.assert_allclose(together, alone, atol=1e-5)


def test_a_stereo_channel_is_placed_as_its_average(bank: Bank) -> None:
    rng = np.random.default_rng(5)
    left, right = rng.uniform(-0.3, 0.3, (2, 4 * BLOCK))
    stereo_project, stereo_store = empty()
    channel_with(
        stereo_project, stereo_store, np.stack([left, right], 1), (0.5, 0.5, 0.0)
    )
    mono_project, mono_store = empty()
    channel_with(mono_project, mono_store, (left + right) / 2, (0.5, 0.5, 0.0))
    np.testing.assert_allclose(
        played(stereo_project, stereo_store, bank, 4),
        played(mono_project, mono_store, bank, 4),
        atol=1e-6,
    )


def test_a_bypassed_channel_plays_as_it_did_before(bank: Bank) -> None:
    rng = np.random.default_rng(6)
    audio = rng.uniform(-0.3, 0.3, 4 * BLOCK)
    project, store = empty()
    channel_with(project, store, audio, (1.0, 0.0, 0.0), bypass=True)
    flat = played(project, store, None, 4)
    np.testing.assert_array_equal(played(project, store, bank, 4), flat)


def test_without_a_bank_every_channel_is_flat(bank: Bank) -> None:
    project, store = empty()
    channel_with(project, store, impulse(), (1.0, 0.0, 0.0))
    flat = played(project, store, None, 2)
    assert flat[0, 0] == flat[0, 1] == 1.0, "straight through, both sides"


# --------------------------------------------------------------------------- #
# moving, seeking, stopping
# --------------------------------------------------------------------------- #


def test_a_position_sent_is_heard_at_the_next_block(bank: Bank) -> None:
    project, store = empty()
    channel_with(project, store, np.full(8 * BLOCK, 0.2), (0.0, 1.0, 0.0))
    engine = Engine(BLOCK)
    snapshot = build(project, store.get, None, bank)
    engine.install(snapshot)
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    engine.process(out)
    engine.send_position(snapshot.generation, 0, 2.0, 0.0, 0.0)
    engine.send_position(snapshot.generation + 5, 0, 9.0, 9.0, 9.0)  # stale: dropped
    engine.process(out)
    np.testing.assert_array_equal(snapshot.positions[0], [2.0, 0.0, 0.0])


def after_moving_and_seeking(
    bank: Bank, audio: npt.NDArray[np.float64]
) -> npt.NDArray[np.float32]:
    """Three blocks ahead, then moved to +X and sought to 8 blocks in: the
    block that follows."""
    project, store = empty()
    channel_with(project, store, audio, (0.0, 1.0, 0.0))
    engine = Engine(BLOCK)
    snapshot = build(project, store.get, None, bank)
    engine.install(snapshot)
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    for _ in range(3):
        engine.process(out)
    engine.send_position(snapshot.generation, 0, 1.0, 0.0, 0.0)
    engine.seek(8 * BLOCK)
    engine.process(out)
    return out.copy()


def test_the_first_block_after_a_seek_crossfades_from_nothing_stale(bank: Bank) -> None:
    """By linearity, the block after the seek is a fresh engine's at the new
    place, plus the tail still sounding from before. A crossfade from the
    stale filter would add its fading-out half at the old place."""
    rng = np.random.default_rng(8)
    audio = rng.uniform(-0.3, 0.3, 16 * BLOCK)
    moved = after_moving_and_seeking(bank, audio)

    silent_after = audio.copy()
    silent_after[8 * BLOCK :] = 0.0
    tail = after_moving_and_seeking(bank, silent_after)  # the old tail alone

    fresh_project, fresh_store = empty()
    channel_with(fresh_project, fresh_store, audio[8 * BLOCK :], (1.0, 0.0, 0.0))
    fresh = played(fresh_project, fresh_store, bank, 1)
    np.testing.assert_allclose(moved, fresh + tail, atol=1e-5)


def after_a_swap(bank: Bank, audio: npt.NDArray[np.float64]) -> npt.NDArray[np.float32]:
    """Three blocks ahead, then the channel moved to +X by a snapshot built
    and installed, as the feed installs one: the block that follows."""
    project, store = empty()
    channel = channel_with(project, store, audio, (0.0, 1.0, 0.0))
    engine = Engine(BLOCK)
    snapshot = build(project, store.get, None, bank)
    engine.install(snapshot)
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    for _ in range(3):
        engine.process(out)
    channel.position = Position(1.0, 0.0, 0.0)
    engine.install(build(project, store.get, snapshot, bank))
    engine.process(out)
    return out.copy()


def test_the_first_block_after_a_swap_crossfades_from_nothing_stale(bank: Bank) -> None:
    """The seek's test, for a snapshot swap. A new snapshot's first block is
    the old one's tail carried across, plus this block heard at the new
    place through its filter alone. Both are measured against an engine
    that never swapped: one kept at the old place, and one at the new place
    since before this block's input began, whose filter is steady there
    whether or not a first block is fresh."""
    rng = np.random.default_rng(9)
    audio = rng.uniform(-0.3, 0.3, 8 * BLOCK)
    silent_after = audio.copy()
    silent_after[3 * BLOCK :] = 0.0
    silent_before = audio.copy()
    silent_before[: 3 * BLOCK] = 0.0

    tail = after_a_swap(bank, silent_after)
    kept_project, kept_store = empty()
    channel_with(kept_project, kept_store, silent_after, (0.0, 1.0, 0.0))
    unswapped = played(kept_project, kept_store, bank, 4)[3 * BLOCK :]
    assert np.abs(unswapped).max() > 0.01, "there is a tail to carry"
    np.testing.assert_allclose(tail, unswapped, atol=1e-6)

    steady_project, steady_store = empty()
    channel_with(steady_project, steady_store, silent_before, (1.0, 0.0, 0.0))
    steady = played(steady_project, steady_store, bank, 4)[3 * BLOCK :]
    np.testing.assert_allclose(after_a_swap(bank, audio), steady + tail, atol=1e-5)


def test_stopped_the_tail_drains_and_is_not_replayed(bank: Bank) -> None:
    project, store = empty()
    channel_with(project, store, impulse(at=BLOCK - 1), (1.0, 0.0, 0.0))
    engine = Engine(BLOCK)
    engine.install(build(project, store.get, None, bank))
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    engine.process(out)  # the impulse, at the block's last sample
    engine.set_playing(False)
    engine.process(out)
    assert np.abs(out).max() > 0.01, "stopped: the decay still sounds"
    engine.set_playing(True)
    engine.seek(4 * BLOCK)  # silence from here
    engine.process(out)
    assert np.abs(out).max() < 1e-6, "and is not heard again"


def test_a_spatial_channels_meter_reads_it_after_its_distance(bank: Bank) -> None:
    project, store = empty()
    channel_with(project, store, np.full(4 * BLOCK, 0.4), (0.0, 2.0, 0.0))
    engine = Engine(BLOCK)
    engine.install(build(project, store.get, None, bank))
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    engine.process(out)
    [(_, left, right)] = engine.take_channel_peaks()
    assert left == right == pytest.approx(0.2, rel=1e-6), "0.4 at half the level"


# --------------------------------------------------------------------------- #
# the crossfade, measured (D-37, the roadmap's named test)
# --------------------------------------------------------------------------- #


def band_limited_sawtooth(freq: float, frames: int) -> npt.NDArray[np.float64]:
    """S0's: summed from the harmonics below Nyquist. A naive sawtooth's
    aliasing raised the crossfaded render's floor by 22 dB and would read as
    the crossfade failing."""
    t = np.arange(frames) / 48_000
    out = np.zeros(frames)
    for k in range(1, int(24_000 / freq) + 1):
        out -= np.sin(2 * np.pi * freq * k * t) / k
    return out * 0.2 / np.pi


def sideband_db(signal: npt.NDArray[np.float64], carrier: float, rate: float) -> float:
    """Block-rate sidebands round `carrier`, in dB below it: a filter that
    switches every block puts its artefact at carrier +- n times the block rate,
    and nowhere else (S0's measure)."""
    power = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) ** 2
    freqs = np.fft.rfftfreq(len(signal), 1 / 48_000)

    def band(centre: float) -> float:
        return float(power[(freqs > centre - 4) & (freqs < centre + 4)].sum())

    sides = sum(
        band(carrier + n * rate) + band(carrier - n * rate) for n in range(1, 5)
    )
    return 10 * np.log10(sides / band(carrier))


def orbiting(bank: Bank, *, crossfade: bool) -> npt.NDArray[np.float32]:
    """Two seconds of the sawtooth orbiting the head once a second."""
    blocks = 2 * 48_000 // BLOCK
    project, store = empty()
    channel_with(
        project, store, band_limited_sawtooth(440.0, blocks * BLOCK), (0.0, 1.0, 0.0)
    )
    engine = Engine(BLOCK)
    snapshot = build(project, store.get, None, bank)
    assert snapshot.space is not None
    snapshot.space.crossfade = crossfade
    engine.install(snapshot)
    engine.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    rendered = []
    for n in range(blocks):
        turn = 2 * np.pi * n * BLOCK / 48_000
        engine.send_position(snapshot.generation, 0, np.sin(turn), np.cos(turn), 0.0)
        engine.process(out)
        rendered.append(out[:, 0].copy())
    return np.concatenate(rendered)


def test_the_crossfade_cuts_the_block_rate_sidebands_by_20_db(bank: Bank) -> None:
    """S0's line, and its proof that the crossfade is running at all: the
    same orbit with it switched off must be audibly - measurably - worse."""
    rate = 48_000 / BLOCK
    crossfaded = sideband_db(orbiting(bank, crossfade=True).astype(float), 440.0, rate)
    plain = sideband_db(orbiting(bank, crossfade=False).astype(float), 440.0, rate)
    assert plain - crossfaded >= 20.0, (crossfaded, plain)
