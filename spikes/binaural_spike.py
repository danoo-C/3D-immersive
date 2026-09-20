#!/usr/bin/env python3
"""S0 — the listening spike.

Throwaway. Not part of the package, not imported by anything, never moved into
`src/`. See docs/s0_listening_spike/ for what each phase of it is for.

Phase 1: fetch a SOFA set, validate it, convert its directions, resample to
48 kHz and normalise the level.
Phase 2: split each measurement into a broadband ITD and a minimum-phase HRIR.

    python spikes/binaural_spike.py --info
    python spikes/binaural_spike.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sofar
import soxr
from scipy import signal

# SADIE II D1 — the KEMAR dummy head, already 48 kHz, 256 taps. The York URL
# in the roadmap's prose is dead; this is the sofacoustics.org mirror. The
# digest is here so a truncated download or a swapped mirror fails loudly.
URL = "https://sofacoustics.org/data/database/sadie/D1_48K_24bit_256tap_FIR_SOFA.sofa"
SHA256 = "e6c72a84dd947b5ef75438ab96a9c2a32ed10f033472b9c4c11a49aff00a8a31"
DATA_DIR = Path(__file__).parent / "data"

RATE = 48_000  # docs/05-audio-engine.md, fixed parameters

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

    @property
    def m(self) -> int:
        return int(self.ir.shape[0])

    @property
    def n(self) -> int:
        return int(self.ir.shape[2])


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

    return HrirSet(
        name=f"{sofa.GLOBAL_DatabaseName} / {sofa.GLOBAL_Title}",
        licence=str(sofa.GLOBAL_License),
        ir=ir,
        directions=sofa_directions(az_el),
        az_el=az_el,
        source_rate=source_rate,
        delay=np.asarray(sofa.Data_Delay, dtype=np.float64),
        gain=gain,
        itd=itd,
        itd_far_ear=itd_far_ear,
    )


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
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--info", action="store_true", help="print the dataset summary")
    parser.add_argument("--check", action="store_true", help="run the phase checks")
    args = parser.parse_args()
    if not (args.info or args.check):
        parser.print_help()
        return 0

    hrir = load()
    if args.info:
        info(hrir)
    if args.check:
        import checks

        return checks.run(hrir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
