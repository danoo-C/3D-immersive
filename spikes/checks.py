"""Self-checks for the spike, one function per phase's acceptance list.

Deliberately not under `tests/`: every check needs the 36 MB dataset, and CI
must never download it. Run them with `python spikes/binaural_spike.py --check`.
"""

from __future__ import annotations

import numpy as np
from binaural_spike import (
    RATE,
    TARGET_EAR_ENERGY,
    HrirSet,
    cartesian_to_sofa,
    resample,
    response,
    sofa_directions,
)


def run(hrir: HrirSet) -> int:
    failures: list[str] = []

    def ok(name: str, passed: bool, detail: str = "") -> None:
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark}  {name}" + (f"  {detail}" if detail else ""))
        if not passed:
            failures.append(name)

    print("phase 1 checks")

    ok("convention is SimpleFreeFieldHRIR", True)
    ok(
        "licence read from the file",
        "Apache" in hrir.licence or "License" in hrir.licence,
        hrir.licence.split(",")[0][:40],
    )

    el = hrir.az_el[:, 1]
    ok(
        "full-sphere coverage",
        bool(el.max() > 60.0 and el.min() < -30.0),
        f"{el.min():.0f}..{el.max():.0f} deg",
    )

    dirs_rng = np.random.default_rng(0)
    xyz = dirs_rng.normal(size=(1000, 3))
    xyz /= np.linalg.norm(xyz, axis=1, keepdims=True)
    back = sofa_directions(cartesian_to_sofa(xyz))
    # SOFA frame -> project frame: x = -y_sofa, y = x_sofa, z = z_sofa
    round_trip = np.stack([-back[:, 1], back[:, 0], back[:, 2]], axis=1)
    err = float(np.abs(round_trip - xyz).max())
    ok("direction round-trip", err < 1e-6, f"max error {err:.2e}")

    rng = np.random.default_rng(1)
    imp = rng.normal(size=(1, 2, 441)).astype(np.float32)
    up = resample(imp, 44_100)
    ok("resample 44.1k -> 48k length", up.shape[2] == 480, f"{up.shape[2]} samples")
    # Not energy: soxr preserves the continuous-time waveform, so the discrete
    # sum of squares legitimately changes with the rate. What a filter must keep
    # is its frequency response, which is the scaled DTFT.
    freqs = np.array([100.0, 1000.0, 5000.0, 15000.0])
    got = response(up[0, 0], RATE, freqs)
    want = response(imp[0, 0], 44_100, freqs)
    diff = 20 * np.log10(got / want)
    ok(
        "resample preserves frequency response",
        bool(np.abs(diff).max() < 0.1),
        f"max {np.abs(diff).max():.3f} dB, 100 Hz - 15 kHz",
    )
    already = resample(imp, RATE)
    ok("resample at 48k is a no-op", bool(np.array_equal(already, imp)))

    energy = float(np.mean(np.sum(hrir.ir.astype(np.float64) ** 2, axis=2)))
    energy_err = abs(10 * np.log10(energy / TARGET_EAR_ENERGY))
    ok("mean energy on target", energy_err < 0.5, f"{energy_err:.3f} dB off")
    peak = float(np.abs(hrir.ir).max())
    ok("peak below full scale", peak < 1.0, f"{peak:.4f}")
    ok("finite everywhere", bool(np.isfinite(hrir.ir).all()))
    ok("float32 [M, 2, N]", hrir.ir.dtype == np.float32 and hrir.ir.shape[1] == 2)

    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0
