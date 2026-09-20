#!/usr/bin/env python3
"""S0 — the listening spike.

Throwaway. Not part of the package, not imported by anything, never moved into
`src/`. See docs/s0_listening_spike/ for what each phase of it is for.

Phase 1: fetch a SOFA set, validate it, convert its directions, resample to
48 kHz and normalise the level.

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

    return HrirSet(
        name=f"{sofa.GLOBAL_DatabaseName} / {sofa.GLOBAL_Title}",
        licence=str(sofa.GLOBAL_License),
        ir=ir,
        directions=sofa_directions(az_el),
        az_el=az_el,
        source_rate=source_rate,
        delay=np.asarray(sofa.Data_Delay, dtype=np.float64),
        gain=gain,
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
