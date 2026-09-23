# S0 · Phase 2 — ITD and minimum phase

**Status:** ✅ complete · **Plan:**
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

- [x] Printed ITD table for the horizontal plane at 0°, ±30°, ±60°, ±90°: the
      value is within ±2 samples of 0 at azimuth 0, and reaches 0.6–0.8 ms
      (roughly 29–38 samples at 48 kHz) near ±90°.
- [x] The ITD is stored as an unsigned magnitude plus which ear is far, not as
      a signed per-ear delay — the representation that lets
      [phase 4](phase_4_block_engine.md) keep both ramps non-negative.
- [x] The far ear is the contralateral one: a source at +90° azimuth delays the
      ear on the opposite side. Asserted, because a sign error here is
      perfectly audible and perfectly easy to miss.
- [x] The two estimators agree on **which ear is far** for at least 99% of the
      directions where `|ITD| > 3` samples — the question a sign error breaks,
      asked only where there is a sign to get wrong.
- [x] Their signed difference has **no systematic offset**: `|median| < 1`
      sample. A bias would mean one of them is calibrated wrong.
- [x] The p95 of `|difference|` is under 8 samples, and the disagreements are
      **structured by shadow depth** rather than scattered — asserted by
      comparing the shadow in the worst decile against the best. Scatter with
      no structure would mean noise in one of the estimators; structure means
      they are measuring different things, which they are.
- [x] The disagreements are printed with their directions rather than averaged
      away.
- [x] `max_itd_samples` is computed from the data, printed, and lands in a
      sanity range of 30–70 samples at 48 kHz. It is never hardcoded.
- [x] Minimum-phase magnitude check: `|FFT(minphase)|` matches `|FFT(original)|`
      within 0.5 dB between 100 Hz and 16 kHz for a random sample of 20
      directions.
- [x] Minimum-phase energy is front-loaded: over 90% of cumulative energy falls
      in the first quarter of the taps, for the same sample.

> **Amended after measurement.** The four lines about the two estimators
> replace one: *"the two estimators agree within 2 samples for at least 95% of
> directions"*. That line cannot be met by an estimator that is independent,
> and it can only be met by one that is not — see the Notes. Amended
> explicitly rather than quietly, per
> [09-workflow.md](../09-workflow.md), and the reasoning is D-69.

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

---

**Step 2 — the onset estimator. Done, and it cost this phase an acceptance
line.** The two estimators are not two estimates of one number, and asking
them to agree within 2 samples was asking for something that is not true.

| Onset estimator | far-ear agreement | median offset | within 2 sa |
|---|---|---|---|
| fullband, −10 dB (independent) | **99.99%** | −0.30 sa | 37% |
| low-pass 1.5 kHz, −10 dB | 100% | +0.02 sa | 48% |
| low-pass 700 Hz, −3 dB | 100% | +0.20 sa | **99.3%** |

The last row passes the original line — and is worthless. At 700 Hz with a
−3 dB threshold the "onset" is the peak of a heavily smoothed envelope, which
is the quantity the cross-correlation already finds. It would have been two
runs of the same algorithm agreeing with itself, which the plan had named in
advance as the thing not to do.

**Why they differ, measured at the worst direction** (azimuth 300°, elevation
+15°, cross-correlation 33.3 samples, onset 20.7):

```
near ear:  peak 0.6507 at sample  95   -10 dB crossing at  95
far  ear:  peak 0.0627 at sample 125   -10 dB crossing at 115
shadow: -20.3 dB
```

The near ear is impulsive enough that it does not reach −10 dB until its own
peak. The far ear is shadowed by 20 dB and its −10 dB crossing fires **ten
samples before its peak**, on a low-level diffracted precursor — the wave that
bends round the head, arriving earlier and much weaker. So cross-correlation
measures the *dominant* delay and the onset threshold measures the *first
arrival*. Both are correct; they are different quantities.

That the divergence is **structure and not noise** is now asserted rather than
argued: the worst decile of disagreements sits at −19.1 dB of shadow, the best
decile at −3.6 dB. No threshold removes it, because it is not an error.

The engine uses the dominant delay — it carries the localisation cue and it is
what the minimum-phase split leaves behind. **D-69** records that, and records
what the cross-check is worth: 99.99% agreement on which ear is far, which
catches a sign flip, a spurious correlation peak or a mirrored dataset. Those
are the errors that would otherwise survive to phase 5. M4 inherits the same
distinction when it rebuilds this in `audio/hrtf/prepare.py`.

⚠️ **The plan's −20 dB threshold was wrong and is now −10 dB.** At −20 dB on
an unfiltered HRIR the crossing lands in the pre-ringing: far-ear agreement
collapses to 73% and outliers reach 62 samples. Measured, not assumed.

---

**Step 3 — `max_itd_samples` and the `nfft` it sizes. Done.**

```
max ITD      39 samples (0.812 ms), from the data
nfft         1024 = next_pow2(512 + 256 + 39 - 1)
             218 samples of slack over the 806 needed
```

**Phase 4's `nfft` is 1024, which is what
[05-audio-engine.md](../05-audio-engine.md)'s cost estimate assumes.** Settled
one phase before anything depends on it, which is what this step was for.

The 218 samples of slack matter more than they look. `ceil(max_itd)` is not a
strict bound on a *fractional* delay — a phase ramp is sinc interpolation and
spreads a little either side of the nominal sample — so a buffer sized exactly
to the formula would be relying on `next_pow2` rounding up. Here it rounds up
by 218 samples, and that is printed rather than assumed.

**The largest ITD in the set is at azimuth 90°, elevation 0° — the interaural
pole, exactly where it has to be.** That is now asserted, and it is the
cheapest check in the file: it tests all 8802 directions at once, where the
front-to-pole ladder from step 1 samples four of them and would walk past a
spurious peak anywhere else.

"Never hardcoded" is also asserted rather than asked for on trust: a synthetic
pair delayed by 12 samples must produce 12, which a constant tuned to this
dataset's 39 would fail.

---

**Step 4 — minimum phase via the real cepstrum. Done.** Magnitude preserved to
**0.017 dB** over 100 Hz – 16 kHz, and **99.1%** of each response's energy
inside the first quarter of its taps, which is what makes truncating back to
256 taps free.

⚠️ **The "4× the impulse length" rule of thumb for the cepstral `nfft` is
wrong for HRIRs, and this plan had specified it.** The cepstrum must decay
before it wraps its own buffer, and the log magnitude of a deep pinna notch
decays very slowly, so the aliasing lands precisely at the nulls:

| cepstral `nfft` | worst in-band error | bins over 0.5 dB |
|---|---|---|
| 1024 (4×) | 5.489 dB | 39 |
| 2048 (8×) | 4.490 dB | 5 |
| 4096 (16×) | 0.886 dB | 1 |
| **8192 (32×)** | **0.017 dB** | **0** |

At 1024 the error is 0.155 dB everywhere within 30 dB of the peak, so nothing
but a check aimed straight at the notches would have caught it. The plan's
risk table had "re-run once at 2048 and compare" as a half-hour mitigation;
it is the only reason this was found.

⚠️ **Two different `nfft`s now exist and they are not the same number.** The
cepstral one is 8192 and comes from how fast a log spectrum decays. Phase 4's
convolution one is 1024 and comes from `block + taps + ITD`. Conflating them
is easy and would be expensive in both directions.

One consequence: the whole-set minimum-phase pass at 8192 would peak at
several GB as a single batched transform, so it is chunked 512 directions at
a time. Load went from ~2 s to 7.6 s. Fine for a spike; M4 caches the prepared
bank ([05](../05-audio-engine.md) §4) and pays it once.

### ⚠️ The reconstruction residual is large, and that is the finding

The plan added a diagnostic no acceptance line asks for: rebuild the original
from its two halves — minimum phase, far ear delayed by the estimated ITD —
and measure what is left. It said, in advance, that *"if it comes out large,
the decomposition is not describing the data and phase 4 would be building on
sand."*

It came out large. Against the best common time alignment, searched rather
than guessed:

```
median +0.1 dB, worst +1.1 dB   (residual RMS relative to the signal)
  100 Hz - 1 kHz   -4.8 dB
    1 kHz - 4 kHz  +1.2 dB
    4 kHz - 8 kHz  -0.3 dB
    8 kHz - 16 kHz +0.8 dB
```

A residual at 0 dB means the error waveform is about the size of the signal.
The magnitude spectra agree to 0.017 dB, so this is **entirely phase**: the
all-pass component that minimum-phase extraction discards is, in waveform
terms, substantial.

**This is not a bug, and it is not a reason to stop.** Minimum phase plus a
broadband delay was never a waveform model — [05](../05-audio-engine.md) §2
says the minimum-phase part is "the remaining spectral cue", and the entire
reason for the split is that magnitudes and delays each interpolate cleanly
while raw HRIRs do not. A model that discards inaudible excess phase is doing
what it was designed to do. The measurement does not say the design is wrong.

**What it does say is that the design's central assumption is load-bearing and
still untested.** "The discarded all-pass is inaudible" is an assumption, this
number is how much is being discarded, and nothing in phases 1–4 can settle
it. [Phase 5](phase_5_listening.md) can. It now has a concrete thing to listen
for beyond the zipper test: whether a source rendered this way sounds *placed*
as convincingly as the dataset should allow, particularly in the 1–4 kHz band
where the residual is worst and where front/back cues live.

If phase 5 says it does not, the escalation is not a fix to this script — it
is an M4 design question about keeping some excess phase, and a decision-log
entry. That boundary is [phase 5's scope](phase_5_listening.md), unchanged.
