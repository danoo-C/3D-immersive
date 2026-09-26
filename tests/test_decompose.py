"""Each measurement split into an ITD and a minimum-phase response (05, *2*;
D-69). Headless.

The synthetic pairs carry a band-limited pulse delayed in the frequency
domain, so a fractional delay is exact and the test measures the estimator,
not the stimulus. The real set is checked where it has been fetched.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.hrtf import decompose as module
from immersive.audio.hrtf.decompose import (
    AGREEMENT,
    Decomposed,
    decompose,
    itd,
    minimum_phase,
    onset_itd,
)
from immersive.audio.hrtf.sofa import HrirSet, builtin
from immersive.core.io.media import Refused

TAPS = 256
Pair = npt.NDArray[np.float32]


def pulse(at: float, taps: int = TAPS) -> npt.NDArray[np.float64]:
    """A smooth pulse centred on `at`, which may be fractional: a Hann-
    windowed shape, delayed as a phase ramp so the delay is exact."""
    base = np.zeros(taps)
    base[:9] = np.hanning(11)[1:10]
    spectrum = np.fft.rfft(base)
    k = np.arange(spectrum.shape[0])
    shift = at - 4.0
    return np.fft.irfft(spectrum * np.exp(-2j * np.pi * k * shift / taps), n=taps)


def pairs(*delays: tuple[float, float]) -> Pair:
    """`[M, 2, TAPS]`: each pair's left pulse at its first delay, right at
    its second, both after 40 samples of lead."""
    out = np.stack([[pulse(40 + left), pulse(40 + right)] for left, right in delays])
    return out.astype(np.float32)


def hrirs(responses: Pair, delays: npt.NDArray[np.float64] | None = None) -> HrirSet:
    count = responses.shape[0]
    return HrirSet(
        title="synthetic",
        licence="",
        database="",
        directions=np.tile([0.0, 1.0, 0.0], (count, 1)),
        responses=responses,
        delays=np.zeros((count, 2)) if delays is None else delays,
        source_rate=48_000,
        gain=1.0,
        hash="",
    )


def decomposed(result: Decomposed | Refused) -> Decomposed:
    assert isinstance(result, Decomposed), result
    return result


# --------------------------------------------------------------------------- #
# the ITD, by cross-correlation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("delay", [0.0, 0.3, 12.0, 12.25, 30.6])
def test_a_known_delay_comes_back_within_a_tenth_of_a_sample(delay: float) -> None:
    measured = itd(pairs((delay, 0.0), (0.0, delay)))
    assert measured[0] == pytest.approx(delay, abs=0.1), "left later: positive"
    assert measured[1] == pytest.approx(-delay, abs=0.1), "its mirror: negative"


def test_the_itd_is_the_datas_not_a_constant() -> None:
    """A constant tuned to SADIE's 39 would pass that set and fail this."""
    result = decomposed(decompose(hrirs(pairs((12.0, 0.0)))))
    assert result.max_itd == pytest.approx(12.0, abs=0.1)


def test_the_decomposed_itd_keeps_its_sign() -> None:
    """Signed, for phase 3 to interpolate: a magnitude would turn +30 and
    -30 across the median plane into 30, pointing the wrong way."""
    result = decomposed(decompose(hrirs(pairs((0.0, 12.0), (12.0, 0.0)))))
    assert result.itd[0] == pytest.approx(-12.0, abs=0.1)
    assert result.itd[1] == pytest.approx(12.0, abs=0.1)


def test_stored_delays_shift_the_itd_by_their_difference() -> None:
    delays = np.array([[5.0, 2.0]])
    result = decomposed(decompose(hrirs(pairs((10.0, 0.0)), delays)))
    assert result.itd[0] == pytest.approx(13.0, abs=0.1)


# --------------------------------------------------------------------------- #
# the cross-check (D-69)
# --------------------------------------------------------------------------- #


def disagreeing(count: int) -> Pair:
    """Pairs whose onsets and dominant arrivals point opposite ways: the
    left ear has a precursor above -10 dB early, and its peak late."""
    out = np.zeros((count, 2, TAPS))
    for m in range(count):
        out[m, 0] = 0.5 * pulse(20) + pulse(100)
        out[m, 1] = pulse(60)
    return out.astype(np.float32)


def test_the_two_estimates_can_point_opposite_ways() -> None:
    responses = disagreeing(1)
    assert itd(responses)[0] > 0 > onset_itd(responses)[0]


def test_a_set_whose_estimates_disagree_on_the_far_ear_is_refused() -> None:
    result = decompose(hrirs(disagreeing(10)))
    assert isinstance(result, Refused) and "mirrored" in result.reason


def test_the_cross_check_is_reported() -> None:
    result = decomposed(decompose(hrirs(pairs((12.0, 0.0), (0.0, 20.0)))))
    assert result.agreement == 1.0 >= AGREEMENT
    assert abs(result.median_difference) < 1.0


# --------------------------------------------------------------------------- #
# minimum phase, by the real cepstrum
# --------------------------------------------------------------------------- #


def decaying(count: int, seed: int = 4) -> Pair:
    """Responses shaped like a head's: noise decaying over a few ms, with a
    sharp notch in each - where cepstral aliasing lands."""
    rng = np.random.default_rng(seed)
    envelope = np.exp(-np.arange(TAPS) / 18.0)
    out = rng.standard_normal((count, 2, TAPS)) * envelope
    out[..., 1:] -= 0.95 * out[..., :-1]  # a deep notch near DC
    return out.astype(np.float32)


#: Where the magnitude is held to a tenth of a dB: within this far of each
#: response's own peak. Below it, 256 taps cannot hold a notch's full
#: depth. SADIE's deepest, 80.6 dB down, comes back 64.7 dB down, and every
#: error over 1 dB lies at least 53.6 dB below its peak (phase 2's Notes).
AUDIBLE_DB = 30.0


def errors(
    minimum: npt.NDArray[np.float32],
    source: npt.NDArray[np.float32],
    points: int = 8192,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Per bin from 100 Hz to 16 kHz: the magnitude error in dB, and how far
    below its own peak the source is there."""
    freqs = np.fft.rfftfreq(points, 1 / 48_000)
    band = (freqs >= 100) & (freqs <= 16_000)
    got = np.abs(np.fft.rfft(minimum.astype(np.float64), n=points, axis=-1))
    want = np.abs(np.fft.rfft(source.astype(np.float64), n=points, axis=-1))
    error = np.abs(20 * np.log10(np.maximum(got, 1e-12) / np.maximum(want, 1e-12)))
    depth = 20 * np.log10(np.maximum(want, 1e-12) / want.max(axis=-1, keepdims=True))
    return error[..., band], depth[..., band]


def test_the_magnitude_is_kept_within_a_tenth_of_a_db_where_it_can_be_heard() -> None:
    source = decaying(6)
    error, depth = errors(minimum_phase(source), source)
    assert error[depth > -AUDIBLE_DB].max() < 0.1


def test_the_energy_is_front_loaded_as_minimum_phase_must_be() -> None:
    minimum = minimum_phase(decaying(6)).astype(np.float64)
    energy = np.cumsum(minimum**2, axis=-1)
    share = energy[..., TAPS // 4 - 1] / energy[..., -1]
    assert share.min() > 0.9


def test_an_exact_null_does_not_come_back_nan() -> None:
    null = np.zeros((1, 2, TAPS), dtype=np.float32)
    null[:, :, 0] = 1.0
    null[:, :, 1] = -1.0  # zero at DC exactly
    assert np.isfinite(minimum_phase(null)).all()


def test_the_cepstral_nfft_is_the_measured_one() -> None:
    """32x the taps, with S0's table of aliasing beside it in the module."""
    assert module.MINIMUM_PHASE_NFFT == 8192
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "0.017 dB" in source and "5.489 dB" in source


# --------------------------------------------------------------------------- #
# SADIE II D1
# --------------------------------------------------------------------------- #


def test_sadie_ii_d1_decomposes_as_s0_heard_it() -> None:
    """One test, so the set is decomposed once: it takes seconds, and
    separate tests on separate workers each paid it again. Phase 4's cache
    is where it stops being paid at all."""
    loaded = builtin("sadie-d1")
    if isinstance(loaded, Refused):
        pytest.skip("SADIE II D1 is not fetched here: launch.py --install")
    sadie = decomposed(decompose(loaded))

    def nearest(direction: tuple[float, float, float]) -> int:
        return int(np.argmin(np.linalg.norm(sadie.directions - direction, axis=1)))

    # The cross-check, as S0 measured it (D-69).
    assert sadie.agreement >= AGREEMENT
    assert abs(sadie.median_difference) < 1.0
    assert sadie.p95_difference < 8.0

    # Zero ahead, behind and above; largest at the ears, and 39 at most.
    for direction in ((0, 1, 0), (0, -1, 0), (0, 0, 1)):
        assert abs(sadie.itd[nearest(direction)]) < 2.0
    largest = int(np.argmax(np.abs(sadie.itd)))
    assert abs(sadie.directions[largest, 0]) > 0.99, "on the interaural axis"
    assert int(np.ceil(sadie.max_itd)) == 39

    # A source on the right delays the left ear: the sign a mirrored mix
    # would get wrong everywhere at once.
    assert sadie.itd[nearest((1, 0, 0))] > 30.0
    assert sadie.itd[nearest((-1, 0, 0))] < -30.0

    # The magnitude, in all 17 604 responses: S0's twenty missed every deep
    # notch, where 256 taps cannot hold the floor. At 2048 points, 23 Hz
    # apart, which a 256-tap response's spectrum cannot hide a notch between.
    for first in range(0, sadie.source.count, 2000):
        error, depth = errors(
            sadie.minimum[first : first + 2000],
            sadie.source.responses[first : first + 2000],
            points=2048,
        )
        assert error[depth > -AUDIBLE_DB].max() < 0.1
        assert (depth[error > 1.0] < -50.0).all(), "only at the notches' floors"
