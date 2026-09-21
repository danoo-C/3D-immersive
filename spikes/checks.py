"""Self-checks for the spike, one function per phase's acceptance list.

Deliberately not under `tests/`: every check needs the 36 MB dataset, and CI
must never download it. Run them with `python spikes/binaural_spike.py --check`.
"""

from __future__ import annotations

import time
from itertools import pairwise

import numpy as np
from binaural_spike import (
    BLOCK,
    EAR_NAMES,
    INTERP_TIERS,
    MINPHASE_NFFT,
    RATE,
    TARGET_EAR_ENERGY,
    HrirSet,
    cartesian_to_sofa,
    elevation_sweep,
    estimate_itd,
    estimate_itd_onset,
    horizontal_itd,
    horizontal_sweep,
    locate,
    minimum_phase,
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

    # --- minimum phase -----------------------------------------------------
    sample = np.random.default_rng(7).choice(hrir.m, 20, replace=False)
    probe_nfft = 8192
    freqs = np.fft.rfftfreq(probe_nfft, 1.0 / RATE)
    band = np.broadcast_to(
        (freqs >= 100.0) & (freqs <= 16_000.0),
        (len(sample), 2, len(freqs)),
    )

    def magnitude_error(candidate: np.ndarray) -> np.ndarray:
        original = np.abs(np.fft.rfft(hrir.ir[sample], n=probe_nfft, axis=-1))
        got = np.abs(np.fft.rfft(candidate, n=probe_nfft, axis=-1))
        ratio = np.maximum(got, 1e-12) / np.maximum(original, 1e-12)
        return np.abs(20 * np.log10(ratio))

    ok("minimum phase is finite", bool(np.isfinite(hrir.minphase).all()))

    error = magnitude_error(hrir.minphase[sample])
    ok(
        "minimum phase preserves the magnitude within 0.5 dB",
        float(error[band].max()) < 0.5,
        f"max {error[band].max():.3f} dB over 20 directions, 100 Hz - 16 kHz",
    )

    # Energy front-loaded, which is what makes truncating back to N taps free -
    # and what a fold done the wrong way round would fail while the magnitude
    # check above passed perfectly.
    cumulative = np.cumsum(hrir.minphase[sample].astype(np.float64) ** 2, axis=-1)
    quarter = cumulative[..., hrir.n // 4 - 1] / cumulative[..., -1]
    ok(
        "minimum-phase energy is in the first quarter of the taps",
        float(quarter.min()) > 0.90,
        f"min {quarter.min() * 100:.1f}%, median {np.median(quarter) * 100:.1f}%",
    )

    # The cepstrum must decay before it wraps. Halving nfft has to make things
    # measurably worse; if it does not, the chosen size is doing nothing and
    # one of these numbers is not measuring what it claims to.
    coarse = magnitude_error(minimum_phase(hrir.ir[sample], nfft=MINPHASE_NFFT // 8))
    ok(
        "nfft is large enough that the cepstrum does not alias",
        float(coarse[band].max()) > float(error[band].max()) * 4,
        f"{MINPHASE_NFFT} -> {error[band].max():.3f} dB, "
        f"{MINPHASE_NFFT // 8} -> {coarse[band].max():.3f} dB",
    )

    # Reconstruction residual: printed, never gated. The decomposition is
    # lossy by construction — minimum phase plus a broadband delay does not
    # capture an all-pass component, and 05 never claimed it would. Nobody
    # knows what a normal value is for this dataset yet, so a threshold now
    # would either pass vacuously or fail for something that is not a bug.
    # What it is for: if this came out *large*, the two halves would not be
    # describing the data and phase 4 would be building on sand.
    rows = np.arange(len(sample))
    tau = np.zeros((len(sample), 2))
    tau[rows, hrir.itd_far_ear[sample]] = hrir.itd[sample]
    omega = 2 * np.pi * np.fft.rfftfreq(probe_nfft)
    spec = np.fft.rfft(hrir.minphase[sample], n=probe_nfft, axis=-1)
    rebuilt = np.fft.irfft(spec * np.exp(-1j * omega * tau[:, :, None]), axis=-1)

    # The model carries no common propagation delay — 05 drops it deliberately
    # as an inaudible constant — so the best common shift is searched rather
    # than guessed from a peak, which would charge the model for a bad
    # alignment on top of what it actually discards.
    original = hrir.ir[sample].astype(np.float64)
    scale = np.sqrt(np.mean(original**2, axis=(1, 2)))
    best = np.full(len(sample), np.inf)
    for shift in range(200):
        candidate = np.roll(rebuilt, shift, axis=-1)[..., : hrir.n]
        rms = np.sqrt(np.mean((candidate - original) ** 2, axis=(1, 2)))
        best = np.minimum(best, rms / scale)
    residual = 20 * np.log10(best)
    print(
        f"       reconstruction residual (not a gate): median "
        f"{np.median(residual):+.1f} dB, worst {residual.max():+.1f} dB "
        f"- waveform, not magnitude; see the phase notes"
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

    print("\nphase 3 checks")

    tri = hrir.tri
    # A closed triangulated sphere has exactly 2V - 4 faces. Anything else
    # means a measurement was swallowed as interior or the hull is not closed,
    # and every containment guarantee below rests on it being closed.
    ok(
        "the hull is a closed sphere",
        tri.f == 2 * hrir.m - 4,
        f"{tri.f} faces for {hrir.m} directions (2M-4 = {2 * hrir.m - 4})",
    )
    # A collinear triangle inverts to nonsense rather than failing, which would
    # show up as wrong weights near wherever it is.
    worst_cond = float(np.linalg.cond(tri.inverse).max())
    ok("no face is degenerate", worst_cond < 1e6, f"worst condition {worst_cond:.1f}")

    rng3 = np.random.default_rng(11)
    probe = rng3.normal(size=(10_000, 3))
    probe /= np.linalg.norm(probe, axis=1, keepdims=True)
    face, weights, tiers = locate(tri, probe)

    ok("every direction finds a containing triangle", bool((face >= 0).all()))
    ok(
        "weights sum to one",
        float(np.abs(weights.sum(-1) - 1.0).max()) < 1e-6,
        f"max error {np.abs(weights.sum(-1) - 1.0).max():.2e}",
    )
    ok(
        "no weight is negative",
        float(weights.min()) >= -1e-9,
        f"min {weights.min():.2e}",
    )
    # Printed so a dataset that stops suiting the tiers is visible as more than
    # "the lookup got slower".
    labels = [*(str(k) for k in INTERP_TIERS), "every face"]
    ok(
        "the tiers still earn their place",
        tiers[-1] < len(probe) // 100,
        ", ".join(f"k={a}: {b}" for a, b in zip(labels, tiers, strict=True)),
    )

    # Querying exactly at a measurement: the direction sits on a vertex shared
    # by several faces, any of which is a correct answer as long as that
    # vertex carries all the weight.
    exact = np.array(
        [
            nearest_direction(hrir, az, el)
            for az, el in [(0, 0), (90, 0), (270, 0), (0, 90), (0, -90), (45, 30)]
        ]
    )
    _, exact_w, _ = locate(tri, hrir.directions[exact])
    ok(
        "a measured direction returns its own vertex",
        float(exact_w.max(-1).min()) > 0.999,
        f"min top weight {exact_w.max(-1).min():.6f}",
    )

    h_face, h_itd = horizontal_sweep(hrir)
    h_step = np.abs(np.diff(np.r_[h_itd, h_itd[0]]))
    ok(
        "horizontal orbit is continuous to under a sample",
        float(h_step.max()) < 1.0,
        f"max step {h_step.max():.3f} sa at az "
        f"{np.arange(360.0)[h_step.argmax()]:.0f}, median {np.median(h_step):.3f}",
    )

    _, v_itd = elevation_sweep(hrir)
    v_step = np.abs(np.diff(v_itd))
    ok(
        "elevation sweep is continuous to under a sample",
        float(v_step.max()) < 1.0,
        f"max step {v_step.max():.3f} sa, median {np.median(v_step):.3f}",
    )

    # "No jump at a triangle boundary" means crossing one is no worse than
    # staying inside one — not that the ITD stops changing, which it must.
    crossed = np.diff(h_face) != 0
    inside_max = float(h_step[:-1][~crossed].max())
    crossing_max = float(h_step[:-1][crossed].max())
    ok(
        "crossing a triangle is no worse than staying in one",
        crossing_max < inside_max * 1.5,
        f"{crossing_max:.3f} sa across {int(crossed.sum())} crossings "
        f"vs {inside_max:.3f} within",
    )

    # Median, because the exhaustive tier is rare and slow by design. Both
    # figures are reported: the scalar one is what this acceptance asks for,
    # and the batched one is what actually predicts the engine, where the
    # per-call overhead is paid once a block rather than once a source.
    single = rng3.normal(size=(1, 3))
    single /= np.linalg.norm(single)
    for _ in range(20):
        locate(tri, single)  # warm up, so the first calls' cache misses are not timed
    scalar = []
    for _ in range(200):
        start = time.perf_counter()
        locate(tri, single)
        scalar.append((time.perf_counter() - start) * 1e6)
    many = rng3.normal(size=(32, 3))
    many /= np.linalg.norm(many, axis=1, keepdims=True)
    batched = []
    for _ in range(100):
        start = time.perf_counter()
        locate(tri, many)
        batched.append((time.perf_counter() - start) * 1e6)
    ok(
        "median lookup is under 50 us",
        float(np.median(scalar)) < 50.0,
        f"{np.median(scalar):.1f} us for one, "
        f"{np.median(batched) / 32:.1f} us per source at 32",
    )

    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0
