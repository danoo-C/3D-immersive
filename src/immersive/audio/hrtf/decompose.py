"""Each measurement split into a delay and a spectrum (05, *2. Split ITD
from spectrum*) - the step that makes or breaks the pipeline.

Two measurements a few degrees apart have different interaural delays, and
blending them sums near-identical signals at slightly different offsets:
comb filtering, a moving source that sounds flanged. So each is split once,
here, into two things that interpolate cleanly on their own:

- **the ITD**, a scalar per direction, by cross-correlating the ears (D-69).
  It is kept **signed**, positive when the left ear is the later, far one,
  because phase 3 interpolates it. Averaging magnitudes across the median
  plane would turn +30 and -30 into 30, a delay pointing the wrong way at
  full strength. Phase 5 turns it into a non-negative delay on the far ear;
- **the minimum-phase response** per ear, by the real cepstrum. It carries
  no delay at all.

The construction is S0 phase 2's, which was heard to work. The constants
below are its measured choices, with their measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy import signal

from immersive.audio.hrtf.sofa import HrirSet
from immersive.core.io.media import Refused
from immersive.core.time import SAMPLE_RATE

#: The ITD is a low-frequency cue. Above about 1.5 kHz head-shadow ripple
#: broadens the correlation peak, and S0 measured what that does: fullband,
#: the largest ITD on SADIE II D1's sphere is 44 samples, somewhere other
#: than the poles, which can only be a spurious peak. At 1.5 kHz it is 38,
#: at the interaural axis, where physics puts it. Zero-phase, so the filter
#: adds no delay of its own to what it measures.
ITD_LOWPASS_HZ: Final = 1500.0

#: Lags searched either way. The largest human ITD is about 50 samples at
#: 48 kHz: loose enough not to constrain it, tight enough to reject a peak
#: in the tail.
ITD_MAX_LAG: Final = 128

#: The onset cross-check's threshold, relative to each ear's own peak. S0's
#: plan said -20 dB, and on an unfiltered response that is in the
#: pre-ringing: agreement on the far ear fell to 73%. -10 dB is on the real
#: leading edge.
ONSET_DB: Final = -10.0

#: Where the cross-check applies: below this many samples of ITD there is no
#: side to get wrong.
SIDED: Final = 3.0

#: The share of sided directions whose two estimates must agree on the far
#: ear. S0 measured 99.99% on SADIE II D1. Below this, a set is mirrored,
#: its ears swapped, or its correlation peaks spurious.
AGREEMENT: Final = 0.99

#: The cepstrum's transform size, 32 times SADIE's 256 taps - and not the
#: convolution's `nfft` (phase 4), which has a different reason entirely.
#: The cepstrum must decay before it wraps its own buffer, and the log
#: magnitude of a deep pinna notch decays slowly, so the aliasing lands at
#: the nulls. S0, over 20 directions, worst error from 100 Hz to 16 kHz:
#:
#:     nfft  1024 (4x)   5.489 dB     39 bins over 0.5 dB
#:     nfft  2048 (8x)   4.490 dB      5 bins
#:     nfft  4096 (16x)  0.886 dB      1 bin
#:     nfft  8192 (32x)  0.017 dB      0 bins
MINIMUM_PHASE_NFFT: Final = 8192

#: One transform of a whole set at that size peaks at several GB; 512
#: measurements at a time is about 70 MB.
CHUNK: Final = 512

#: A notch's `log(0)` would make every tap NaN. Floored relative to each
#: response's own peak, so it does not depend on the set's level.
FLOOR_DB: Final = -100.0


@dataclass(frozen=True, eq=False)
class Decomposed:
    """A set split into delays and spectra, for phase 3 to interpolate."""

    source: HrirSet
    #: `[M]` samples at 48 kHz, positive when the left ear is far.
    itd: npt.NDArray[np.float64]
    #: `[M, 2, N]` float32: the minimum-phase part of each ear's response.
    minimum: npt.NDArray[np.float32]
    #: The largest ITD's size in the set, from the data.
    max_itd: float
    #: The cross-check, reported: the share of sided directions whose two
    #: estimates agree on the far ear, and their median and p95 difference.
    agreement: float
    median_difference: float
    p95_difference: float

    @property
    def directions(self) -> npt.NDArray[np.float64]:
        return self.source.directions


def decompose(hrirs: HrirSet) -> Decomposed | Refused:
    """Split `hrirs`, or refuse it if its two delay estimates disagree about
    which ear is far - the sign of a mirrored or malformed set."""
    correlated = itd(hrirs.responses)
    onset = onset_itd(hrirs.responses)
    stored = hrirs.delays[:, 0] - hrirs.delays[:, 1]
    sided = np.abs(correlated) > SIDED
    agree = (
        float(np.mean(np.sign(correlated[sided]) == np.sign(onset[sided])))
        if sided.any()
        else 1.0
    )
    if agree < AGREEMENT:
        return Refused(
            hrirs.title or "The HRTF set",
            f"has ears whose delays disagree about which is far in "
            f"{100 * (1 - agree):.0f}% of directions - it may be mirrored",
        )
    difference = correlated - onset
    total = correlated + stored
    return Decomposed(
        source=hrirs,
        itd=total,
        minimum=minimum_phase(hrirs.responses),
        max_itd=float(np.abs(total).max()),
        agreement=agree,
        median_difference=float(np.median(difference)),
        p95_difference=float(np.percentile(np.abs(difference), 95)),
    )


def itd(responses: npt.NDArray[np.float32]) -> npt.NDArray[np.float64]:
    """Each measurement's ITD by cross-correlation, in samples, signed:
    positive when the left ear is the later one.

    Refined past the sample by a parabola through the peak and its two
    neighbours, because phase 5's phase ramp gives sub-sample delay for free
    and phase 3 has to interpolate the field smoothly.
    """
    b, a = signal.butter(4, ITD_LOWPASS_HZ, btype="low", fs=SAMPLE_RATE)
    low = signal.filtfilt(b, a, responses.astype(np.float64), axis=-1)
    nfft = 1 << int(np.ceil(np.log2(2 * low.shape[-1])))
    left = np.fft.rfft(low[:, 0], n=nfft, axis=-1)
    right = np.fft.rfft(low[:, 1], n=nfft, axis=-1)
    # Circular: negative lags live at the end of the buffer, so the two
    # halves are stitched into one window running -MAX .. +MAX. A positive
    # lag means the left ear is the later one.
    correlation = np.fft.irfft(left * np.conj(right), n=nfft, axis=-1)
    w = ITD_MAX_LAG
    window = np.concatenate([correlation[:, -w:], correlation[:, : w + 1]], axis=-1)

    peak = window.argmax(axis=-1)
    rows = np.arange(window.shape[0])
    last = window.shape[-1] - 1
    before = window[rows, np.clip(peak - 1, 0, last)]
    at = window[rows, peak]
    after = window[rows, np.clip(peak + 1, 0, last)]
    curvature = before - 2.0 * at + after
    refine = (peak > 0) & (peak < last) & (curvature != 0.0)
    delta = np.where(
        refine, 0.5 * (before - after) / np.where(refine, curvature, 1.0), 0.0
    )
    return (peak - w) + np.clip(delta, -0.5, 0.5)


def onset_itd(responses: npt.NDArray[np.float32]) -> npt.NDArray[np.float64]:
    """Each measurement's ITD from its ears' onsets - the cross-check.

    It shares nothing with `itd`: no low-pass, no transform, no correlation.
    Two estimators that agreed because they were one algorithm twice would
    be worth less than one. It finds the *first* arrival where `itd` finds
    the dominant one (D-69), so it is asked about the side, not the size.
    """
    envelope = np.abs(responses.astype(np.float64))
    threshold = envelope.max(axis=-1, keepdims=True) * 10 ** (ONSET_DB / 20.0)
    first = (envelope >= threshold).argmax(axis=-1)
    m, ear = np.indices(first.shape)
    previous = np.clip(first - 1, 0, None)
    low, high = envelope[m, ear, previous], envelope[m, ear, first]
    rising = high > low
    fraction = np.where(
        rising,
        (threshold[m, ear, 0] - low) / np.where(rising, high - low, 1.0),
        0.0,
    )
    position = previous + np.clip(fraction, 0.0, 1.0)
    return position[:, 0] - position[:, 1]


def minimum_phase(
    responses: npt.NDArray[np.float32], nfft: int = MINIMUM_PHASE_NFFT
) -> npt.NDArray[np.float32]:
    """The minimum-phase part of each response, by the real cepstrum.

    Not "the response with the ITD taken out": the construction discards
    every scrap of excess phase, the delay and any all-pass together. The
    ITD is measured from the original pair, never subtracted first.
    """
    taps = responses.shape[-1]
    half = nfft // 2
    out = np.empty(responses.shape, dtype=np.float32)
    for start in range(0, responses.shape[0], CHUNK):
        chunk = responses[start : start + CHUNK].astype(np.float64)
        magnitude = np.abs(np.fft.rfft(chunk, n=nfft, axis=-1))
        floor = magnitude.max(axis=-1, keepdims=True) * 10 ** (FLOOR_DB / 20)
        cepstrum = np.fft.irfft(np.log(np.maximum(magnitude, floor)), n=nfft, axis=-1)
        # The fold is the whole construction: keep quefrency 0 and the
        # midpoint, double the causal half, discard the anticausal. The
        # other way round gives a maximum-phase response whose magnitude is
        # just as right and whose energy sits at the far end.
        folded = np.zeros_like(cepstrum)
        folded[..., 0] = cepstrum[..., 0]
        folded[..., 1:half] = 2.0 * cepstrum[..., 1:half]
        folded[..., half] = cepstrum[..., half]
        spectrum = np.exp(np.fft.rfft(folded, n=nfft, axis=-1))
        out[start : start + CHUNK] = np.fft.irfft(spectrum, n=nfft, axis=-1)[..., :taps]
    out.flags.writeable = False
    return out
