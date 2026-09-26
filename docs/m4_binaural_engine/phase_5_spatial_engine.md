# M4 · Phase 5 — The engine, spatial

**Status:** planned · **Plan:** [plans/phase_5_spatial_engine.md](plans/phase_5_spatial_engine.md)

## Goal

The engine plays every channel that is not bypassed through the HRTF: each
channel's block, downmixed to a mono point (D-16), scaled by its distance
(D-21), windowed twice for the crossfade (D-37), transformed in one batched
FFT, multiplied by its interpolated filter with its ITD as a non-negative
phase ramp on the far ear, and **summed over sources in the frequency
domain** before four inverse transforms and an overlap-add (05, *Per-block
processing*). It does this without allocating, as the flat engine does.

## Scope

**In:** positions reaching the audio thread (the plan's first decision);
distance gain with its per-sample ramp; the lookup, the gather and weighting
of the bank, the ITD ramp; the input-windowed crossfade with `H_prev` reset
on a seek and on a snapshot swap; the overlap-add tail and its reset; the
channel peaks tapped before the HRTF (D-117); the zero-allocation test held
over it all.

**Out:** bypassed channels and the master bus → phase 6. Setting a
position from the pane → phase 7.

## Acceptance

- [ ] An impulse at a measured direction comes out as that direction's
      minimum-phase pair with its ITD on the far ear, to within float32.
- [ ] A source at the front is equal in both ears, one at +X is louder and
      earlier in the right, and one at −X the reverse.
- [ ] Halving the distance past `ref_distance` raises the level by
      `rolloff × 6.02` dB, and inside `min_distance` it stops rising.
- [ ] A band-limited 440 Hz sawtooth orbiting at 1 rev/s has block-rate
      sidebands at least 20 dB lower with the crossfade than with it
      disabled by a test-only switch - S0's measure and S0's line, where it
      measured 33.7 dB - so the crossfade is provably running (the
      roadmap's named test, measured). *Amended while planning: as first
      written this compared against S0's uncrossfaded figure, a number from
      another engine; the A/B within this one is the measure S0 used.*
- [ ] No sample is discontinuous across a seek or a snapshot swap: the
      first block after either does not crossfade from a stale filter.
- [ ] `process()` allocates nothing and keeps nothing with 32 spatial
      sources moving, by the zero-allocation test.
- [ ] Four channels summed in the frequency domain equal the four convolved
      alone and added, to within float32.

## Implements

D-16, D-21, D-37, D-70, D-106, D-117 - *Per-block processing* and
*Parameter smoothing* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
