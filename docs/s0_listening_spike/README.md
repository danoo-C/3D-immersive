# S0 — Listening spike

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Workflow:
[09-workflow.md](../09-workflow.md)

A throwaway script, not a milestone. Its only job is to put the two riskiest
decisions in the design — the ITD/minimum-phase split and the unconditional
per-block crossfade (D-37) — into someone's ears before three more milestones
are built on top of them.

Everything it produces lives in `spikes/`, outside `src/`, and is not imported
by the package. It is not tidied or promoted afterwards; if a piece of it turns
out to be useful twice, it gets rewritten properly inside `audio/hrtf/` during
M4.

| Phase | Status |
|---|---|
| [1 — SOFA load](phase_1_sofa_load.md) | ✅ |
| [2 — ITD and minimum phase](phase_2_itd_minimum_phase.md) | ✅ |
| [3 — Spherical interpolation](phase_3_interpolation.md) | ✅ |
| [4 — Block engine and renders](phase_4_block_engine.md) | ✅ |
| [5 — Listening](phase_5_listening.md) | ✅ |

Phases 1–4 are code and each ends at something a test or a printed number can
settle. Phase 5 is the only one whose acceptance is a pair of ears, and it is
the reason the other four exist.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> the four files exist, they have been listened to on headphones, and the set
> the spike ran on is recorded — by name, version and licence — as the leading
> candidate for the bundled default. Choosing that default stays QA-30's, at
> M4. Feeds QA-30 and M4.

This previously read "and a default SOFA set has been chosen", which did not
agree with QA-30 in [07-qa-archive.md](../07-qa-archive.md) — that resolves
the bundled default by listening test **during M4**. The reading recorded here
was that S0 chooses the set it *runs on* and records it as the leading
candidate, which is what "feeds QA-30" implies; the roadmap's wording has now
been corrected to say so, which is where the fix belonged.

## What this spike deliberately does not do

| Not here | Where it belongs |
|---|---|
| More than one source | M4 — including the N-1 benchmark |
| The zero-allocation rule, `out=` everywhere | M4 |
| `sys.setswitchinterval` measurement (D-39) | M4, and it needs a live UI to mean anything |
| Any device output | M2's audition, then M3 |
| A disk cache for the prepared bank | M4 |
| Distance rolloff tuning (D-21) | M4; the spike holds radius constant at 1.5 m |
| Anything under `src/` | nowhere — the spike never moves in |

## Outcome

**S0 is complete, and it did what it was for: D-37 was decided by ear.**

The uncrossfaded fast orbit was described, unprompted and with no prior
description of what to listen for, as *"horrible, like a dial up tone under
the sound"*, against *"a clean tone"* for the crossfaded one. The per-block
filter crossfade is necessary and it works. Three milestones of design now
rest on something heard rather than argued.

| file | verdict |
|---|---|
| `orbit_noise.wav` | ✅ *"sounds so realistic"* — convincingly externalised |
| `orbit_tone.wav` | ✅ the zipper test: no buzz, rasp or roughness |
| `orbit_tone_nocrossfade.wav` | ✅ audibly different; dramatic at 4 rev/s |
| `front_back_bursts.wav` | ✅ motion followable with eyes closed |

Full verdicts in [phase 5's Notes](phase_5_listening.md).

### What the listening found that measurement had not

- **The crossfade's benefit depends on how fast the source moves** — 33.7 dB
  at 1 rev/s down to 8.6 dB at 8. Found only because the first listen
  disagreed with the spec and the disagreement was chased. Now **D-70**, and
  [05](../05-audio-engine.md)'s "clearly audible buzz" claim is corrected in
  place: at 1 rev/s an uncrossfaded held tone sounded realistic.
- **The specified front/back stimulus could not carry its own test.** Clicks
  one sample long gave an inconclusive result; 40 ms pink-noise bursts on the
  same trajectory gave a clear one. The deliverable is now
  `front_back_bursts.wav`.

### What phases 1–4 found on the way

Each of these was a measured surprise, and each would have been expensive
later. Details in the phase Notes.

| | |
|---|---|
| Phase 1 | `soxr` does not conserve discrete energy across a rate change — the plan's test asserted the wrong property |
| Phase 2 | Cross-correlation and onset ITD are different quantities, not two estimates of one (**D-69**); the cepstral `nfft` needs 32× the taps, not the textbook 4×, or the aliasing lands in the pinna notches |
| Phase 3 | A centroid KD-tree cannot guarantee "every query finds a triangle" at any `k`; an exhaustive fallback can, and runs twice in ten thousand |
| Phase 4 | `scipy.signal.sawtooth` aliases badly enough to make the crossfade measure 13 dB instead of 33 — it would have looked exactly like D-37 failing |

### For M4

`max_itd_samples` is 39, so the convolution `nfft` is 1024 — the value
[05](../05-audio-engine.md)'s cost estimate assumes. Per-block time for one
source is 0.20 ms mean, 0.44 ms p99 of a 10.7 ms budget, with the direction
lookup in the loop; N-1's thirty-two sources remain M4's to benchmark. Listen
to the fast orbit before the slow one — it teaches the ear what the artefact
is, and the slow one then takes seconds to judge instead of being a coin flip.

## Notes

**Phase 1.** Running on SADIE II D1 (KEMAR), 8802 positions, full sphere,
48 kHz, 256 taps — and **Apache 2.0**, which is permissive enough to bundle if
M4 wants it. `Data_Delay` is zero, so there is no stored delay for phase 2 to
fold into the ITD, and N = 256 puts phase 4's `nfft` at 1024 as the cost
estimate assumes. Details in [phase 1's Notes](phase_1_sofa_load.md).
