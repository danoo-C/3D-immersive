# Plan — S0 · Phase 5 — Listening

**Written:** 2026-09-21, *during the phase rather than before it* ·
**Status:** ✅ complete

## Why this one was written late

[09-workflow.md](../../09-workflow.md) puts the plan before the code, and this
phase has no code. Its content is a person putting on headphones, and the
listening had already started before there was anything to plan. Writing a
route in advance and dating it as though it had guided the walk would be the
documentation fiction [doc-system.md](../../doc-system.md) §8 warns about.

It is written at all because the *protocol* turned out to have content, and M4
repeats these listening tests with the dataset QA-30 finally picks. What
follows is what was actually done, including the two things that had to be
fixed mid-listening before the files could answer anything.

## Approach

Four renders, judged on headphones, on a machine that plays them properly —
not over WSLg, per the development environment note in
[06-roadmap.md](../../06-roadmap.md). No measurement is admissible here. The
whole point of the phase is that a number cannot settle what it asks.

The order matters and was not planned: `orbit_noise` first, because if
localisation does not work at all then nothing after it means anything.

## What had to be fixed mid-phase

**The stimulus in `front_back_clicks.wav` was too weak to carry the test.**
The listener reported being unable to tell what was happening, and correctly
diagnosed why: the clicks were too short. Each was a single sample, about
20 µs. Front/back is the hard direction — interaural time and level are nearly
identical in front and behind, so almost the only cue separating them is the
spectral notch pattern the pinna imposes, and that is a timbre judgement with
essentially no signal to make it from.

Replaced with 40 ms pink-noise bursts every 160 ms, 3 ms raised-cosine edges,
on the *identical* trajectory so the comparison stayed clean. One variable.
The file is now `front_back_bursts.wav`; the roadmap's table and phase 4's
acceptance were updated to match, rather than leaving a file named for a
stimulus it no longer uses.

This is repairing the instrument, not acting on a verdict, so it stays inside
this phase's scope. The boundary the Scope section draws — that a crossfade
found insufficient or an ITD split found wrong is an M4 design change — is
about the *engine*, not the test signals.

**The A/B was unfair, mildly.** The two orbit-tone renders were each
normalised to peak independently, so they did not play at matched level.
Measured afterwards at only 0.10 dB apart in RMS, so it changed nothing — but
it was checked rather than assumed, and a commonly-scaled pair
(`ab_crossfade.wav` / `ab_nocrossfade.wav`) was rendered to remove the doubt.

**A faster orbit was added to calibrate the ear.** At 1 rev/s the listener
found the crossfaded and uncrossfaded renders nearly as good as each other,
which is not what D-37 predicts. Rather than argue, a 4 rev/s pair was
rendered, where the artefact is about 7 dB louder in absolute terms. That
settled it immediately and produced the speed-dependence finding behind D-70.

## Files listened to

| file | role |
|---|---|
| `orbit_noise.wav` | is it convincingly externalised and followable |
| `orbit_tone.wav` | **the zipper test** |
| `orbit_tone_nocrossfade.wav` | the A/B |
| `front_back_bursts.wav` | elevation and front/back |
| `ab_crossfade.wav` / `ab_nocrossfade.wav` | the same pair, commonly scaled |
| `fast_orbit_crossfade.wav` / `fast_orbit_nocrossfade.wav` | 4 rev/s, to calibrate |

The last four are diagnostics, not deliverables. They are not in the roadmap's
table and are not reproduced by `--render`.

## Outcome

**Every acceptance line passes.** The verdicts themselves are in
[the phase doc's Notes](../phase_5_listening.md), which is where
[09](../../09-workflow.md) says they belong.

**What this phase was for, it did.** D-37 was the riskiest decision in the
design and it was decided by ear, unprompted and in the right direction: the
uncrossfaded fast orbit was described as *"horrible, like a dial-up tone under
the sound"* with no prior description of what the artefact should sound like.
That is the strongest form the evidence could have taken.

**Two things the listening found that no measurement had.** The stimulus
problem above, which would have left the elevation test permanently
inconclusive. And the speed dependence of the crossfade — D-70 — which was
discovered only because the first listen disagreed with the spec and the
disagreement was chased rather than filed.

**For M4, which repeats this:** listen to the fast orbit first. It teaches the
ear what the artefact is, and the slow one is then judgeable in seconds rather
than being a coin flip.
