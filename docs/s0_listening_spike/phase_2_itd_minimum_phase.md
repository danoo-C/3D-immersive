# S0 · Phase 2 — ITD and minimum phase

**Status:** in progress · **Plan:**
[plans/phase_2_itd_minimum_phase.md](plans/phase_2_itd_minimum_phase.md)

## Goal

Each loaded HRIR is decomposed once into two things that interpolate cleanly on
their own: a scalar broadband ITD in samples, and a minimum-phase HRIR with
that delay removed. This is the step
[05-audio-engine.md](../05-audio-engine.md) §2 calls the one that makes or
breaks the whole pipeline, and it is worth more scrutiny here than anywhere
else in the spike — a quiet error becomes flanging on every moving source three
milestones later, where it will be blamed on the crossfade.

## Scope

**In:** ITD estimation by cross-correlation of the two ears, with an
onset-threshold estimator kept as an independent cross-check; minimum-phase
decomposition via the real cepstrum; `max_itd_samples` computed from the
resampled data and printed.

**Out:** *applying* the delay, which is a frequency-domain phase ramp in
[phase 4](phase_4_block_engine.md). Interpolating between directions →
[phase 3](phase_3_interpolation.md).

## Acceptance

- [ ] Printed ITD table for the horizontal plane at 0°, ±30°, ±60°, ±90°: the
      value is within ±2 samples of 0 at azimuth 0, and reaches 0.6–0.8 ms
      (roughly 29–38 samples at 48 kHz) near ±90°.
- [ ] The ITD is stored as an unsigned magnitude plus which ear is far, not as
      a signed per-ear delay — the representation that lets
      [phase 4](phase_4_block_engine.md) keep both ramps non-negative.
- [ ] The far ear is the contralateral one: a source at +90° azimuth delays the
      ear on the opposite side. Asserted, because a sign error here is
      perfectly audible and perfectly easy to miss.
- [ ] The two estimators agree within 2 samples for at least 95% of directions;
      the disagreements are printed with their directions rather than averaged
      away.
- [ ] `max_itd_samples` is computed from the data, printed, and lands in a
      sanity range of 30–70 samples at 48 kHz. It is never hardcoded.
- [ ] Minimum-phase magnitude check: `|FFT(minphase)|` matches `|FFT(original)|`
      within 0.5 dB between 100 Hz and 16 kHz for a random sample of 20
      directions.
- [ ] Minimum-phase energy is front-loaded: over 90% of cumulative energy falls
      in the first quarter of the taps, for the same sample.

## Implements

§2 *Split ITD from spectrum* of [05-audio-engine.md](../05-audio-engine.md),
and the *Delays must be non-negative on both ears* rule from §4, whose
representation is decided here even though it is applied later. Mitigates the
"HRTF interpolation artifacts" row of the risk register in
[06-roadmap.md](../06-roadmap.md).

## Notes

**Step 1 — ITD by cross-correlation. Done; all of this phase's ITD acceptance
lines pass.** Measured on SADIE II D1:

```
    azimuth    ITD samples      ms    far ear
        0.0           0.37   0.008    left
       30.0          15.08   0.314    right
       60.0          33.68   0.702    right
       90.0          38.29   0.798    right
      270.0          38.09   0.794    left
      300.0          34.31   0.715    left
      330.0          15.73   0.328    left
```

**The 1.5 kHz low-pass earns its place on evidence, not on principle.** It was
chosen in the plan on the argument that head-shadow ripple above ~1.5 kHz
broadens the correlation peak. Measured across the whole set:

| Cutoff | ITD at ±90° | max over all 8802 |
|---|---|---|
| none (fullband) | 39 / 38 sa | **44 sa** |
| 1.5 kHz | 38 / 38 sa | **38 sa** |
| 3 kHz | 38 / 37 sa | 40 sa |
| 8 kHz | 39 / 39 sa | 44 sa |

The tell is not the pole values, which barely move — it is that with the
low-pass the **maximum over the entire sphere occurs at the poles**, where
physics says it must. Without it the maximum is 44 samples *somewhere else*,
which can only be a spurious peak. Fullband would have produced an ITD field
with a handful of directions ~6 samples wrong and no summary statistic
complaining.

⚠️ **The acceptance's sample figures are a rounded version of its millisecond
band, and this set falls in the gap.** 0.8 ms is 38.4 samples; the acceptance
says "roughly 29–38". The measured 38.29 samples is 0.798 ms — inside the
stated band, outside the rounded parenthetical. The check gates on
milliseconds, which is the criterion the line actually states. Flagged rather
than quietly widened, because "the number was just outside so I moved it" and
"the units in the acceptance disagree with each other" look identical in a
diff.

**Early sighting for step 3, not yet confirmed:** the maximum ITD over the set
is ~38 samples, which puts phase 4's
`next_pow2(512 + 256 + ceil(38) - 1) = next_pow2(805)` at **1024** — the value
[05-audio-engine.md](../05-audio-engine.md)'s cost estimate assumes. Step 3
measures and asserts this properly.

**Sign convention.** Pinned by a synthetic pair (impulse at sample 100 in the
left ear, 117 in the right) *and* its mirror image, so a convention that is
backwards cannot pass by being backwards consistently. A positive
cross-correlation lag means the left ear is the later one. Contralateral
behaviour on real data is asserted separately at azimuth 90 and 270.
