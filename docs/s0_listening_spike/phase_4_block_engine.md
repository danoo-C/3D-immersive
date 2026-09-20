# S0 · Phase 4 — Block engine and renders

**Status:** not started · **Plan:** not written yet —
`plans/phase_4_block_engine.md`

## Goal

The per-block engine for exactly one source at block 512, including the
input-windowed crossfade (D-37) and the buffer-length and delay-sign
constraints from §4 of [05-audio-engine.md](../05-audio-engine.md) — and the
four WAV files it exists to produce.

This is the phase that has to be *correct* rather than *good*: it is a
throwaway script, but it is the only evidence that the design in `05` actually
sounds like anything before M4 commits to it.

## Scope

**In:** the prepared frequency-domain bank at `nfft`; the ITD applied as a
non-negative phase ramp on the far ear only; the two-copy input-windowed
crossfade; overlap-add; an 8 s render loop driven by an analytic orbit; a
`--no-crossfade` flag; per-block timing statistics.

**Out:** multiple sources, summing in the frequency domain, the scheduler,
distance rolloff, the limiter, any device output, and the zero-allocation rule
— all M4. Radius is fixed at 1.5 m and level is constant.

## Acceptance

- [ ] Four files in `spikes/out/`, each 8 s, 48 kHz, stereo, float32-sourced:
      `orbit_noise.wav`, `orbit_tone.wav`, `orbit_tone_nocrossfade.wav`,
      `front_back_clicks.wav`. No NaN, no sample at or above full scale.
- [ ] `nfft` is printed and equals `next_pow2(block + N + max_itd_samples - 1)`
      using the value measured in [phase 2](phase_2_itd_minimum_phase.md).
- [ ] No circular wraparound: with an impulse as input and a fixed direction,
      the far-ear response begins at its expected offset and the buffer's first
      samples are silent to below −120 dBFS.
- [ ] Block-loop output for a *static* direction matches a direct, whole-signal
      convolution with the same interpolated filter to better than −60 dBFS.
      This separates "the engine is wrong" from "the motion sounds wrong".
- [ ] The crossfade is demonstrably running: `orbit_tone.wav` and
      `orbit_tone_nocrossfade.wav` differ by more than −40 dBFS RMS, **and**
      the energy at the 93.75 Hz block rate and its sidebands around the 440 Hz
      tone is at least 20 dB lower in the crossfaded file. Two files that
      measure the same mean the flag is not wired up.
- [ ] Per-block processing time printed as mean and p99, with p99 well under
      the 10.7 ms budget for this single source — a first data point for the M4
      benchmark, not a substitute for it.
- [ ] The script imports nothing beyond numpy, scipy, `sofar` and `soxr`, is
      not imported by the package, and nothing in it has moved into `src/`.

## Implements

D-37, the *Prepare the bank* buffer-length and non-negative-delay rules, and
the per-block pseudocode — all §4 and *Per-block processing* of
[05-audio-engine.md](../05-audio-engine.md). The block rate and the 512-frame
default come from that document's fixed-parameters table.

## Notes

**Acceptance amended before this phase started, twice, and the second time it
lost its number.** It read "the script stays under 300 lines"; that was raised
to 450 during phase 2, and phase 2 then finished at 506 with two phases still
to go. Both figures were estimates of *code* lines against a budget measured
in *total* lines, and the second was wrong by more than the first.

So the count is gone and the clause that was always doing the work stays:
four dependencies, never imported by the package, nothing promoted into
`src/`. Those are checkable; a line count that has to be renegotiated every
phase is not. The full reasoning is in the S0 constraints of
[06-roadmap.md](../06-roadmap.md) and in the Outcome of
[the phase 2 plan](plans/phase_2_itd_minimum_phase.md). Recorded here because
[09-workflow.md](../09-workflow.md) says an acceptance line may change only if
someone says so out loud — which applies no less when the change is a removal.
