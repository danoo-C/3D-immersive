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
from dataclasses import dataclass
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

#: The segment a file's spectra are read in, for its fold: 4096 frames, 12 Hz
#: apart, and how many segments are transformed at once.
SEGMENT: Final = 4096
SEGMENTS_AT_ONCE: Final = 256


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


@dataclass(frozen=True, eq=False)
class StemSpectra:
    """A sample's K-weighted power spectra, averaged over its 4096-frame
    segments (D-133): its left side's, its right's, and the cross-spectrum
    between them, `E[L · conj(R)]`. A mono sample's three are its one
    spectrum. At `SEGMENT`'s bins, from 0 Hz to Nyquist, in Parseval's scale,
    which every use divides out."""

    left: npt.NDArray[np.float64]
    right: npt.NDArray[np.float64]
    shared: npt.NDArray[np.complex128]

    def at(
        self, bins: int
    ) -> tuple[
        npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.complex128]
    ]:
        """The three at `bins` rfft bins across the same 0 Hz to Nyquist,
        each the average of the finer bins its band covers, divided by the
        stem as mixed - its two sides' power summed - so a side heard at
        unity in its own ear is 1."""
        fine = SEGMENT // 2 + 1
        centres = np.arange(bins) * ((fine - 1) / max(bins - 1, 1))
        edges = np.clip(
            np.ceil(centres - (fine - 1) / max(bins - 1, 1) / 2), 0, fine - 1
        )
        starts = edges.astype(np.int64)
        starts[0] = 0
        counts = np.diff(np.append(starts, fine))
        counts = np.maximum(counts, 1)

        def banded(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            return np.asarray(
                np.add.reduceat(values, starts) / counts, dtype=np.float64
            )

        left = banded(self.left)
        right = banded(self.right)
        shared = np.empty(bins, dtype=np.complex128)
        shared.real = banded(self.shared.real)
        shared.imag = banded(self.shared.imag)
        total = float(left.sum() + right.sum())
        if total <= 0.0:
            half = np.full(bins, 0.5 / bins)
            return half, half.copy(), np.zeros(bins, dtype=np.complex128)
        return left / total, right / total, shared / total

    @property
    def fold(self) -> float:
        """What folding to the sides' average loses, as the factor that
        gives it back (D-129), at most `FOLD_CAP`."""
        left, right = float(self.left.sum()), float(self.right.sum())
        middle = (left + right + 2.0 * float(self.shared.real.sum())) / 4.0
        sides = (left + right) / 2.0
        if sides == 0.0:
            return 1.0
        if middle <= sides / FOLD_CAP**2:
            return FOLD_CAP
        return math.sqrt(sides / middle)


def measure(audio: npt.NDArray[np.floating]) -> StemSpectra:
    """A sample's `StemSpectra`, read from the spectra of 4096-frame
    segments rather than by filtering: for a weighting as smooth as K's
    that is the filtered answer, within 0.002 dB on the stems measured, and
    ten times quicker - 0.2 s against 2.2 s for three minutes of stereo,
    which every import pays."""
    weights = weighting(
        np.arange(SEGMENT // 2 + 1, dtype=np.float64) * (SAMPLE_RATE / SEGMENT)
    )
    bins = SEGMENT // 2 + 1
    left_total = np.zeros(bins)
    right_total = np.zeros(bins)
    shared_total = np.zeros(bins, dtype=np.complex128)
    stereo = audio.ndim == 2 and audio.shape[1] == 2
    for start in range(0, audio.shape[0], SEGMENT * SEGMENTS_AT_ONCE):
        part = np.asarray(
            audio[start : start + SEGMENT * SEGMENTS_AT_ONCE], dtype=np.float32
        ).reshape(-1, audio.shape[1] if audio.ndim == 2 else 1)
        short = -part.shape[0] % SEGMENT
        if short:
            part = np.pad(part, ((0, short), (0, 0)))
        spectra = np.fft.rfft(part.reshape(-1, SEGMENT, part.shape[1]), axis=1)
        left = spectra[..., 0]
        right = spectra[..., 1] if stereo else left
        left_total += (np.abs(left) ** 2).sum(axis=0)
        right_total += (np.abs(right) ** 2).sum(axis=0)
        shared_total += (left * np.conj(right)).sum(axis=0)
    return StemSpectra(
        left_total * weights, right_total * weights, shared_total * weights
    )


def fold(audio: npt.NDArray[np.floating]) -> float:
    """What a stereo file loses folded to the average of its sides, as the
    factor that gives it back (D-129): `sqrt(((P_L + P_R) / 2) / P_M)`, at
    most `FOLD_CAP`. A mono or silent file loses nothing: 1."""
    if audio.ndim != 2 or audio.shape[1] != 2:
        return 1.0
    return measure(audio).fold


def _powers(audio: npt.NDArray[np.floating]) -> list[float]:
    """Each column's K-weighted mean square, a chunk at a time with the
    filters' state carried between."""
    frames, columns = audio.shape
    if frames == 0:
        return [0.0] * columns
    shelf = [signal.lfilter_zi(SHELF_B, SHELF_A) * 0.0 for _ in range(columns)]
    highpass = [signal.lfilter_zi(HIGHPASS_B, HIGHPASS_A) * 0.0 for _ in range(columns)]
    totals = [0.0] * columns
    for start in range(0, frames, CHUNK):
        chunk = np.asarray(audio[start : start + CHUNK], dtype=np.float64)
        rows = [chunk[:, column] for column in range(columns)]
        for index, row in enumerate(rows):
            shelved, shelf[index] = signal.lfilter(
                SHELF_B, SHELF_A, row, zi=shelf[index]
            )
            weighted, highpass[index] = signal.lfilter(
                HIGHPASS_B, HIGHPASS_A, shelved, zi=highpass[index]
            )
            totals[index] += float(np.dot(weighted, weighted))
    return [total / frames for total in totals]
