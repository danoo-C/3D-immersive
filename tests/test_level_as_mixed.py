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
