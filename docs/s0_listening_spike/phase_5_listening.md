# S0 · Phase 5 — Listening

**Status:** ✅ complete · **Plan:**
[plans/phase_5_listening.md](plans/phase_5_listening.md)

## Goal

Someone puts on headphones and listens to the four files, and the result is
written down. This phase produces no code. It is the only phase whose
acceptance a test cannot settle, and it is what the other four were for.

## Scope

**In:** listening on real headphones on a machine that can play them properly —
not over WSLg, per the development environment note in
[06-roadmap.md](../06-roadmap.md); recording a verdict per file; recording the
dataset used and how it sounded; filing anything that turns out to be a
judgement call as a new `D-` row in
[01-requirements.md](../01-requirements.md) per
[doc-system.md](../doc-system.md) §3.

**Out:** acting on the verdict. If the crossfade turns out to be insufficient
or the ITD split audibly wrong, that is an M4 design change and a decision-log
entry — not a fix bolted onto a throwaway script.

## Acceptance

- [x] `orbit_noise.wav` — the source is convincingly outside the head and its
      direction is followable through a full revolution.
- [x] `orbit_tone.wav` — **the zipper test.** No buzz, rasp or roughness at the
      block rate while the tone orbits. This is the pass/fail the whole spike
      exists for.
- [x] `orbit_tone_nocrossfade.wav` — A/B'd against the above, and the
      difference is audible. If the two sound identical, D-37 is unproven and
      the measurement in
      [phase 4](phase_4_block_engine.md) needs re-reading before anything else
      is concluded.
- [x] `front_back_bursts.wav` — elevation is perceivable and front/back is not
      systematically reversed. Some front/back confusion on a non-individual
      HRTF is expected and is not a failure. *(Was `front_back_clicks.wav`;
      the stimulus was too short to carry the test and was replaced mid-phase.
      See the Notes.)*
- [x] The dataset used is recorded by name, version and licence, as the leading
      candidate for QA-30 — which is still decided at M4.
- [x] Verdicts and any surprises are appended to the Notes below and summarised
      in [README.md](README.md); decisions go to the log, not here.

## Implements

The "Done when" of S0 in [06-roadmap.md](../06-roadmap.md), the named listening
test attached to D-37, and the evidence behind the "HRTF interpolation
artifacts" row of that document's risk register. Feeds QA-30 and M4.

## Notes

**All five lines pass.** Listened on headphones, off WSLg. Verdicts verbatim
where the wording matters, because how something was described is evidence.

### `orbit_noise.wav` ✅

> *"it sounds so realistic"*

Convincingly externalised and followable through the revolution. This file
exercises the whole chain at once — the ITD/minimum-phase split, barycentric
interpolation, and the crossfade — so a clean result here is the single
broadest piece of evidence the spike produced.

### `orbit_tone.wav` — the zipper test ✅

No buzz, rasp or roughness. Described as *"incredibly realistic"*.

### `orbit_tone_nocrossfade.wav` — the A/B ✅

The line to beat was *"if the two sound identical, D-37 is unproven"*. They are
not identical: the crossfaded render was preferred on both the original pair
and the commonly-scaled one.

⚠️ **But the difference at 1 rev/s was subtle, and that is the finding.** First
report was that the crossfaded file had *"a subtle sharpness"* and that **both
sounded incredibly realistic** — an uncrossfaded held tone, orbiting, with no
audible buzz. That is not what [05](../05-audio-engine.md) predicted.

Two confounds were ruled out before anything was concluded. Independent peak
normalisation made the files play 0.10 dB apart in RMS — negligible, and a
commonly-scaled pair was rendered anyway. And the crossfaded render is
marginally *darker*, not brighter (spectral centroid 1153 vs 1165 Hz), so the
"sharpness" was not added treble.

**A 4 rev/s pair settled it in seconds:**

> *"fast orbit with crossfading is a clean tone and fast orbit nocrossfade
> sound horrible. like a dial up tone under the sound"*

Unprompted, with no prior description of what the artefact should sound like —
and "dial-up tone" is exactly right for a carrier chopped at 93.75 Hz. **D-37
is decided by ear, in the right direction.** The *unconditional* half is
vindicated too: at 1 rev/s the artefact is quiet enough to be missed on a first
listen, so any "only crossfade on a large jump" threshold would have to sit low
enough to fire almost always.

The speed dependence behind all of this is **D-70**, and the overstated claim
in `05` has been corrected in place.

### `front_back_bursts.wav` ✅

> *"i could figure out the motion with closed eyes, but naturally up/down is
> harder to recreate than side to side. but it works"*

Elevation perceivable, front/back not systematically reversed, trajectory
followable with eyes closed. Weaker than azimuth, which is the expected result
rather than a shortcoming: azimuth rides on interaural time and level
differences, which are robust between people, while elevation rides on the
spectral notches of the listener's own pinnae — and this is a KEMAR dummy
head, so it is someone else's ears. The acceptance anticipated exactly this.

⚠️ **The specified stimulus could not carry the test.** `front_back_clicks.wav`
produced only *"focusing on it real hard, i could get the illusion of front to
back"*, with the listener diagnosing the cause unaided: *"the click sound is
too short"*. Each click was one sample, about 20 µs, and front/back is carried
almost entirely by pinna spectral cues, which are a timbre judgement. Replaced
with 40 ms pink-noise bursts on the identical trajectory — one variable — and
the result went from inconclusive to clear. The roadmap table and phase 4's
acceptance now name `front_back_bursts.wav`.

Worth carrying to M4: a stimulus too short to judge would have left the
elevation test permanently ambiguous, and it was found by ear, not by any
measurement in phases 1–4.

### Dataset ✅

**SADIE II D1** — the KEMAR dummy head, from the sofacoustics.org mirror.
8802 positions, full sphere (−90° to +90°), 256 taps, natively 48 kHz,
`Data_Delay` zero. **Apache 2.0**, per its own `GLOBAL_License` field, which is
permissive enough to bundle. Recorded as the leading candidate for QA-30; the
bundled default is still M4's to choose.

### What phases 2 and 3 handed up, and how it sounded

Phase 2 flagged that the reconstruction residual is about 0 dB — the all-pass
component the minimum-phase split discards is substantial in waveform terms —
and asked whether it is audible. **Nothing in the listening suggested it is.**
`orbit_noise` was called realistic and the tone renders clean. That is not
proof, but the assumption `05` §2 rests on survived its first contact with a
pair of ears.

Phase 3 asked whether three-vertex barycentric weighting holds up for complex
spectra, where the failure mode is comb filtering rather than a step. **No
flanging, metallic tinge or hollowness was reported on any file**, including
the orbits, which sweep continuously across triangle boundaries. Also not
proof, and also the right answer.
