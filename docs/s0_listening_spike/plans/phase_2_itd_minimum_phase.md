# Plan — S0 · Phase 2 — ITD and minimum phase

**Written:** 2026-09-21 · **Status:** in progress

## Approach

Two independent operations on the array phase 1 left behind, not one operation
with two outputs. For every one of the 8802 measurements:

- a **broadband ITD**, estimated from the pair of ears, stored as an unsigned
  magnitude in (fractional) samples plus which ear is the far one;
- a **minimum-phase HRIR** per ear, built from that ear's magnitude spectrum
  alone and carrying no delay at all.

They are computed separately and neither is derived from the other. That is
worth stating because the obvious mental model — "remove the ITD from the HRIR
and what is left is the minimum-phase part" — is wrong in a way that hides:
minimum-phase extraction discards *all* excess phase, the interaural delay and
any all-pass residual together, so subtracting an ITD estimate first would
double-count whatever the estimate got wrong. Estimate the delay; build the
minimum-phase response; keep both; let phase 4 put them back together.

**Minimum phase via the real cepstrum**, as §2 of
[05-audio-engine.md](../../05-audio-engine.md) specifies. The fold is the
textbook one: `log|H|` → `irfft` → double the causal quefrencies, zero the
anticausal ones → `exp(rfft(·))`. The alternative, a Hilbert transform of the
log-magnitude, is mathematically the same construction with the same aliasing
caveats and one fewer visible step — which is exactly why it is not used here.
When this goes wrong it goes wrong *inside* the fold, and a version where the
fold is a line you can print is worth more in a spike than a version where it
is inside `scipy.signal.hilbert`.

**ITD by cross-correlation of low-passed ears, with an onset-threshold
estimator kept beside it.** Low-passing before correlating is not an
optimisation: ITD is a low-frequency cue, and above roughly 1.5 kHz head-shadow
ripple makes the correlation peak broad and occasionally bimodal, which is how
a plausible-looking ITD field acquires a handful of directions that are a
millisecond wrong. The onset estimator shares no machinery with the
correlation, which is the entire reason to keep it — two estimators that agree
because they are the same algorithm twice would be worse than one.

Sub-sample refinement by parabolic interpolation around the correlation peak.
Phase 4 applies the delay as a frequency-domain phase ramp, so fractional
values cost nothing there, and phase 3 has to interpolate this field and check
it is continuous to better than a sample — which a sample-quantised field
cannot be.

## Steps

1. **ITD by cross-correlation.** Low-pass both ears (4th-order Butterworth,
   1.5 kHz, zero-phase via `filtfilt` so the filter itself adds no delay),
   cross-correlate, parabolic-refine the peak, convert lag to magnitude plus a
   far-ear index.
   *Test:* first against a **synthetic pair** — one ear a unit impulse, the
   other the same impulse delayed by a known 17 samples — which pins down
   scipy's correlation sign convention by experiment rather than by reading it
   out of the docs and hoping. Then on real data: the printed horizontal-plane
   table at 0°, ±30°, ±60°, ±90°, within ±2 samples of zero at the front and
   reaching 0.6–0.8 ms near the poles, and an assertion that the far ear at
   +90° azimuth is the contralateral one.

2. **ITD by onset threshold, and the agreement check.** First sample where an
   ear's envelope crosses −20 dB relative to *that ear's own* peak; ITD is the
   difference. Per-ear rather than a shared absolute threshold, because the far
   ear is head-shadowed and a shared threshold measures the shadow as much as
   the delay.
   *Test:* the two estimators agree within 2 samples for at least 95% of
   directions. The disagreements are **printed with their directions**, never
   averaged away — if they cluster near the poles or at the contralateral
   shadow that is a property of the method and belongs in the phase Notes; if
   they are scattered uniformly, something is wrong.

3. **`max_itd_samples`, and the `nfft` it implies.** Computed from the
   resampled data, printed, never hardcoded.
   *Test:* it lands in 30–70 samples at 48 kHz, and
   `next_pow2(512 + 256 + ceil(max_itd) - 1)` is printed alongside it. Phase 4
   sizes its buffers from this number, and the cost estimate in
   [05-audio-engine.md](../../05-audio-engine.md) assumes it comes out at 1024
   — so this step is where that assumption is confirmed or the estimate is
   wrong, one phase before anything depends on it.

4. **Minimum phase via the real cepstrum.** `nfft = 1024` (4× the 256 taps) so
   the cepstrum decays before it wraps; `log|H|` floored at −100 dB relative to
   each response's own peak, because HRTFs have deep pinna notches and an
   unfloored `log(0)` puts an infinity into the cepstrum; fold; `exp`; inverse;
   truncate back to 256 taps.
   *Test:* `|FFT(minphase)|` within 0.5 dB of `|FFT(original)|` between 100 Hz
   and 16 kHz over 20 pseudo-random directions with a fixed seed; and over 90%
   of cumulative energy inside the first quarter of the taps for the same
   sample, which is what makes truncating back to 256 taps free and is the
   cheapest proof that the fold went the right way round. A fold with the
   causal and anticausal halves swapped produces a *maximum*-phase response
   whose magnitude check passes perfectly and whose energy sits at the end.

5. **Wire it into `HrirSet`, `--info` and `--check`.** Two new arrays beside
   the existing ones — `itd` `[M]` float32 and `itd_far_ear` `[M]` uint8 — and
   `minphase` `[M, 2, N]` replacing nothing: the original stays, because phase
   4's no-wraparound check convolves against it.
   *Test:* `--check` prints the phase 2 block and exits zero; `--info` prints
   the horizontal ITD table, `max_itd_samples` and the implied `nfft`.

Five steps, inside the six [09-workflow.md](../../09-workflow.md) allows.

### One extra check, deliberately not a gate

After step 4, print the **reconstruction residual**: take the minimum-phase
pair, delay the far ear by the estimated ITD, and compare against the original
HRIR. It will not be zero — there is usually a small all-pass component that
neither output captures — and `05` does not claim it would be. It is printed
rather than asserted because nobody knows yet what a normal value is for this
dataset, and inventing a threshold now would either pass vacuously or fail for
a reason that is not a bug. What it is for: if it comes out *large*, the
decomposition is not describing the data and phase 4 would be building on
sand. Record the number in the phase Notes so phase 4 and M4 have a baseline.

## Files

```
spikes/binaural_spike.py    amended — ITD and minimum-phase functions,
                            two new HrirSet fields, --info additions
spikes/checks.py            amended — the phase 2 check block
```

Nothing under `src/`, nothing under `tests/`. The checks stay in the spike and
CI never sees them, for the reason phase 1's plan gives: `testpaths` is
deliberately `["tests"]`, and no CI matrix leg should download 36 MB for a
throwaway script.

## ⚠️ The line budget has to be settled before phase 4

Not a risk — an arithmetic problem, raised here because this is the phase where
it starts to bind and the last comfortable moment to answer it.

The spike is **227 lines** today against the roadmap's *"under ~300 lines"*,
and phase 4's acceptance carries *"the script stays under 300 lines"* as a
checkbox. What is left to write:

| | estimate |
|---|---|
| now, after phase 1 | 227 |
| phase 2 — two estimators, the cepstral fold, wiring | ~55 |
| phase 3 — hull, KD-tree, barycentric query | ~32 |
| phase 4 — bank, ITD ramp, crossfade, block loop, four renders, timing | ~116 |
| **total** | **~430** |

So phase 4's acceptance is written to fail, by about 50%. Phase 2 fits (227 +
55 = 282) and phase 3 does not, which is why this cannot be left to phase 4 to
discover.

Two ways to settle it, and this plan does not get to choose — the constraint
lives in the S0 section of [06-roadmap.md](../../06-roadmap.md) and in
[phase 4's acceptance](../phase_4_block_engine.md), and per
[09-workflow.md](../../09-workflow.md) changing an acceptance line means saying
so explicitly:

1. **Raise the number to ~450 in both places**, with a note that the original
   was an estimate made before any of the DSP was written.
2. **Split the DSP into `spikes/hrtf.py`** beside `checks.py`, leaving the
   script as fetch, load, render and `main`.

**Recommendation: (1).** What the constraint was protecting is in the
roadmap's own words — *"not generalised, not tidied, not moved into `src/`
afterwards"* — and none of that changes at 450 lines. The line count was a
proxy for "do not build a library", and splitting the DSP into an importable
module is a closer thing to building a library than writing 430 honest lines
in one file. A spike is also read top to bottom exactly once, by someone
deciding whether to trust it, and one file is the form that serves that.

Phase 1's split of `checks.py` is not a precedent against this: it moved *test
code*, on the argument that test code is not what a script's line budget is
measuring. The DSP is precisely what it is measuring.

This is a correction to a spec claim rather than a judgement between real
alternatives, so I do not think it earns a `D-` row —
[doc-system.md](../../doc-system.md) §3's "an implementation detail with one
sensible option: write the prose". Worth a sentence in the roadmap saying the
number moved and why, so the next person does not read 450 and assume drift.

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| scipy's cross-correlation sign convention is easy to get backwards, and a sign error here is audible and invisible in every summary statistic | The whole spike sounds mirrored, and phase 5 blames the dataset | Step 1 pins it against a synthetic pair with a known delay *before* real data is loaded. The acceptance's contralateral assertion is the second net |
| Deep pinna notches make `log\|H\|` explode | Garbage cepstrum, minimum-phase output full of NaN | Floor at −100 dB relative to each response's own peak; assert finite afterwards, which is cheap and catches it immediately |
| `nfft` too small for the cepstrum, so it time-aliases | Minimum-phase magnitudes quietly wrong by a fraction of a dB — passes the 0.5 dB check while being wrong | Use 4× the tap count, and **re-run once at 2048** comparing the two. If they differ, 1024 was too small. Half an hour, once |
| The two estimators disagree on more than 5% of directions | The acceptance line fails and it is not obvious whether the method or the threshold is at fault | Two knobs only — the low-pass cutoff and the onset threshold — and the disagreements are printed by direction before either is touched. Tuning against a percentage without looking at *which* directions fail is how a systematic error gets tuned into invisibility |
| ITD is ill-defined where it is near zero and the correlation peak is broad — the median plane, directly overhead | Noisy values in the field that phase 3 then has to interpolate smoothly | Expected, not a fault. The acceptance only asserts the horizontal plane; print the median-plane spread and hand it to phase 3, which is where continuity is actually tested |
| `Data_Delay` was zero for this dataset, and step 1 assumes nothing else carries a stored delay | Nothing here; it bites on the next dataset | Phase 1 already reads and prints it. Assert it is zero rather than ignoring it, so a non-zero one stops the run instead of silently biasing every ITD |

The genuine unknown is the **reconstruction residual**. Nobody has measured
what fraction of a KEMAR HRIR is neither minimum-phase magnitude nor broadband
delay. The design in `05` assumes it is small enough to discard; this phase
prints the number that says whether that is true, which is why the extra check
above exists even though no acceptance line asks for it.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| *Applying* the delay — the non-negative phase ramp on the far ear | [phase 4](../phase_4_block_engine.md) |
| Interpolating ITD or spectra between directions | [phase 3](../phase_3_interpolation.md) |
| `nfft`, the frequency-domain bank, any convolution | [phase 4](../phase_4_block_engine.md); this phase only computes the number that sizes it |
| Caching the prepared decomposition | M4. The spike recomputes each run, and at 8802 × 2 × 256 that is seconds |
| The same decomposition inside the package | M4, `audio/hrtf/prepare.py`. Nothing here moves in |
| Choosing the bundled default dataset | QA-30, at M4 |

## Amended while building

**Step 1 done.** Two departures, left visible rather than tidied away.

**The horizontal-plane check gates on milliseconds, not samples.** The
acceptance gives both — "0.6–0.8 ms (roughly 29–38 samples at 48 kHz)" — and
they are not the same band: 0.8 ms is 38.4 samples. This set measures 38.29
samples at azimuth 90, which passes in milliseconds and fails in the rounded
sample figures. Gating on the millisecond band, since that is the criterion
the line states and the sample figures are explicitly "roughly". Recorded
because widening a threshold to make a measurement pass and reading the
threshold correctly look the same in a diff.

**The low-pass cutoff was validated rather than assumed.** The plan argued for
1.5 kHz from theory. Comparing cutoffs across the whole set showed the pole
values barely move, but the *maximum over the sphere* does — 38 samples at the
poles with the low-pass, 44 samples somewhere else without it. That second
number is a spurious peak, so the low-pass is load-bearing rather than
tidiness. The table is in [the phase Notes](../phase_2_itd_minimum_phase.md).

Step 1 also added two checks the acceptance does not ask for, both cheap and
both aimed at failures that every stated check would have passed: the
mirrored synthetic probe (a backwards convention cannot pass by being
backwards consistently) and a monotonic front-to-pole ladder (a spurious peak
between the sampled azimuths).

## Outcome

Filled in at the end. What actually happened, what this plan got wrong, and
anything phase 3 needs to know — including `max_itd_samples`, the implied
`nfft`, the estimator agreement rate and the reconstruction residual, all four
of which phase 3 or phase 4 inherits as a fact rather than an assumption.
