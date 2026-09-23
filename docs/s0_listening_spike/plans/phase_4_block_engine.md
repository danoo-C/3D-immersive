# Plan — S0 · Phase 4 — Block engine and renders

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

The per-block engine for one source, exactly as the pseudocode in
[05-audio-engine.md](../../05-audio-engine.md) *Per-block processing* describes
it, minus everything that only matters with more than one source. Prepare the
bank once; per block, locate the direction, weight three spectra, apply the ITD
as a phase ramp, convolve two input-windowed copies against the previous and
current filters, overlap-add, write.

Everything below was measured while writing this plan, on the real dataset.
Four of the five acceptance lines already have a number against them, and the
two that surprised me are the reason this document is worth reading before the
code rather than after.

### The bank

`rfft` of the phase 2 minimum-phase set at `nfft = 1024`, giving
`[8802, 2, 513]` complex64 — **72 MB, built in 0.14 s**. No disk cache: that is
an M4 concern and at 0.14 s it would be a cache that costs more to explain than
it saves.

### The ITD ramp, and what it costs

`exp(-2j·π·f·τ)` delays by `τ`; verified against an impulse at τ = 0, 10 and
10.5. Applied as the full `|ITD|` on the far ear and zero on the near one, so
both ramps are non-negative and nothing wraps — the *Delays must be
non-negative on both ears* rule from §4.

⚠️ **A fractional phase ramp is not a compactly supported filter, and that
sets the engine's error floor.** Measured on the far ear at azimuth 45°,
elevation 20°: the filter carries **−47.9 dB of energy beyond 295 taps**, and
the same −47.9 dB beyond 513 and beyond 700. It is a wrapped sinc — spread
across the whole buffer, not decaying within it. Overlap-add with
`nfft = 1024` and `block = 512` supports a filter of at most
`nfft - block + 1 = 513` taps, so some of that tail aliases, and no larger
`nfft` removes it: the block-vs-reference error improves only from −59.9 to
−61.8 dB across a fourfold increase.

This is not a defect to fix, it is the price of D-37's sub-sample delay, which
[05](../../05-audio-engine.md) chose deliberately over the audible stair-step
of a sample-quantised ITD. The number is worth recording as the engine's error
budget, because it is the floor every other measurement in this phase sits on.

### ⚠️ The static-direction check needs its reference named

The acceptance asks the block loop to match "a direct, whole-signal convolution
with the same interpolated filter to better than −60 dBFS". There are two
readings and they disagree:

| reference | result |
|---|---|
| `irfft(H)` — the combined spectrum — then linear-convolve | **−59.9 dBFS**, fails |
| convolve with the 256-tap minimum phase, then delay the whole signal | **−74.1 dBFS**, passes |
| the two references against each other | −59.5 dBFS |

The first is the one you reach for, and it is wrong: it takes a filter that is
*circular* by construction — the fractional ramp above — and feeds it to a
*linear* convolution, so the wrapped sinc tail becomes a real echo instead of
folding back. The two references disagree with each other by as much as either
disagrees with the block loop, which is the tell.

The second is the operation the engine is actually approximating, so it is the
one this phase uses, and it is named here so that a later reader does not
"simplify" the check back into the first and conclude the engine is broken.

The harness is proved separately: with an **integer** ITD the block loop
matches to **−307 dBFS**, which says overlap-add, `nfft` and the tail
bookkeeping are all exact and the −74 dB is entirely the fractional ramp.

### ⚠️ `scipy.signal.sawtooth` aliases, and it would have failed this phase

The acceptance wants the block-rate sidebands around 440 Hz at least 20 dB
lower in the crossfaded render. Measured:

| test signal | crossfaded | no crossfade | reduction |
|---|---|---|---|
| 440 Hz sine | −71.6 dB | −35.9 dB | **35.7 dB** |
| 440 + 880 | −69.1 dB | −35.9 dB | 33.1 dB |
| `scipy.signal.sawtooth` | −48.9 dB | −35.8 dB | **13.1 dB** |
| band-limited sawtooth | −69.1 dB | −35.9 dB | **33.1 dB** |

`scipy.signal.sawtooth` is a naive time-domain generator with no band
limiting: at 440 Hz into 48 kHz it carries **−20.1 dB of energy off the
harmonic grid**, against −108.6 dB for a summed band-limited sawtooth. That
aliased hash sets a floor in the crossfaded render 22 dB above where it should
be, and drags the measured reduction to 13.1 dB — below the acceptance.

The failure would have looked exactly like the crossfade not working, which is
to say like D-37 being wrong, on the one measurement the whole spike exists to
make. **The sawtooth is therefore synthesised as a sum of harmonics below
Nyquist**, and step 4 asserts its off-grid energy so a naive generator cannot
come back.

This matters for [phase 5](../phase_5_listening.md) as much as for the
numbers: an aliased sawtooth has broadband roughness of its own, and broadband
roughness is precisely what the zipper test listens for.

### Crossfade

The two-copy input-windowed form from *Parameter smoothing*, unconditional
every block, with `--no-crossfade` to disable it for the A/B. Measured RMS
difference between the two renders: **−21.5 dBFS**, against the acceptance's
"more than −40".

## Steps

1. **The bank.** `rfft` the minimum-phase set at `nfft`, complex64.
   *Test:* shape `[M, 2, nfft//2+1]`, finite, and `nfft` equals
   `next_pow2(block + N + max_itd_samples - 1)` using phase 2's measured
   value. One entry inverse-transforms back to its own minimum-phase taps.

2. **The filter for a direction.** Barycentric-weighted sum of three bank
   entries (phase 3's `locate`), times the non-negative ITD ramp on the far
   ear.
   *Test:* the no-wraparound line — an impulse in, a fixed direction, the
   far-ear response beginning at its expected offset and the buffer's first
   samples silent below −120 dBFS. Plus a direct check that the ramp delays
   rather than advances, at integer and fractional τ.

3. **The block engine.** Overlap-add, the input-windowed crossfade, and the
   `--no-crossfade` flag.
   *Test:* static direction against the convolve-then-delay reference, better
   than −60 dBFS; and the integer-ITD control against the same reference, which
   must come out near −300 dB. The control is what separates "the engine is
   wrong" from "the fractional ramp costs what it costs".

4. **Signal generators.** Band-limited sawtooth, pink noise in 100 ms
   on/off bursts, and a click train.
   *Test:* the sawtooth's energy off the harmonic grid is below −60 dB. This
   is the check that stops `scipy.signal.sawtooth` from being reintroduced as
   an obvious simplification.

5. **The four renders, and timing.** The orbit at 1 rev/s, ear level, 1.5 m;
   the front → overhead → behind sweep; 8 s each into `spikes/out/`.
   *Test:* four files, 8 s, stereo, finite, no sample at or above full scale;
   the crossfade RMS difference above −40 dBFS and the sideband reduction at
   least 20 dB; per-block time as mean and p99, p99 well inside the 10.7 ms
   budget.

Five steps, inside the six [09-workflow.md](../../09-workflow.md) allows.

## Files

```
spikes/binaural_spike.py    amended — bank, filter-for-direction, block engine,
                            signal generators, the render entry point
spikes/checks.py            amended — the phase 4 check block
spikes/out/                 new — gitignored (`*.wav` already covers it)
```

Nothing under `src/`, nothing under `tests/`.

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The static-direction reference is chosen wrongly by a later reader | The engine looks broken at −59.9 dB when it is correct at −74.1 | Both references measured and written down above; the integer-ITD control pins the harness at −300 dB independently |
| A naive sawtooth returns | The crossfade measures 13.1 dB and D-37 looks disproved | Step 4 asserts off-grid energy below −60 dB |
| Timing measured on WSL, in Python, with `locate` in the loop | Reads as an engine benchmark, which it is not | Report mean and p99 for one source and say plainly that N-1's 32-source benchmark is M4's, per the phase scope |
| The orbit steps 4° per block at 1 rev/s, so consecutive filters differ more than they will in most real use | Nothing — this is deliberately the hard case | Say so, rather than letting a future reader think it is typical |
| `spikes/out/` accidentally committed | 4 WAV files in git history | `.gitignore` already has `*.wav`; confirmed, and `git status` is checked after the run |

The genuine unknown is **whether three-vertex barycentric weighting is enough
for complex spectra**, which phase 3 raised and could not close. The scalar ITD
interpolates provably continuously; three minimum-phase magnitudes summed with
the same weights should too, because that is exactly what removing the delay
first was for. The failure mode is comb filtering rather than a visible step,
so no number in this phase settles it — only [phase 5](../phase_5_listening.md)
does. The 33.1 dB sideband figure says the *block-rate* artefact is handled; it
says nothing about the *inter-direction* one.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| More than one source, frequency-domain summation | M4, and N-1's benchmark |
| The scheduler, clip reads, fades | M3 |
| Distance rolloff (D-21), the limiter, master gain | M4 — radius is fixed at 1.5 m here and the level is constant |
| The zero-allocation rule and `out=` everywhere | M4 |
| Any device output | M2's audition, then M3 |
| A disk cache for the prepared bank | M4; 0.14 s does not earn one |
| Deciding whether it *sounds* right | [phase 5](../phase_5_listening.md), which is the point of the four files |

## Outcome

**Every acceptance line passes.** `--check` prints 59 checks and exits zero.

**The headline: 33.7 dB.** Block-rate sideband reduction against a 20 dB bar,
and −21.6 dBFS between the crossfaded and plain renders against a −40 dB bar.
D-37 is measured rather than argued. Per-block time 0.20 ms mean, 0.44 ms p99
of a 10.7 ms budget, one source, `locate` in the loop.

**What the plan got right.** Both of the things it spent its probing on. The
band-limited sawtooth and the named static-direction reference were each the
difference between a passing phase and one that looked like D-37 failing. An
implementation that had reached for `scipy.signal.sawtooth` and the obvious
`irfft`-then-convolve reference would have produced 13.1 dB and −59.9 dB, and
the natural conclusion from both would have been that the design is wrong.

**What it got wrong.** Two numbers, one of them interesting:

- The integer-ITD control was predicted at −300 dB and lands at **−155 dB**.
  The plan measured it in float64 and the engine's bank is complex64, which
  round-trips at −184 dB. The conclusion holds — the arithmetic is exact and
  the −69 dB is the fractional ramp — but the floor is the bank's precision,
  not the arithmetic's.
- It did not anticipate that the **wraparound line cannot be measured with a
  fractional delay at all.** A fractional delay is sinc interpolation and
  rings before its own onset by construction, so the "first samples silent
  below −120 dBFS" reads −42 dB for a reason that is not wrapping. Measured
  with a whole-sample delay it is −192 dB. This is the same shape of problem
  as the static-direction reference, and the plan found that one and missed
  this one.

**It also broke a phase 3 check.** The 72 MB bank changed the memory pressure
around the lookup timing, which began flapping between 43 and 79 µs. Fixed by
taking the best of several batch medians instead of one — noise only adds
time, so the cheapest batch is the honest estimate. Stable at 42.6–43.4 µs.

**Handed to [phase 5](../phase_5_listening.md):** four files in `spikes/out/`,
8 s each, 48 kHz float32 stereo, peaking at 0.89.

| file | what it is for |
|---|---|
| `orbit_noise.wav` | is it convincingly outside the head, and followable round |
| `orbit_tone.wav` | **the zipper test** — the one that decides |
| `orbit_tone_nocrossfade.wav` | the A/B. 33.7 dB apart by measurement |
| `front_back_clicks.wav` | elevation, and whether front/back is systematically reversed |

Two things to listen for beyond the acceptance, both inherited rather than
discovered here. From phase 2, whether the discarded all-pass component is
audible — the reconstruction residual is about 0 dB, worst in 1–4 kHz where
front/back cues live. From phase 3, whether three-vertex barycentric weighting
is enough for *complex spectra*: the 33.7 dB says the block-rate artefact is
handled and says nothing about the inter-direction one, whose failure mode is
comb filtering rather than a step.

Nothing in phases 1–4 can settle either. That is what phase 5 is.
