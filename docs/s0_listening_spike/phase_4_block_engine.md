# S0 · Phase 4 — Block engine and renders

**Status:** ✅ complete · **Plan:**
[plans/phase_4_block_engine.md](plans/phase_4_block_engine.md)

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

- [x] Four files in `spikes/out/`, each 8 s, 48 kHz, stereo, float32-sourced:
      `orbit_noise.wav`, `orbit_tone.wav`, `orbit_tone_nocrossfade.wav`,
      `front_back_clicks.wav`. No NaN, no sample at or above full scale.
- [x] `nfft` is printed and equals `next_pow2(block + N + max_itd_samples - 1)`
      using the value measured in [phase 2](phase_2_itd_minimum_phase.md).
- [x] No circular wraparound: with an impulse as input and a fixed direction,
      the far-ear response begins at its expected offset and the buffer's first
      samples are silent to below −120 dBFS.
- [x] Block-loop output for a *static* direction matches a direct, whole-signal
      convolution with the same interpolated filter to better than −60 dBFS.
      This separates "the engine is wrong" from "the motion sounds wrong".
- [x] The crossfade is demonstrably running: `orbit_tone.wav` and
      `orbit_tone_nocrossfade.wav` differ by more than −40 dBFS RMS, **and**
      the energy at the 93.75 Hz block rate and its sidebands around the 440 Hz
      tone is at least 20 dB lower in the crossfaded file. Two files that
      measure the same mean the flag is not wired up.
- [x] Per-block processing time printed as mean and p99, with p99 well under
      the 10.7 ms budget for this single source — a first data point for the M4
      benchmark, not a substitute for it.
- [x] The script imports nothing beyond numpy, scipy, `sofar` and `soxr`, is
      not imported by the package, and nothing in it has moved into `src/`.

## Implements

D-37, the *Prepare the bank* buffer-length and non-negative-delay rules, and
the per-block pseudocode — all §4 and *Per-block processing* of
[05-audio-engine.md](../05-audio-engine.md). The block rate and the 512-frame
default come from that document's fixed-parameters table.

## Notes

**Done. Every acceptance line passes.** `--check` prints 59 checks and exits
zero; the four files are in `spikes/out/`, gitignored.

```
orbit_noise              block mean 0.19 ms, p99 0.41 ms
orbit_tone               block mean 0.20 ms, p99 0.39 ms
orbit_tone_nocrossfade   block mean 0.20 ms, p99 0.50 ms
front_back_clicks        block mean 0.24 ms, p99 0.59 ms
```

**The crossfade works, and the measurement says so with room to spare:**
**33.7 dB** of block-rate sideband reduction against a 20 dB bar (−69.6 dB
versus −35.9 dB below the 440 Hz carrier), and the two renders differ by
−21.6 dBFS against a −40 dB bar. That is the number this entire spike was
built to produce. It is not a verdict — [phase 5](phase_5_listening.md) is —
but D-37 is no longer an argument.

Per-block time is **0.20 ms mean, 0.44 ms p99** against a 10.7 ms budget, for
one source, with `locate` inside the loop. N-1's thirty-two sources are M4's.

⚠️ **`scipy.signal.sawtooth` would have failed this phase, and it would have
looked like D-37 being wrong.** It is a naive time-domain generator with no
band limiting: at 440 Hz into 48 kHz it puts −20.1 dB of energy off the
harmonic grid, against −109 dB for a sum of harmonics below Nyquist. That
aliased hash raises the *crossfaded* render's floor by 22 dB — the
uncrossfaded one barely moves — and drags the measured reduction from 33 dB to
13 dB, under the acceptance. Caught while planning, and now asserted so it
cannot return as an obvious simplification. It would have misled phase 5 too:
broadband roughness is exactly what the zipper test listens for.

⚠️ **Two acceptance lines needed their measurement pinned down, and both would
otherwise have read as engine bugs.**

*The static-direction reference.* "A direct, whole-signal convolution with the
same interpolated filter" has two readings and they disagree by as much as
either disagrees with the engine:

| reference | result |
|---|---|
| `irfft(H)`, then linear-convolve | −59.9 dBFS — **fails** |
| convolve with the minimum phase, then delay the whole signal | **−68.9 dBFS** — passes |
| the two references against each other | −59.5 dBFS |

The first takes a filter that is *circular* by construction and feeds it to a
linear convolution, so the fractional ramp's wrapped tail becomes a real echo.
The second is the operation the engine approximates, so it is the one used.

*The wraparound line.* It asks for "the buffer's first samples silent to below
−120 dBFS", and with a **fractional** delay that is not achievable for a
reason that has nothing to do with wrapping: a fractional delay is sinc
interpolation, so it rings *before* its own onset by construction — 1/(π·22) at
22 samples early, about −37 dB, measured at −42 dB. The check therefore
measures wraparound with a **whole-sample** delay, where any energy ahead of
the onset can only have wrapped: **−192 dBFS**, far below the bar. The
fractional precursor is printed beside it rather than quietly dropped.

**The engine's exactness floor is the bank's precision, not −300 dB.** With a
whole-sample delay the filter is compactly supported and overlap-add is exact;
what remains is complex64, which round-trips at −184 dB and gives a block-loop
match of **−155 dBFS**. The plan predicted −300 from a float64 probe and was
wrong about the reason rather than the conclusion. A complex128 bank reaches
−343 dB and costs 144 MB, buying nothing against a −69 dB working floor.

So the chain reads: −155 dB is the arithmetic, −69 dB is what the fractional
ITD ramp costs on top of it, and that is the price of D-37's sub-sample delay
over the audible stair-step of a quantised one.

**One thing this phase broke elsewhere.** Adding the 72 MB bank changed the
memory pressure around phase 3's timing check, which started flapping between
43 and 79 µs. It now takes the best of several batch medians rather than one:
scheduling noise only ever adds time, so the cheapest batch is the closest
estimate of what the code costs, and averaging would have measured the
machine's load. Stable at 42.6–43.4 µs across six runs.

---

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
