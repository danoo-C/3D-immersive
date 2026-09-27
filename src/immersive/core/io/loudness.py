"""Loudness as ITU-R BS.1770 weights it (D-128).

The K-weighting is two biquads at 48 kHz: a shelf that lifts the top by
about 4 dB, as a head does to a sound arriving from in front, and a
high-pass that takes out the low end loudness does not hear. A signal's
loudness is its mean square after them, summed over its channels.

Two ways in. `weighted_power` filters samples, for a decoded file.
`pink_power` reads a filter's loudness to pink noise straight from its
spectrum: the weighting's response squared, over the frequency, summed over
the bins. That is what an HRTF bank is calibrated by.

Nothing here is gated. The standard gates out silence to measure a whole
programme, but every use here compares a thing with itself - a file's sides
with their average, a direction with the front - where gating would only
change what the two share.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy import signal

from immersive.core.time import SAMPLE_RATE

#: BS.1770's pre-filter at 48 kHz: the shelf, then the high-pass.
SHELF_B: Final = (1.53512485958697, -2.69169618940638, 1.19839281085285)
SHELF_A: Final = (1.0, -1.69065929318241, 0.73248077421585)
HIGHPASS_B: Final = (1.0, -2.0, 1.0)
HIGHPASS_A: Final = (1.0, -1.99004745483398, 0.99007225036621)

#: How much a stereo clip folded to a point is given back, at most (D-129):
#: 6 dB, as a factor. A stem losing more than that is mostly cancelled.
FOLD_CAP: Final = 2.0

#: How many frames are filtered at a time, so a long file never needs more
#: than a few megabytes of float64 at once.
CHUNK: Final = 1 << 20


def weighting(frequencies: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """The K-weighting's power response, `|K(f)|²`, at `frequencies` in Hz."""
    _, shelf = signal.freqz(SHELF_B, SHELF_A, worN=frequencies, fs=SAMPLE_RATE)
    _, highpass = signal.freqz(HIGHPASS_B, HIGHPASS_A, worN=frequencies, fs=SAMPLE_RATE)
    return np.asarray(np.abs(shelf * highpass) ** 2, dtype=np.float64)


def pink_weights(nfft: int) -> npt.NDArray[np.float64]:
    """Each rfft bin's share of pink noise's K-weighted loudness: `|K|²/f`,
    nothing at 0 Hz."""
    frequencies = np.arange(nfft // 2 + 1, dtype=np.float64) * (SAMPLE_RATE / nfft)
    weights = weighting(frequencies)
    weights[1:] /= frequencies[1:]
    weights[0] = 0.0
    return weights


def pink_power(
    spectra: npt.NDArray[np.complexfloating], weights: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """How loud each filter in `spectra`, `[..., bins]`, makes pink noise, in
    the units of `weights` from `pink_weights`: a flat response of 1 is
    `weights.sum()`."""
    power = np.abs(spectra.astype(np.complex128)) ** 2
    return np.asarray(power @ weights, dtype=np.float64)


def weighted_power(samples: npt.NDArray[np.floating]) -> float:
    """The mean square of `samples`, one channel, after K-weighting."""
    return _powers(samples[:, None])[0]


def fold(audio: npt.NDArray[np.floating]) -> float:
    """What a stereo file loses folded to the average of its sides, as the
    factor that gives it back (D-129): `sqrt(((P_L + P_R) / 2) / P_M)`, at
    most `FOLD_CAP`. A mono or silent file loses nothing: 1."""
    if audio.ndim != 2 or audio.shape[1] != 2:
        return 1.0
    left, right, middle = _powers(audio, fold=True)
    sides = (left + right) / 2
    if sides == 0.0:
        return 1.0
    if middle <= sides / FOLD_CAP**2:
        return FOLD_CAP
    return math.sqrt(sides / middle)


def _powers(audio: npt.NDArray[np.floating], *, fold: bool = False) -> list[float]:
    """Each column's K-weighted mean square, and with `fold` their average's
    too, a chunk at a time with the filters' state carried between."""
    frames, columns = audio.shape
    count = columns + (1 if fold else 0)
    if frames == 0:
        return [0.0] * count
    shelf = [signal.lfilter_zi(SHELF_B, SHELF_A) * 0.0 for _ in range(count)]
    highpass = [signal.lfilter_zi(HIGHPASS_B, HIGHPASS_A) * 0.0 for _ in range(count)]
    totals = [0.0] * count
    for start in range(0, frames, CHUNK):
        chunk = np.asarray(audio[start : start + CHUNK], dtype=np.float64)
        rows = [chunk[:, column] for column in range(columns)]
        if fold:
            rows.append(chunk.mean(axis=1))
        for index, row in enumerate(rows):
            shelved, shelf[index] = signal.lfilter(
                SHELF_B, SHELF_A, row, zi=shelf[index]
            )
            weighted, highpass[index] = signal.lfilter(
                HIGHPASS_B, HIGHPASS_A, shelved, zi=highpass[index]
            )
            totals[index] += float(np.dot(weighted, weighted))
    return [total / frames for total in totals]
