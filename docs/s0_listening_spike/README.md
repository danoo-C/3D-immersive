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
| [2 — ITD and minimum phase](phase_2_itd_minimum_phase.md) | not started |
| [3 — Spherical interpolation](phase_3_interpolation.md) | not started |
| [4 — Block engine and renders](phase_4_block_engine.md) | not started |
| [5 — Listening](phase_5_listening.md) | not started |

Phases 1–4 are code and each ends at something a test or a printed number can
settle. Phase 5 is the only one whose acceptance is a pair of ears, and it is
the reason the other four exist.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> the four files exist, they have been listened to on headphones, and a default
> SOFA set has been chosen. Feeds QA-30 and M4.

⚠️ That last clause and QA-30 in [07-qa-archive.md](../07-qa-archive.md) do not
quite agree: QA-30 resolves the default dataset by listening test **during M4**.
The reading taken here is that S0 chooses the set it *runs on* and records it as
the leading candidate, and QA-30's pick stays an M4 task — which is what "feeds
QA-30" implies. If that reading is wrong, the roadmap's wording is the thing to
fix, not this file.

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

## Notes

**Phase 1.** Running on SADIE II D1 (KEMAR), 8802 positions, full sphere,
48 kHz, 256 taps — and **Apache 2.0**, which is permissive enough to bundle if
M4 wants it. `Data_Delay` is zero, so there is no stored delay for phase 2 to
fold into the ITD, and N = 256 puts phase 4's `nfft` at 1024 as the cost
estimate assumes. Details in [phase 1's Notes](phase_1_sofa_load.md).
