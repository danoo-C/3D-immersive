#!/usr/bin/env python3
"""S0 — the listening spike.

Throwaway. Not part of the package, not imported by anything, never moved into
`src/`. See docs/s0_listening_spike/ for what each phase of it is for.

Phase 1: fetch a SOFA set, validate it, convert its directions, resample to
48 kHz and normalise the level.
Phase 2: split each measurement into a broadband ITD and a minimum-phase HRIR.
Phase 3: triangulate the sphere and interpolate between measured directions.
Phase 4: the per-block engine, and the four files phase 5 listens to.

    python spikes/binaural_spike.py --info
    python spikes/binaural_spike.py --check
    python spikes/binaural_spike.py --render
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sofar
import soxr
from scipy import signal
from scipy.io import wavfile
from scipy.spatial import ConvexHull, cKDTree

# SADIE II D1 — the KEMAR dummy head, already 48 kHz, 256 taps. The York URL
# in the roadmap's prose is dead; this is the sofacoustics.org mirror. The
# digest is here so a truncated download or a swapped mirror fails loudly.
URL = "https://sofacoustics.org/data/database/sadie/D1_48K_24bit_256tap_FIR_SOFA.sofa"
SHA256 = "e6c72a84dd947b5ef75438ab96a9c2a32ed10f033472b9c4c11a49aff00a8a31"
DATA_DIR = Path(__file__).parent / "data"

RATE = 48_000  # docs/05-audio-engine.md, fixed parameters
BLOCK = 512  # ditto: the default block, and what phase 4 renders at

# Normalisation target: mean per-ear broadband energy. Energy rather than peak,
# so switching datasets does not change perceived loudness (05-audio-engine.md
# §1); 0.25 per ear means the pair sums to -3 dBFS nominal, which is the fixed
# headroom that keeps the loudest single direction under full scale. That it
# actually does is checked, not assumed - at 0.5 this set peaks at 1.06.
TARGET_EAR_ENERGY = 0.25

# ITD is a low-frequency cue. Above roughly 1.5 kHz the head shadow puts ripple
# on the cross-correlation that makes its peak broad and sometimes bimodal,
# which is how an otherwise plausible ITD field acquires a handful of
# directions that are a millisecond out. Zero-phase, so the filter adds no
# delay of its own to the thing being measured.
ITD_LOWPASS_HZ = 1500.0

# Only lags this far out are searched. The largest human ITD is around 50
# samples at 48 kHz, so 128 is loose enough not to constrain the answer and
# tight enough to reject a spurious peak somewhere in the tail.
ITD_MAX_LAG = 128

#: SOFA azimuths, in the order the horizontal-plane table prints them.
#: 0 is front and azimuth increases anticlockwise, so 90 is the listener's
#: left and 270 their right (docs/03-data-model.md).
HORIZONTAL_AZIMUTHS = (0.0, 30.0, 60.0, 90.0, 270.0, 300.0, 330.0)

EAR_NAMES = ("left", "right")

# Candidate face counts tried in order before the exhaustive test. Measured
# over 10 000 seeded directions: k=8 resolves 83.8%, k=32 resolves 98.95%,
# k=128 resolves 100%. The tiers are the optimisation; the exhaustive pass
# behind them is the correctness argument, because "100% of ten thousand
# directions from one seed" is not the same claim as "every query finds a
# containing triangle", which is what this has to be true of.
#
# 8 first, not 32: the kd-tree costs the same either way (13-14 us, all of it
# call overhead), but the barycentric test is linear in k, so the 84% that
# resolve at 8 pay a quarter of the arithmetic. The 16% that fall through pay
# for both, and still come out ahead on the average.
INTERP_TIERS = (8, 32, 128)

# A barycentric weight below this is outside the triangle. Not zero, because a
# query landing exactly on a shared edge or a vertex - which happens whenever
# anyone asks for a measured direction - computes as a hair either side of it.
INTERP_TOL = 1e-9


@dataclass
class Triangulation:
    """The spherical Delaunay triangulation of a set of directions.

    On a sphere the convex hull *is* the Delaunay triangulation, so this is one
    `ConvexHull` call and a little bookkeeping.
    """

    simplices: np.ndarray  # [F, 3] vertex indices
    inverse: np.ndarray  # [F, 3, 3], inv of the three vertices as columns
    centroids: np.ndarray  # [F, 3] unit vectors
    tree: cKDTree  # over the centroids

    @property
    def f(self) -> int:
        return int(self.simplices.shape[0])


@dataclass
class HrirSet:
    """A loaded, resampled, normalised HRIR set."""

    name: str
    licence: str
    ir: np.ndarray  # [M, 2, N] float32, 48 kHz
    directions: np.ndarray  # [M, 3] unit vectors, SOFA frame (+x front, +y left)
    az_el: np.ndarray  # [M, 2] degrees, as measured
    source_rate: int
    delay: np.ndarray  # Data_Delay as stored, samples
    gain: float  # normalisation gain that was applied
    itd: np.ndarray  # [M] float32, unsigned magnitude in samples
    itd_far_ear: np.ndarray  # [M] uint8, 0 = left, 1 = right
    minphase: np.ndarray  # [M, 2, N] float32, no delay of any kind
    tri: Triangulation  # the sphere these directions triangulate to

    @property
    def m(self) -> int:
        return int(self.ir.shape[0])

    @property
    def n(self) -> int:
        return int(self.ir.shape[2])

    @property
    def max_itd_samples(self) -> int:
        """The largest ITD in this set, rounded up.

        Derived from the measured field every time, never a constant. A set
        recorded on a larger head, or one resampled from a different rate,
        will not match anybody's estimate — and this number sizes the buffer
        the ITD phase ramp lives in, so guessing it low is not a small error:
        a circular delay pushes the tail of the response past the end of the
        buffer and it reappears at the beginning, ahead of the onset.
        """
        return int(np.ceil(self.itd.max()))


# --------------------------------------------------------------------------- #
# step 1 — fetch and cache
# --------------------------------------------------------------------------- #


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str = URL, expected: str = SHA256) -> Path:
    """Download once into spikes/data/, verify on every run."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / url.rsplit("/", 1)[-1]

    if not path.exists():
        print(f"fetching {url}")
        tmp = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url) as stream, tmp.open("wb") as fh:
            shutil.copyfileobj(stream, fh)
        tmp.replace(path)

    got = digest(path)
    if expected and got != expected:
        raise SystemExit(
            f"checksum mismatch for {path.name}\n"
            f"  expected {expected}\n  got      {got}"
        )
    if not expected:
        print(f"no expected digest recorded; this file is sha256 {got}")
    return path


# --------------------------------------------------------------------------- #
# steps 2-5 — load, orient, resample, normalise
# --------------------------------------------------------------------------- #


def sofa_directions(az_el: np.ndarray) -> np.ndarray:
    """SOFA spherical degrees -> unit vectors in SOFA's frame (+x front, +y left)."""
    az = np.radians(az_el[:, 0])
    el = np.radians(az_el[:, 1])
    return np.stack(
        [np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=1
    )


def cartesian_to_sofa(xyz: np.ndarray) -> np.ndarray:
    """Project frame (x right, y front, z up) -> SOFA azimuth/elevation degrees.

    The formula is owned by docs/03-data-model.md; this is the only place the
    spike converts, so phase 3's hull and phase 4's queries cannot disagree
    about which way is left.
    """
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    r = np.sqrt(x * x + y * y + z * z)
    az = np.degrees(np.arctan2(-x, y)) % 360.0
    el = np.degrees(np.arcsin(z / r))
    return np.stack([az, el], axis=1)


def resample(ir: np.ndarray, source_rate: int) -> np.ndarray:
    """Resample [M, 2, N] to RATE. A no-op when the set is already there."""
    if source_rate == RATE:
        return ir
    m, ears, n = ir.shape
    flat = ir.transpose(2, 0, 1).reshape(n, m * ears)
    out = soxr.resample(flat, source_rate, RATE)
    return np.ascontiguousarray(out.reshape(-1, m, ears).transpose(1, 2, 0))


def response(h: np.ndarray, rate: int, freqs: np.ndarray) -> np.ndarray:
    """|H(f)| of an impulse response, scaled by 1/rate so it is rate-independent."""
    n = np.arange(len(h))
    return np.array(
        [abs(np.sum(h * np.exp(-2j * np.pi * f * n / rate))) / rate for f in freqs]
    )


def normalise(ir: np.ndarray) -> tuple[np.ndarray, float]:
    """Scale so the mean per-ear broadband energy hits TARGET_EAR_ENERGY."""
    energy = float(np.mean(np.sum(ir.astype(np.float64) ** 2, axis=2)))
    gain = float(np.sqrt(TARGET_EAR_ENERGY / energy))
    return (ir * gain).astype(np.float32), gain


# --------------------------------------------------------------------------- #
# phase 2, step 1 — ITD by cross-correlation
# --------------------------------------------------------------------------- #


def lowpass(ir: np.ndarray, cutoff: float = ITD_LOWPASS_HZ) -> np.ndarray:
    """Zero-phase low-pass along the last axis."""
    b, a = signal.butter(4, cutoff, btype="low", fs=RATE)
    return signal.filtfilt(b, a, ir.astype(np.float64), axis=-1)


def estimate_itd(ir: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Broadband ITD per direction, by cross-correlation of the two ears.

    Returns `(magnitude, far_ear)`: an unsigned delay in samples, and which
    ear it belongs to. That representation is not incidental — 05-audio-engine
    §4 applies the delay as a frequency-domain phase ramp, and a ramp with a
    negative sign is an *advance*, which wraps the start of the response round
    to the end of the buffer. Carrying the sign as "which ear" instead lets
    phase 4 apply the full magnitude to the far ear and zero to the near one,
    so both ramps stay non-negative and nothing wraps.

    The magnitude is fractional. Phase 4's ramp gives sub-sample delay for
    free, and phase 3 has to interpolate this field and show it is continuous
    to better than a sample, which a sample-quantised field cannot be.
    """
    lp = lowpass(ir)
    nfft = 1 << int(np.ceil(np.log2(2 * lp.shape[-1])))
    left = np.fft.rfft(lp[:, 0], n=nfft, axis=-1)
    right = np.fft.rfft(lp[:, 1], n=nfft, axis=-1)

    # Circular cross-correlation. Negative lags live at the end of the buffer,
    # so the two halves are stitched into one window running -MAX .. +MAX.
    # Sign convention: a positive lag means the *left* ear is the later one.
    # That is pinned by the synthetic check in checks.py rather than argued
    # from a convention here, because it is the error that would survive every
    # summary statistic in this file and only show up in phase 5, as a mix
    # that is quietly mirrored.
    cc = np.fft.irfft(left * np.conj(right), n=nfft, axis=-1)
    w = ITD_MAX_LAG
    window = np.concatenate([cc[:, -w:], cc[:, : w + 1]], axis=-1)

    peak = window.argmax(axis=-1)
    rows = np.arange(window.shape[0])
    last = window.shape[-1] - 1

    # Parabolic interpolation through the three samples around the peak. Guard
    # the edges and a flat top, both of which mean there is nothing to refine.
    y0 = window[rows, np.clip(peak - 1, 0, last)]
    y1 = window[rows, peak]
    y2 = window[rows, np.clip(peak + 1, 0, last)]
    curvature = y0 - 2.0 * y1 + y2
    refine = (peak > 0) & (peak < last) & (curvature != 0.0)
    delta = np.where(refine, 0.5 * (y0 - y2) / np.where(refine, curvature, 1.0), 0.0)

    lag = (peak - w) + np.clip(delta, -0.5, 0.5)
    far = np.where(lag > 0.0, 0, 1).astype(np.uint8)
    return np.abs(lag).astype(np.float32), far


# Onset threshold, relative to each ear's own peak. -20 dB was the plan's
# figure and measured badly: on an unfiltered HRIR that level is down in the
# pre-ringing, and the estimator agrees with the correlation about which ear is
# even *far* only 73% of the time, with outliers 62 samples out. -10 dB sits on
# the real leading edge. Per-ear rather than a level shared across the pair,
# because the far ear is head-shadowed and a shared threshold would measure the
# shadow as much as the delay.
ITD_ONSET_DB = -10.0


def estimate_itd_onset(ir: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """ITD from onset times — the independent cross-check on `estimate_itd`.

    Deliberately shares nothing with the cross-correlation: no low-pass, no
    FFT, no correlation, no windowing. That is the whole value of it. Two
    estimators that agreed because they were the same algorithm twice would be
    worth less than one estimator honestly reported, and tuning this one until
    it matches is the exact failure it exists to prevent.

    Returns the same `(magnitude, far_ear)` pair as `estimate_itd`.
    """
    env = np.abs(ir)
    threshold = env.max(axis=-1, keepdims=True) * 10 ** (ITD_ONSET_DB / 20.0)
    first = (env >= threshold).argmax(axis=-1)

    # Linear interpolation between the samples straddling the crossing, so the
    # estimate is not quantised to whole samples when the comparison it feeds
    # is measured in samples.
    m, ear = np.indices(first.shape)
    prev = np.clip(first - 1, 0, None)
    low, high = env[m, ear, prev], env[m, ear, first]
    rising = high > low
    frac = np.where(
        rising, (threshold[m, ear, 0] - low) / np.where(rising, high - low, 1.0), 0.0
    )
    position = prev + np.clip(frac, 0.0, 1.0)

    lag = position[:, 0] - position[:, 1]
    far = np.where(lag > 0.0, 0, 1).astype(np.uint8)
    return np.abs(lag).astype(np.float32), far


# 32x the 256 taps, measured rather than assumed - and *not* the same number as
# phase 4's convolution nfft, which is 1024 and comes from a different formula
# entirely (block + taps + ITD). Two nffts, two reasons; conflating them is an
# easy and expensive mistake.
#
# The usual rule of thumb is 4x the impulse length, and for HRIRs it is wrong.
# The cepstrum has to decay before it wraps round its own buffer, and the log
# magnitude of a deep pinna notch decays very slowly, so the aliasing lands
# exactly at the nulls. Measured over 20 directions, worst in-band error:
#
#     nfft  1024 (4x)   5.489 dB     39 bins over 0.5 dB
#     nfft  2048 (8x)   4.490 dB      5 bins
#     nfft  4096 (16x)  0.886 dB      1 bin
#     nfft  8192 (32x)  0.017 dB      0 bins
#
# A tenfold improvement per doubling, all of it at the nulls. At 1024 the
# error is small enough everywhere else - 0.155 dB within 30 dB of the peak -
# that nothing but a check aimed straight at the notches would have caught it.
MINPHASE_NFFT = 8192

# One batched transform of the whole set at that size would peak at several GB.
# Chunked, it is 70 MB at a time and no slower in any way that matters here.
MINPHASE_CHUNK = 512

# HRTFs have deep pinna notches, and log(0) at one of them puts an infinity
# into the cepstrum that comes back as NaN in every tap. Floored relative to
# each response's own peak, so it does not depend on the set's overall level.
MINPHASE_FLOOR_DB = -100.0


def minimum_phase(ir: np.ndarray, nfft: int = MINPHASE_NFFT) -> np.ndarray:
    """The minimum-phase part of each HRIR, via the real cepstrum.

    Per §2 of docs/05-audio-engine.md. Minimum-phase magnitudes interpolate
    cleanly and delays interpolate cleanly; their sum does not, which is why
    the two are kept apart. This returns the spectral half — it carries no
    delay at all, including no ITD.

    Note this is *not* "the HRIR with the ITD taken out": the construction
    discards every scrap of excess phase, the interaural delay and any all-pass
    component together. The ITD is estimated separately from the original pair,
    never subtracted first, or whatever the estimate got wrong would be counted
    twice.
    """
    taps = ir.shape[-1]
    half = nfft // 2
    out = np.empty(ir.shape, dtype=np.float32)

    for start in range(0, ir.shape[0], MINPHASE_CHUNK):
        chunk = ir[start : start + MINPHASE_CHUNK].astype(np.float64)
        magnitude = np.abs(np.fft.rfft(chunk, n=nfft, axis=-1))
        floor = magnitude.max(axis=-1, keepdims=True) * 10 ** (MINPHASE_FLOOR_DB / 20)
        cepstrum = np.fft.irfft(np.log(np.maximum(magnitude, floor)), n=nfft, axis=-1)

        # The fold, which is the whole construction: keep quefrency 0 and the
        # midpoint, double everything causal, discard everything anticausal.
        # Doing it the other way round produces a *maximum*-phase response
        # whose magnitude check passes perfectly and whose energy sits at the
        # far end - which is why the energy check is not a nicety.
        folded = np.zeros_like(cepstrum)
        folded[..., 0] = cepstrum[..., 0]
        folded[..., 1:half] = 2.0 * cepstrum[..., 1:half]
        folded[..., half] = cepstrum[..., half]

        spectrum = np.exp(np.fft.rfft(folded, n=nfft, axis=-1))
        built = np.fft.irfft(spectrum, n=nfft, axis=-1)[..., :taps]
        out[start : start + MINPHASE_CHUNK] = built

    return out


# --------------------------------------------------------------------------- #
# phase 3 — spherical interpolation
# --------------------------------------------------------------------------- #


def triangulate(directions: np.ndarray) -> Triangulation:
    """Triangulate the sphere the measurement directions lie on.

    Per §3 of docs/05-audio-engine.md. `ConvexHull` because for points on a
    sphere the hull *is* the Delaunay triangulation - every face is one, and a
    closed hull has no gaps, which is what makes "every direction is inside
    some triangle" true rather than hopeful.

    Each face gets the inverse of its three vertices-as-columns. Solving
    `M @ [a, b, c] = q` then gives coefficients whose normalised form is
    exactly the barycentric coordinate of where the ray from the origin
    pierces that triangle's plane, and `q` is inside the spherical triangle if
    and only if all three are non-negative. One 3x3 inverse per face turns both
    the containment test and the weights into a single einsum - no ray-plane
    intersection and no spherical trigonometry to get wrong at a pole.
    """
    hull = ConvexHull(directions)
    simplices = np.asarray(hull.simplices, dtype=np.int64)
    corners = directions[simplices]  # [F, 3, 3], row j is vertex j
    inverse = np.linalg.inv(np.transpose(corners, (0, 2, 1)))
    centroids = corners.mean(axis=1)
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    return Triangulation(simplices, inverse, centroids, cKDTree(centroids))


def barycentric(inverse: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Normalised weights of each direction in each candidate face.

    `inverse` is [Q, K, 3, 3] and `q` is [Q, 3]; the result is [Q, K, 3]. A
    face whose plane the ray meets *behind* the listener is scored -1 rather
    than left to produce a plausible-looking set of weights with the wrong
    sign, which is the one way a normalised barycentric coordinate can lie.
    """
    w = np.einsum("qkij,qj->qki", inverse, q)
    total = w.sum(-1)
    behind = total <= 0
    total[behind] = 1.0
    w /= total[..., None]
    w[behind] = -1.0
    return w


def locate(
    tri: Triangulation, q: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Containing face and barycentric weights for each direction.

    Returns `(face, weights, resolved_per_tier)`. The tiers narrow the search;
    the last one is every face in the triangulation, so on a closed hull this
    cannot fail to find a triangle - the guarantee comes from the geometry
    rather than from a `k` that happened to be big enough on the dataset it
    was tuned against.
    """
    tiers = (*INTERP_TIERS, tri.f)
    resolved = [0] * len(tiers)
    face = weights = None
    pending = np.arange(len(q))

    for tier, k in enumerate(tiers):
        here = q[pending]
        if k >= tri.f:
            candidates = np.broadcast_to(np.arange(tri.f), (len(pending), tri.f))
            inverse = np.broadcast_to(tri.inverse, (len(pending), tri.f, 3, 3))
        else:
            candidates = np.atleast_2d(tri.tree.query(here, k=k)[1])
            inverse = tri.inverse[candidates]

        w = barycentric(inverse, here)
        inside = (w >= -INTERP_TOL).all(-1)
        hit = inside.any(-1)
        pick = inside.argmax(-1)
        rows = np.arange(len(pending))
        resolved[tier] = int(hit.sum())

        if face is None and hit.all():
            # Everything landed in the first tier it was offered, which is the
            # overwhelmingly common case. Returning here skips the scatter
            # bookkeeping below, which on a single direction costs more than
            # the arithmetic it exists to manage.
            resolved[tier] = len(q)
            return candidates[rows, pick], w[rows, pick], resolved

        if face is None:
            face = np.full(len(q), -1, dtype=np.int64)
            weights = np.zeros((len(q), 3))
        face[pending[hit]] = candidates[rows, pick][hit]
        weights[pending[hit]] = w[rows, pick][hit]
        pending = pending[~hit]
        if not len(pending):
            break

    if len(pending):  # a closed hull leaves nowhere for a direction to hide
        raise AssertionError(f"{len(pending)} directions outside every face")
    assert face is not None and weights is not None
    return face, weights, resolved


def signed_itd(hrir: HrirSet) -> np.ndarray:
    """The ITD field as a signed quantity, positive when the left ear is far.

    Interpolation happens here and not on the magnitude: averaging two
    magnitudes across the median plane turns +30 and -30 into 30, a delay
    pointing the wrong way at full strength, instead of the 0 it should be.
    """
    return np.where(hrir.itd_far_ear == 0, hrir.itd, -hrir.itd).astype(np.float64)


def interpolate_itd(
    hrir: HrirSet, face: np.ndarray, weights: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Barycentric ITD for located directions, back in phase 2's form."""
    blended = (signed_itd(hrir)[hrir.tri.simplices[face]] * weights).sum(-1)
    far = np.where(blended > 0.0, 0, 1).astype(np.uint8)
    return np.abs(blended).astype(np.float32), far


def sweep(
    hrir: HrirSet, az: np.ndarray, el: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Signed interpolated ITD along a path, plus the face used at each step."""
    face, weights, _ = locate(hrir.tri, sofa_directions(np.stack([az, el], axis=1)))
    blended = (signed_itd(hrir)[hrir.tri.simplices[face]] * weights).sum(-1)
    return face, blended


def horizontal_sweep(hrir: HrirSet, step: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    az = np.arange(0.0, 360.0, step)
    return sweep(hrir, az, np.zeros_like(az))


def elevation_sweep(hrir: HrirSet, step: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """From -40 deg, up over the pole, and down the far side to -40.

    Where the triangles are largest and sparsest, and where a scheme that
    indexes faces by their vertices falls apart - the pole is one measurement
    fanning out to 400 faces.
    """
    t = np.arange(-40.0, 221.0, step)
    el = np.where(t <= 90.0, t, 180.0 - t)
    az = np.where(t <= 90.0, 0.0, 180.0)
    return sweep(hrir, az, el)


# --------------------------------------------------------------------------- #
# phase 4 — the block engine
# --------------------------------------------------------------------------- #

#: Fixed for the spike. Distance rolloff (D-21) is M4's; here the source stays
#: at one radius so nothing but direction changes between blocks.
ORBIT_RADIUS_M = 1.5
RENDER_SECONDS = 8.0
OUT_DIR = Path(__file__).parent / "out"

#: Peak the renders are normalised to. Below full scale, because the
#: acceptance asks for no sample at or above it and a file that just touches
#: 1.0 will clip the first resampler it meets.
RENDER_PEAK = 0.89


def prepare_bank(minphase: np.ndarray, nfft: int) -> np.ndarray:
    """The frequency-domain minimum-phase bank, `[M, 2, nfft//2+1]` complex64.

    05-audio-engine.md §4. complex64 rather than complex128 because this is
    72 MB either way doubled, and the engine's error floor is set by the
    fractional ITD ramp at about -74 dBFS, nowhere near single precision.
    """
    return np.fft.rfft(minphase.astype(np.float64), n=nfft, axis=-1).astype(
        np.complex64
    )


class Engine:
    """The per-block binaural engine, for exactly one source.

    Everything M4 adds — more sources, frequency-domain summation, the
    scheduler, distance, the limiter, the zero-allocation rule — is absent on
    purpose. What is here is the part the design could be wrong about.
    """

    def __init__(
        self,
        hrir: HrirSet,
        *,
        crossfade: bool = True,
        block: int = BLOCK,
        quantise_itd: bool = False,
    ):
        self.hrir = hrir
        self.block = block
        # For the phase 4 control only. A whole-sample delay makes the filter
        # compactly supported, so overlap-add becomes exact and the block loop
        # matches a direct convolution to around -300 dB. That is what
        # separates "the engine's arithmetic is wrong" from "the fractional
        # ramp costs what D-37 says it costs" - and without it, the -74 dB the
        # real path reaches has nothing to be compared against.
        self.quantise_itd = quantise_itd
        self.nfft = nfft_for(hrir.n, hrir.max_itd_samples, block)
        self.bank = prepare_bank(hrir.minphase, self.nfft)
        self.freqs = np.fft.rfftfreq(self.nfft)
        self.crossfade = crossfade
        self.w_in = np.linspace(0.0, 1.0, block)
        self.w_out = 1.0 - self.w_in
        self.tail = np.zeros((2, self.nfft - block))
        self.h_prev: np.ndarray | None = None

    def filter_for(self, az: float, el: float) -> np.ndarray:
        """`[2, bins]` filter for one direction: weighted bank, then the ITD.

        The delay goes on entirely as the far ear's ramp and zero on the near
        one, so both are non-negative and neither wraps — the rule from §4 of
        05-audio-engine.md, whose whole point is that a negative ramp is an
        *advance* and puts the tail of the response before its own onset.
        """
        face, weights, _ = locate(self.hrir.tri, sofa_directions(np.array([[az, el]])))
        vertices = self.hrir.tri.simplices[face[0]]
        h = (self.bank[vertices].astype(np.complex128) * weights[0][:, None, None]).sum(
            0
        )
        magnitude, far = interpolate_itd(self.hrir, face, weights)
        delay = float(magnitude[0])
        tau = np.zeros(2)
        tau[far[0]] = round(delay) if self.quantise_itd else delay
        return h * np.exp(-2j * np.pi * self.freqs[None, :] * tau[:, None])

    def process(self, x: np.ndarray, az: float, el: float) -> np.ndarray:
        """One block of mono input from one direction -> `[2, block]` stereo."""
        h_cur = self.filter_for(az, el)
        if self.h_prev is None:
            # Nothing to fade from on the first block. 05 requires the same
            # after a seek or a snapshot swap, for the same reason: crossfading
            # from a stale filter is worse than not crossfading at all.
            self.h_prev = h_cur

        if self.crossfade:
            # D-37, windowing the *input*: two full-length convolutions whose
            # tails each taper correctly into the next block, rather than one
            # output crossfade that would chop them.
            copies = np.stack([x * self.w_out, x * self.w_in])
            spectra = np.fft.rfft(copies, n=self.nfft, axis=-1)
            y_f = spectra[0][None, :] * self.h_prev + spectra[1][None, :] * h_cur
        else:
            y_f = np.fft.rfft(x, n=self.nfft)[None, :] * h_cur

        y = np.fft.irfft(y_f, n=self.nfft, axis=-1)
        y[:, : self.nfft - self.block] += self.tail
        self.tail = y[:, self.block :]
        self.h_prev = h_cur
        return y[:, : self.block]


# --------------------------------------------------------------------------- #
# test signals
# --------------------------------------------------------------------------- #


def band_limited_sawtooth(freq: float, n: int, rate: int = RATE) -> np.ndarray:
    """A sawtooth summed from the harmonics that fit below Nyquist.

    Not `scipy.signal.sawtooth`, which is a naive time-domain generator with
    no band limiting: at 440 Hz into 48 kHz it puts -20.1 dB of energy off the
    harmonic grid, against -108.6 dB for this. That aliased hash raises the
    crossfaded render's noise floor by 22 dB and drags the measured sideband
    reduction from 33 dB to 13 - below this phase's acceptance, and looking
    exactly like the crossfade failing rather than the test signal being
    wrong. It would have misled the listening test too, because broadband
    roughness is precisely what the zipper test listens for.
    """
    t = np.arange(n) / rate
    out = np.zeros(n)
    for k in range(1, int(rate / 2 / freq) + 1):
        out -= np.sin(2 * np.pi * freq * k * t) / k
    return out * 2.0 / np.pi


def pink_noise(n: int, seed: int = 0) -> np.ndarray:
    """Pink noise, by shaping white in the frequency domain. Seeded."""
    spectrum = np.fft.rfft(np.random.default_rng(seed).normal(size=n))
    f = np.fft.rfftfreq(n)
    shape = np.ones_like(f)
    shape[1:] = 1.0 / np.sqrt(f[1:])
    out = np.fft.irfft(spectrum * shape, n=n)
    return out / np.abs(out).max()


def burst_envelope(n: int, on_ms: float = 100.0, rate: int = RATE) -> np.ndarray:
    """100 ms on, 100 ms off, with 2 ms raised-cosine edges.

    The edges are not decoration: a hard gate is a click, and a click is a
    localisation cue of its own, which would flatter the result.
    """
    period = int(on_ms / 1000.0 * rate)
    gate = ((np.arange(n) // period) % 2 == 0).astype(np.float64)
    ramp = max(1, int(0.002 * rate))
    window = np.hanning(2 * ramp)
    return np.convolve(gate, window / window.sum(), mode="same")


def click_train(n: int, interval_ms: float = 100.0, rate: int = RATE) -> np.ndarray:
    """Single-sample impulses. Kept, but no longer what the renders use.

    Phase 5 listened to this and could barely tell what was happening. One
    sample is about 20 us, and front/back is carried almost entirely by the
    spectral notches the pinna imposes - a timbre judgement, with nearly no
    signal to make it from. `burst_train` replaced it. See the phase 5 notes.
    """
    out = np.zeros(n)
    out[:: max(1, int(interval_ms / 1000.0 * rate))] = 1.0
    return out


def burst_train(
    n: int,
    interval_ms: float = 160.0,
    burst_ms: float = 40.0,
    seed: int = 1,
    rate: int = RATE,
) -> np.ndarray:
    """Pink-noise bursts, as an alternative to single-sample clicks.

    Front/back is the hard direction: interaural time and level are nearly the
    same in front and behind — the cone of confusion — so almost the only cue
    distinguishing them is the spectral shape the pinna imposes, mostly
    notches in the 5-12 kHz region. That is a *timbre* judgement, and a
    one-sample click is about 20 us of signal to make it from.

    These bursts keep the discrete onsets, which are what makes a source easy
    to follow as it moves, and give the spectral cue something to sit in.
    """
    noise = pink_noise(n, seed=seed)
    period = max(1, int(interval_ms / 1000.0 * rate))
    length = max(1, int(burst_ms / 1000.0 * rate))
    edge = max(1, int(0.003 * rate))
    shape = np.ones(length)
    shape[:edge] = np.hanning(2 * edge)[:edge]
    shape[-edge:] = np.hanning(2 * edge)[edge:]

    envelope = np.zeros(n)
    for start in range(0, n - length, period):
        envelope[start : start + length] = shape
    return noise * envelope


def orbit_path(
    blocks: int, block: int = BLOCK, rev_per_s: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Azimuth and elevation per block for a horizontal orbit at ear level.

    One revolution a second is about 4 degrees a block, which is deliberately
    the hard case rather than a typical one: it is fast enough that the filter
    changes measurably every block, which is what the crossfade exists for.
    """
    t = np.arange(blocks) * block / RATE
    return (360.0 * rev_per_s * t) % 360.0, np.zeros(blocks)


def front_back_path(blocks: int, block: int = BLOCK) -> tuple[np.ndarray, np.ndarray]:
    """Front, up over the top, and down to directly behind."""
    travel = 180.0 * np.arange(blocks) / max(1, blocks - 1)
    azimuth = np.where(travel <= 90.0, 0.0, 180.0)
    elevation = np.where(travel <= 90.0, travel, 180.0 - travel)
    return azimuth, elevation


def next_pow2(n: int) -> int:
    return 1 << int(np.ceil(np.log2(n)))


def nfft_for(taps: int, max_itd: int, block: int = BLOCK) -> int:
    """Buffer length for a block of convolution plus its ITD ramp.

    From *Prepare the bank* in docs/05-audio-engine.md. The ramp is a circular
    delay, so the buffer has to be long enough for the block, the impulse
    response and the delay together; anything past the end wraps round to the
    front, which is not a subtle artefact but the tail arriving before the
    onset.

    `max_itd` is rounded up from the measured field. A fractional delay is not
    strictly confined to `ceil(tau)` — a phase ramp is sinc interpolation and
    spreads a little either side — but `next_pow2` leaves hundreds of samples
    of slack at these sizes, which the caller prints rather than assumes.
    """
    return next_pow2(block + taps + max_itd - 1)


def nearest_direction(hrir: HrirSet, az: float, el: float = 0.0) -> int:
    """Index of the measurement closest to (az, el), in degrees."""
    d_az = (hrir.az_el[:, 0] - az + 180.0) % 360.0 - 180.0
    d_el = hrir.az_el[:, 1] - el
    return int(np.argmin(d_az * d_az + d_el * d_el))


def horizontal_itd(hrir: HrirSet) -> list[tuple[float, float, float, int]]:
    """(azimuth, ITD samples, ITD ms, far ear) across the horizontal plane."""
    rows = []
    for az in HORIZONTAL_AZIMUTHS:
        i = nearest_direction(hrir, az)
        samples = float(hrir.itd[i])
        az_measured = float(hrir.az_el[i, 0])
        far = int(hrir.itd_far_ear[i])
        rows.append((az_measured, samples, samples / RATE * 1e3, far))
    return rows


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def load(path: Path | None = None) -> HrirSet:
    sofa = sofar.read_sofa(str(path or fetch()), verify="auto", verbose=False)

    convention = sofa.GLOBAL_SOFAConventions
    if convention != "SimpleFreeFieldHRIR":
        raise SystemExit(f"not an HRIR set: SOFAConventions is {convention!r}")
    if sofa.SourcePosition_Type != "spherical":
        raise SystemExit(f"unhandled SourcePosition_Type {sofa.SourcePosition_Type!r}")

    source_rate = int(np.atleast_1d(sofa.Data_SamplingRate)[0])
    az_el = np.asarray(sofa.SourcePosition, dtype=np.float64)[:, :2]
    ir = np.asarray(sofa.Data_IR, dtype=np.float32)

    ir, gain = normalise(resample(ir, source_rate))
    itd, itd_far_ear = estimate_itd(ir)
    directions = sofa_directions(az_el)

    return HrirSet(
        name=f"{sofa.GLOBAL_DatabaseName} / {sofa.GLOBAL_Title}",
        licence=str(sofa.GLOBAL_License),
        ir=ir,
        directions=directions,
        az_el=az_el,
        source_rate=source_rate,
        delay=np.asarray(sofa.Data_Delay, dtype=np.float64),
        gain=gain,
        itd=itd,
        itd_far_ear=itd_far_ear,
        minphase=minimum_phase(ir),
        tri=triangulate(directions),
    )


def render(
    hrir: HrirSet,
    x: np.ndarray,
    path: Callable[[int], tuple[np.ndarray, np.ndarray]],
    *,
    crossfade: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Render mono `x` along a direction path. Returns `(stereo, block times)`."""
    engine = Engine(hrir, crossfade=crossfade)
    blocks = len(x) // engine.block
    azimuth, elevation = path(blocks)
    out = np.zeros((2, blocks * engine.block))
    elapsed = np.empty(blocks)

    for b in range(blocks):
        chunk = x[b * engine.block : (b + 1) * engine.block]
        start = time.perf_counter()
        y = engine.process(chunk, float(azimuth[b]), float(elevation[b]))
        elapsed[b] = time.perf_counter() - start
        out[:, b * engine.block : (b + 1) * engine.block] = y

    return out, elapsed


def write_wav(path: Path, stereo: np.ndarray) -> np.ndarray:
    """Normalise below full scale and write a float32 stereo WAV."""
    peak = float(np.abs(stereo).max())
    scaled = (stereo * (RENDER_PEAK / peak)).astype(np.float32) if peak > 0 else stereo
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(path), RATE, scaled.T.copy())
    return scaled


def render_all(
    hrir: HrirSet, *, seconds: float = RENDER_SECONDS, crossfade: bool = True
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """The four files the spike exists to produce."""
    n = int(seconds * RATE)
    noise = pink_noise(n) * burst_envelope(n)
    tone = band_limited_sawtooth(440.0, n)
    bursts = burst_train(n)

    renders = {
        "orbit_noise": render(hrir, noise, orbit_path, crossfade=crossfade),
        "orbit_tone": render(hrir, tone, orbit_path, crossfade=crossfade),
        # The A/B. Always uncrossfaded, whatever the flag says - it is the
        # control, and a control that follows the switch proves nothing.
        "orbit_tone_nocrossfade": render(hrir, tone, orbit_path, crossfade=False),
        "front_back_bursts": render(hrir, bursts, front_back_path, crossfade=crossfade),
    }
    return {
        name: (write_wav(OUT_DIR / f"{name}.wav", audio), times)
        for name, (audio, times) in renders.items()
    }


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #


def info(hrir: HrirSet) -> None:
    energy = float(np.mean(np.sum(hrir.ir.astype(np.float64) ** 2, axis=2)))
    print(
        f"""
dataset      {hrir.name}
licence      {" ".join(hrir.licence.split())[:78]}
positions    M = {hrir.m}
taps         N = {hrir.n}
rate         {hrir.source_rate} Hz as stored -> {RATE} Hz internal
azimuth      {hrir.az_el[:, 0].min():.1f} .. {hrir.az_el[:, 0].max():.1f} deg
elevation    {hrir.az_el[:, 1].min():.1f} .. {hrir.az_el[:, 1].max():.1f} deg
Data_Delay   {np.unique(hrir.delay)} samples
normalised   {20 * np.log10(hrir.gain):+.2f} dB applied
mean energy  {energy:.4f} per ear (target {TARGET_EAR_ENERGY})
peak         {np.abs(hrir.ir).max():.4f}
"""
    )

    # SOFA azimuth increases anticlockwise, so 90 is the listener's left. The
    # far ear must be the opposite one on every row; that it is, is the whole
    # point of printing this rather than a single summary number.
    print("ITD, horizontal plane      (azimuth 90 = left, 270 = right)\n")
    print("    azimuth    ITD samples      ms    far ear")
    for az, samples, ms, far in horizontal_itd(hrir):
        print(f"    {az:7.1f}    {samples:11.2f}   {ms:5.3f}    {EAR_NAMES[far]}")

    max_itd = hrir.max_itd_samples
    nfft = nfft_for(hrir.n, max_itd)
    used = BLOCK + hrir.n + max_itd - 1
    print(
        f"""
max ITD      {max_itd} samples ({max_itd / RATE * 1e3:.3f} ms), from the data
nfft         {nfft} = next_pow2({BLOCK} + {hrir.n} + {max_itd} - 1)
             {nfft - used} samples of slack over the {used} needed
"""
    )

    _, h_itd = horizontal_sweep(hrir)
    _, v_itd = elevation_sweep(hrir)
    h_step = np.abs(np.diff(np.r_[h_itd, h_itd[0]]))  # closed orbit
    v_step = np.abs(np.diff(v_itd))
    euler = 2 * hrir.m - 4
    print(
        f"""triangles    {hrir.tri.f} faces over {hrir.m} directions (2M-4 = {euler})
continuity   horizontal 1 deg: max step {h_step.max():.3f} samples
             elevation sweep:  max step {v_step.max():.3f} samples
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--info", action="store_true", help="print the dataset summary")
    parser.add_argument("--check", action="store_true", help="run the phase checks")
    parser.add_argument(
        "--render", action="store_true", help="write the four WAVs to spikes/out/"
    )
    parser.add_argument(
        "--no-crossfade",
        action="store_true",
        help="disable the per-block filter crossfade (D-37), for experimenting",
    )
    args = parser.parse_args()
    if not (args.info or args.check or args.render):
        parser.print_help()
        return 0

    hrir = load()
    if args.info:
        info(hrir)
    if args.render:
        for name, (_, times) in render_all(
            hrir, crossfade=not args.no_crossfade
        ).items():
            print(
                f"  {name:24} block mean {times.mean() * 1e3:.2f} ms, "
                f"p99 {np.percentile(times, 99) * 1e3:.2f} ms"
            )
    if args.check:
        import checks

        return checks.run(hrir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
