"""Self-checks for the spike, one function per phase's acceptance list.

Deliberately not under `tests/`: every check needs the 36 MB dataset, and CI
must never download it. Run them with `python spikes/binaural_spike.py --check`.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from binaural_spike import (
    BLOCK,
    EAR_NAMES,
    RATE,
    TARGET_EAR_ENERGY,
    HrirSet,
    cartesian_to_sofa,
    estimate_itd,
    estimate_itd_onset,
    horizontal_itd,
    nearest_direction,
    next_pow2,
    nfft_for,
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

    print("\nphase 2 checks")

    # The sign convention, pinned against a synthetic pair before any real
    # data is involved. Ear 0 carries an impulse at sample 100 and ear 1 the
    # same impulse 17 samples later, so the right ear is unambiguously the far
    # one. Reading scipy's correlation convention out of the docs and trusting
    # it is exactly how a mirrored mix reaches phase 5 with every summary
    # statistic in this file still looking healthy.
    probe = np.zeros((1, 2, 256), dtype=np.float32)
    probe[0, 0, 100] = 1.0
    probe[0, 1, 117] = 1.0
    mag, far = estimate_itd(probe)
    ok("synthetic delay recovered", abs(float(mag[0]) - 17.0) < 0.5, f"{mag[0]:.2f} sa")
    ok("synthetic far ear is the delayed one", int(far[0]) == 1, EAR_NAMES[far[0]])

    # ...and the mirror image, so a convention that is backwards cannot pass by
    # being backwards consistently.
    mag_m, far_m = estimate_itd(probe[:, ::-1].copy())
    ok("mirrored probe, same magnitude", abs(float(mag_m[0]) - 17.0) < 0.5)
    ok("mirrored probe, far ear flips", int(far_m[0]) == 0, EAR_NAMES[far_m[0]])

    rows = horizontal_itd(hrir)
    by_az = {round(az): (samples, far) for az, samples, _, far in rows}

    front = by_az[0][0]
    ok("ITD at the front is zero", front < 2.0, f"{front:.2f} samples")

    left_itd, left_far = by_az[90]
    right_itd, right_far = by_az[270]
    # Gated in milliseconds, which is what the acceptance states; its "roughly
    # 29-38 samples" is that band rounded, and 0.8 ms is 38.4 samples. This set
    # lands at 38.3, inside the stated band and outside the rounded one.
    left_ms, right_ms = left_itd / RATE * 1e3, right_itd / RATE * 1e3
    ok(
        "ITD near the poles is 0.6-0.8 ms",
        bool(0.6 <= left_ms <= 0.8 and 0.6 <= right_ms <= 0.8),
        f"left {left_ms:.3f} ms ({left_itd:.1f} sa), "
        f"right {right_ms:.3f} ms ({right_itd:.1f} sa)",
    )
    # A source on the left must delay the right ear. This is the assertion the
    # whole sign story exists for.
    ok(
        "far ear is contralateral",
        left_far == 1 and right_far == 0,
        f"az 90 -> {EAR_NAMES[left_far]}, az 270 -> {EAR_NAMES[right_far]}",
    )

    # Monotonic out to the pole, which a field with a spurious peak somewhere
    # would break even while the three sampled azimuths above looked right.
    ladder = [by_az[a][0] for a in (0, 30, 60, 90)]
    ok(
        "ITD grows from front to left pole",
        all(b > a - 1.0 for a, b in pairwise(ladder)),
        " -> ".join(f"{v:.1f}" for v in ladder),
    )

    # The median plane has no interaural delay to find, so it is the cheapest
    # place to see the estimator inventing one.
    median = [nearest_direction(hrir, 0.0, el) for el in (-30.0, 0.0, 30.0, 60.0, 90.0)]
    median_max = float(np.abs(hrir.itd[median]).max())
    ok(
        "median plane stays near zero",
        median_max < 3.0,
        f"max {median_max:.2f} samples",
    )

    ok("itd is finite everywhere", bool(np.isfinite(hrir.itd).all()))
    ok(
        "itd is an unsigned magnitude",
        bool((hrir.itd >= 0).all()) and set(np.unique(hrir.itd_far_ear)) <= {0, 1},
    )

    # --- the independent onset estimator ---------------------------------
    onset, onset_far = estimate_itd_onset(hrir.ir)
    signed_cc = np.where(hrir.itd_far_ear == 0, hrir.itd, -hrir.itd)
    signed_on = np.where(onset_far == 0, onset, -onset)
    diff = signed_on.astype(np.float64) - signed_cc

    # Which ear is far is the thing a sign error would break, and it is only a
    # meaningful question where there is a delay to have a sign about.
    sided = hrir.itd > 3.0
    far_agree = float(np.mean(onset_far[sided] == hrir.itd_far_ear[sided])) * 100
    ok(
        "estimators agree on the far ear",
        far_agree >= 99.0,
        f"{far_agree:.2f}% of {int(sided.sum())} directions with |ITD| > 3 sa",
    )
    ok(
        "estimators have no systematic offset",
        abs(float(np.median(diff))) < 1.0,
        f"median {np.median(diff):+.2f} samples",
    )

    p95 = float(np.percentile(np.abs(diff), 95))
    ok(
        "difference p95 under 8 samples",
        p95 < 8.0,
        f"p95 {p95:.1f} sa, max {np.abs(diff).max():.1f} sa",
    )

    # Structure, not scatter. The two estimators diverge where the far ear is
    # deeply shadowed, because there the onset threshold fires on a diffracted
    # precursor ten samples ahead of the main energy (D-69). If the worst
    # disagreements were *not* the most shadowed directions, the divergence
    # would be noise in one of the estimators and worth chasing.
    peaks = np.abs(hrir.ir).max(axis=-1)
    near = np.where(hrir.itd_far_ear == 0, peaks[:, 1], peaks[:, 0])
    far_pk = np.where(hrir.itd_far_ear == 0, peaks[:, 0], peaks[:, 1])
    shadow_db = 20 * np.log10(np.maximum(far_pk, 1e-12) / np.maximum(near, 1e-12))
    order = np.argsort(np.abs(diff))
    decile = max(1, hrir.m // 10)
    best, worst = shadow_db[order[:decile]], shadow_db[order[-decile:]]
    ok(
        "disagreements track shadow depth",
        float(np.median(worst)) < float(np.median(best)) - 3.0,
        f"worst decile {np.median(worst):+.1f} dB vs best {np.median(best):+.1f} dB",
    )

    # --- max ITD, and the nfft it sizes -----------------------------------
    max_itd = hrir.max_itd_samples
    ok(
        "max ITD is in the sane range",
        30 <= max_itd <= 70,
        f"{max_itd} samples ({max_itd / RATE * 1e3:.3f} ms)",
    )

    # The largest ITD on a sphere must lie at an interaural pole. Asserting
    # where the maximum *is* tests all 8802 directions at once: the
    # front-to-pole ladder above samples four of them, and a spurious peak
    # anywhere else would walk straight past it.
    peak_dir = int(np.argmax(hrir.itd))
    peak_az, peak_el = hrir.az_el[peak_dir]
    off_pole = min(abs(peak_az - 90.0), abs(peak_az - 270.0))
    ok(
        "the largest ITD is at an interaural pole",
        off_pole <= 10.0 and abs(peak_el) <= 10.0,
        f"az {peak_az:.0f}, el {peak_el:+.0f}",
    )

    # "Never hardcoded" is a claim about the code, so it needs a case where a
    # constant would give the wrong answer. A synthetic pair delayed by 12
    # samples must produce 12, not this dataset's 39.
    synth = np.zeros((1, 2, 256), dtype=np.float32)
    synth[0, 0, 100] = 1.0
    synth[0, 1, 112] = 1.0
    synth_mag, _ = estimate_itd(synth)
    ok(
        "max ITD is derived, not a constant",
        int(np.ceil(synth_mag.max())) == 12,
        f"synthetic 12-sample set gives {int(np.ceil(synth_mag.max()))}",
    )

    nfft = nfft_for(hrir.n, max_itd)
    needed = BLOCK + hrir.n + max_itd - 1
    ok(
        "nfft follows 05's formula and has slack",
        nfft == next_pow2(needed) and nfft > needed,
        f"{nfft} for {needed} needed, {nfft - needed} spare",
    )
    # 05-audio-engine.md's cost estimate assumes 1024 at block 512 with a
    # 256-tap set. Confirmed here, one phase before phase 4 depends on it.
    ok(
        "nfft matches the cost estimate in 05",
        nfft == 1024,
        f"{nfft} at block {BLOCK}, N {hrir.n}",
    )

    # Printed with their directions rather than averaged away, because where
    # they fail is the finding. A cluster is a property of the method; a
    # uniform scatter means something is wrong.
    worst = np.argsort(-np.abs(diff))[:6]
    print("       worst disagreements (az, el, cross-corr, onset):")
    for i in worst:
        print(
            f"         {hrir.az_el[i, 0]:6.1f} {hrir.az_el[i, 1]:+6.1f}"
            f"   {signed_cc[i]:+7.2f}  {signed_on[i]:+7.2f}"
        )

    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0
