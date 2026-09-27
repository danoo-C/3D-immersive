"""Level as mixed (M4 phase 8; D-128 to D-131): a placed channel as loud as
the same channel played flat, wherever it is, until distance takes it away.
Headless: the engine through `test_spatial`'s synthetic head.

Loudness is measured as BS.1770 weights it: pink noise, K-weighted, summed
over both ears. "Played flat" is the channel as the engine plays it without
placing it: a mono clip to both ears.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hearing import listen
from immersive.audio.engine import Engine
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.scheduler import build
from immersive.core.io.loudness import pink_power, pink_weights, weighted_power
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Master, MediaFile, Position, Project

BLOCK = 256
Audio = npt.NDArray[np.float32]


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


def pink(seconds: float, seed: int = 0) -> Audio:
    """Pink noise, mono, at about -20 dBFS RMS."""
    frames = int(seconds * 48_000)
    spectrum = np.fft.rfft(np.random.default_rng(seed).standard_normal(frames))
    frequencies = np.fft.rfftfreq(frames, 1 / 48_000)
    spectrum[1:] /= np.sqrt(frequencies[1:])
    spectrum[0] = 0.0
    noise = np.fft.irfft(spectrum, frames)
    return (0.1 * noise / noise.std()).astype(np.float32)[:, None]


def placed(
    bank: Bank,
    sample: Audio | Decoded,
    where: Position,
    blocks: int,
    *,
    bypass: bool = False,
    **distance: object,
) -> Audio:
    """`sample` on one channel at `where`, heard for `blocks` blocks."""
    decoded = sample if isinstance(sample, Decoded) else Decoded(sample, 48_000)
    audio = decoded.audio
    media = MediaFile(
        "m-00000001", "/a.wav", "a.wav", 48_000, audio.shape[1], len(audio)
    )
    project = Project(
        media_pool=[media],
        master=Master(limiter_on=False),
        channels=[
            Channel(
                "c-00000001",
                "C",
                "#A855F7",
                position=where,
                hrtf_bypass=bypass,
                clips=[Clip("k-00000001", media.id, 0, 0, len(audio))],
            )
        ],
    )
    for name, value in distance.items():
        setattr(project.distance, name, value)
    engine = Engine(BLOCK)
    engine.install(build(project, {media.id: decoded}.get, None, bank))
    engine.set_playing(True)
    return listen(engine, blocks)


def loudness(out: Audio) -> float:
    """Both ears, K-weighted, in dB."""
    return 10 * math.log10(
        weighted_power(out[:, 0].astype(np.float64))
        + weighted_power(out[:, 1].astype(np.float64))
    )


def flat(audio: Audio, frames: int) -> float:
    """The same mono clip played flat: to both ears, as it is."""
    return 10 * math.log10(2 * weighted_power(audio[:frames, 0].astype(np.float64)))


# --------------------------------------------------------------------------- #
# the set, calibrated (D-128)
# --------------------------------------------------------------------------- #


def test_pink_noise_straight_ahead_is_as_loud_as_played_flat(bank: Bank) -> None:
    noise = pink(3.0)
    blocks = len(noise) // BLOCK - 1
    out = placed(bank, noise, Position(0.0, 1.0, 0.0), blocks)
    assert loudness(out) - flat(noise, len(out)) == pytest.approx(0.0, abs=0.1)
    assert bank.calibration != 0.0, "the head was not already at flat"


def test_it_is_straight_ahead_that_is_calibrated(tmp_path: Path) -> None:
    """A head half again as loud in front as at its poles and sides: only a
    calibration made in front leaves the front as loud as flat."""
    from dataclasses import replace

    from test_spatial import head

    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    try:
        plain = head()
        louder = (1.0 + 0.5 * np.maximum(plain.directions[:, 1], 0.0)).astype(
            np.float32
        )
        front_heavy = replace(
            plain,
            responses=plain.responses * louder[:, None, None],
            hash="sha256:" + "f7" * 32,
        )
        made = prepare(front_heavy, BLOCK, tmp_path)
    finally:
        patch.undo()
    assert isinstance(made, Bank)
    noise = pink(3.0, seed=1)
    out = placed(made, noise, Position(0.0, 1.0, 0.0), len(noise) // BLOCK - 1)
    assert loudness(out) - flat(noise, len(out)) == pytest.approx(0.0, abs=0.1)


def test_evening_makes_every_measured_direction_as_loud_as_straight_ahead(
    bank: Bank,
) -> None:
    weights = pink_weights(bank.nfft)
    each = pink_power(bank.filters, weights).sum(axis=1)
    np.testing.assert_allclose(each * bank.evening**2, 2 * weights.sum(), rtol=1e-5)
    # The head's sides are louder than its front, (1 - 0.4x)² + (1 + 0.4x)².
    assert bank.evening.min() < 0.95, "so there is something to even out"


# --------------------------------------------------------------------------- #
# the fold (D-129)
# --------------------------------------------------------------------------- #


def written(tmp_path: Path, audio: Audio) -> Decoded:
    """`audio` through a file and back, as an import decodes it."""
    import soundfile

    from immersive.core.io.media import decode

    path = tmp_path / "stem.wav"
    soundfile.write(path, audio, 48_000, subtype="FLOAT")
    decoded = decode(path)
    assert isinstance(decoded, Decoded)
    return decoded


def test_a_placed_stereo_file_is_as_loud_as_played_flat(
    bank: Bank, tmp_path: Path
) -> None:
    """Two unrelated sides lose 3 dB folded, and get it back."""
    sides = np.hstack([pink(3.0, seed=2), pink(3.0, seed=3)])
    decoded = written(tmp_path, sides)
    assert 20 * math.log10(decoded.fold) == pytest.approx(3.0, abs=0.1)
    out = placed(bank, decoded, Position(0.0, 1.0, 0.0), len(sides) // BLOCK - 1)
    frames = len(out)
    as_it_is = 10 * math.log10(
        weighted_power(sides[:frames, 0].astype(np.float64))
        + weighted_power(sides[:frames, 1].astype(np.float64))
    )
    assert loudness(out) - as_it_is == pytest.approx(0.0, abs=0.1)


def test_a_fold_past_6_db_is_given_back_6_db(bank: Bank, tmp_path: Path) -> None:
    side = pink(2.0, seed=4)
    opposite = written(tmp_path, np.hstack([side, -0.9 * side]))
    assert opposite.fold == 2.0
    unfolded = Decoded(opposite.audio, 48_000)
    blocks = len(side) // BLOCK - 1
    given = placed(bank, opposite, Position(0.0, 1.0, 0.0), blocks)
    kept = placed(bank, unfolded, Position(0.0, 1.0, 0.0), blocks)
    assert loudness(given) - loudness(kept) == pytest.approx(6.02, abs=0.01)


def test_a_mono_file_has_nothing_to_give_back(tmp_path: Path) -> None:
    assert written(tmp_path, pink(1.0, seed=5)).fold == 1.0


def test_a_bypassed_stereo_channel_is_untouched_by_its_fold(bank: Bank) -> None:
    sides = np.hstack([pink(1.0, seed=6), pink(1.0, seed=7)])
    sides.flags.writeable = False
    out = placed(
        bank,
        Decoded(sides, 48_000, 1.7),
        Position(),
        len(sides) // BLOCK - 1,
        bypass=True,
    )
    np.testing.assert_array_equal(out, sides[: len(out)])


# --------------------------------------------------------------------------- #
# the centre (D-130)
# --------------------------------------------------------------------------- #


def ears(out: Audio) -> tuple[float, int]:
    """The difference between the ears, right over left in dB, and the lag
    of the right ear behind the left, in samples, by cross-correlation."""
    left, right = out[:, 0].astype(np.float64), out[:, 1].astype(np.float64)
    difference = 10 * math.log10(weighted_power(right) / weighted_power(left))
    lags = range(-40, 41)
    trimmed = slice(40, len(left) - 40)
    lag = max(
        lags, key=lambda k: float(np.dot(left[trimmed], np.roll(right, -k)[trimmed]))
    )
    return difference, lag


def test_at_the_listener_a_placed_channel_is_played_flat(bank: Bank) -> None:
    """No filter, no delay between the ears: the channel as it is (D-130)."""
    noise = pink(1.0, seed=8)
    out = placed(bank, noise, Position(), len(noise) // BLOCK - 1)
    np.testing.assert_allclose(out[:, 0], noise[: len(out), 0], atol=1e-5)
    np.testing.assert_allclose(out[:, 1], noise[: len(out), 0], atol=1e-5)


@pytest.mark.parametrize("side", [1.0, -1.0])
def test_a_centimetre_either_side_of_the_listener_is_nearly_the_middle(
    bank: Bank, side: float
) -> None:
    """Where it flipped from ear to ear (the first report), it now passes
    through the middle; at the minimum distance it is fully placed."""
    noise = pink(1.0, seed=9)
    blocks = len(noise) // BLOCK - 1
    near_difference, near_lag = ears(
        placed(bank, noise, Position(0.01 * side, 0, 0), blocks)
    )
    assert abs(near_difference) < 1.0 and abs(near_lag) <= 2
    at_edge = ears(placed(bank, noise, Position(0.2 * side, 0, 0), blocks))
    at_a_metre = ears(placed(bank, noise, Position(1.0 * side, 0, 0), blocks))
    assert at_edge[0] == pytest.approx(at_a_metre[0], abs=0.01)
    assert at_edge[1] == at_a_metre[1] and abs(at_edge[1]) > 20
    assert math.copysign(1.0, at_edge[0]) == side, "louder on its own side"


def test_moving_out_of_the_centre_steps_no_more_than_standing_still(bank: Bank) -> None:
    """A 200 Hz tone carried from the listener to 0.3 m, a centimetre a block:
    no sample jumps further than it does from a source that stays put."""
    tone = (0.25 * np.sin(2 * np.pi * 200 * np.arange(48_000) / 48_000)).astype(
        np.float32
    )[:, None]
    media = MediaFile("m-00000001", "/t.wav", "t.wav", 48_000, 1, len(tone))
    project = Project(
        media_pool=[media],
        master=Master(limiter_on=False),
        channels=[
            Channel(
                "c-00000001",
                "C",
                "#A855F7",
                clips=[Clip("k-00000001", media.id, 0, 0, len(tone))],
            )
        ],
    )
    engine = Engine(BLOCK)
    snapshot = build(project, {media.id: Decoded(tone, 48_000)}.get, None, bank)
    engine.install(snapshot)
    engine.set_playing(True)
    from hearing import Tape

    tape = Tape(engine)
    for n in range(40):
        engine.send_position(snapshot.generation, 0, min(n * 0.01, 0.3), 0.0, 0.0)
        tape.play()
    moving = tape.heard(1, 38)
    still = placed(bank, tone, Position(0.3, 0.0, 0.0), 40)[BLOCK:]
    worst = max(float(np.abs(np.diff(moving[:, side])).max()) for side in (0, 1))
    steady = max(float(np.abs(np.diff(still[:, side])).max()) for side in (0, 1))
    assert worst <= 1.1 * max(steady, 2 * np.pi * 200 / 48_000 * 0.25)


# --------------------------------------------------------------------------- #
# the switch (D-131)
# --------------------------------------------------------------------------- #


def measured(bank: Bank, towards: tuple[float, float, float]) -> Position:
    """The measured direction nearest `towards`, as a position one metre out."""
    index = int(np.argmax(bank.directions @ np.array(towards)))
    x, y, z = (float(v) for v in bank.directions[index])
    return Position(x, y, z)


DIRECTIONS = [(1, 0, 0), (-1, 0, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (0.7, 0.7, 0)]


@pytest.mark.parametrize("towards", DIRECTIONS)
def test_on_every_measured_direction_nearer_than_a_metre_is_as_loud_as_flat(
    bank: Bank, towards: tuple[float, float, float]
) -> None:
    noise = pink(2.0, seed=10)
    blocks = len(noise) // BLOCK - 1
    where = measured(bank, towards)
    half = Position(where.x / 2, where.y / 2, where.z / 2)  # 0.5 m: no boost
    out = placed(bank, noise, half, blocks)
    assert loudness(out) - flat(noise, len(out)) == pytest.approx(0.0, abs=0.1)


def test_on_only_the_level_changes_not_the_delay_or_the_spectrum(bank: Bank) -> None:
    """Switched on, a measured direction's output is its switched-off output
    times one number: its evening gain."""
    noise = pink(1.0, seed=11)
    blocks = len(noise) // BLOCK - 1
    where = measured(bank, (1, 0, 0))
    index = int(np.argmax(bank.directions @ np.array((where.x, where.y, where.z))))
    on = placed(bank, noise, where, blocks)
    off = placed(bank, noise, where, blocks, keep_level=False)
    np.testing.assert_allclose(on, bank.evening[index] * off, atol=2e-6)
    assert bank.evening[index] < 0.95


@pytest.mark.parametrize(("distance", "down"), [(2.0, 6.02), (4.0, 12.04)])
def test_on_past_a_metre_distance_takes_it_down(
    bank: Bank, distance: float, down: float
) -> None:
    noise = pink(2.0, seed=12)
    blocks = len(noise) // BLOCK - 1
    near = placed(bank, noise, Position(0.0, 1.0, 0.0), blocks)
    far = placed(bank, noise, Position(0.0, distance, 0.0), blocks)
    assert loudness(near) - loudness(far) == pytest.approx(down, abs=0.01)


def test_off_nearer_is_louder_and_the_side_as_the_head_has_it(bank: Bank) -> None:
    noise = pink(2.0, seed=13)
    blocks = len(noise) // BLOCK - 1
    ahead_half = placed(bank, noise, Position(0.0, 0.5, 0.0), blocks, keep_level=False)
    ahead_one = placed(bank, noise, Position(0.0, 1.0, 0.0), blocks, keep_level=False)
    assert loudness(ahead_half) - loudness(ahead_one) == pytest.approx(6.02, abs=0.01)
    side = placed(bank, noise, measured(bank, (1, 0, 0)), blocks, keep_level=False)
    assert loudness(side) - flat(noise, len(side)) > 0.4, "the head's side is louder"
