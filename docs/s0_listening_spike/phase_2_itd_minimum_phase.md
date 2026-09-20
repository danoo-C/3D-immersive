# S0 · Phase 2 — ITD and minimum phase

**Status:** not started · **Plan:** not written yet —
`plans/phase_2_itd_minimum_phase.md`

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

Appended while building.
