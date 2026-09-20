# S0 · Phase 5 — Listening

**Status:** not started · **Plan:** not written yet —
`plans/phase_5_listening.md`

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

- [ ] `orbit_noise.wav` — the source is convincingly outside the head and its
      direction is followable through a full revolution.
- [ ] `orbit_tone.wav` — **the zipper test.** No buzz, rasp or roughness at the
      block rate while the tone orbits. This is the pass/fail the whole spike
      exists for.
- [ ] `orbit_tone_nocrossfade.wav` — A/B'd against the above, and the
      difference is audible. If the two sound identical, D-37 is unproven and
      the measurement in
      [phase 4](phase_4_block_engine.md) needs re-reading before anything else
      is concluded.
- [ ] `front_back_clicks.wav` — elevation is perceivable and front/back is not
      systematically reversed. Some front/back confusion on a non-individual
      HRTF is expected and is not a failure.
- [ ] The dataset used is recorded by name, version and licence, as the leading
      candidate for QA-30 — which is still decided at M4.
- [ ] Verdicts and any surprises are appended to the Notes below and summarised
      in [README.md](README.md); decisions go to the log, not here.

## Implements

The "Done when" of S0 in [06-roadmap.md](../06-roadmap.md), the named listening
test attached to D-37, and the evidence behind the "HRTF interpolation
artifacts" row of that document's risk register. Feeds QA-30 and M4.

## Notes

Appended after listening. The verdicts themselves go here.
