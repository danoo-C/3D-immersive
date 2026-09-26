# M4 · Phase 1 — The HRTF set

**Status:** not started · **Plan:** not written yet

## Goal

`audio/hrtf/sofa.py` loads a `SimpleFreeFieldHRIR` SOFA file into an
`HrirSet`: every measurement's direction as a unit vector in the project's
axes, both ears' impulse responses at 48 kHz, and the file's licence and
title as it states them. Loudness is normalised, so that switching sets does
not change how loud the mix is. The default set - SADIE II D1, the spike's
and QA-30's leading candidate - ships with the application and loads by its
id, `sadie-d1`, the id every project already names.

## Scope

**In:** the loader, headless; checking the convention and refusing any other
with a reason; mapping SOFA's spherical positions to the project's axes;
resampling a set not at 48 kHz with `soxr`; the level normalisation; how the
default set is bundled and found; the licence carried into the
application's credits file; tests against the real file and against small
synthetic SOFA files written by the tests.

**Out:** anything done to the responses beyond resampling and scaling →
phase 2. Choosing among candidate sets by ear → phase 9.

## Acceptance

- [ ] `load(path)` returns an `HrirSet` with `M` unit directions, `M × 2 ×
      N` float32 responses at 48 kHz, the source rate, and the licence and
      title read from the file, never from a constant.
- [ ] A set measured at 44.1 kHz comes back at 48 kHz, with the same
      measurement count and its tap count scaled by the rate.
- [ ] A file that is not `SimpleFreeFieldHRIR`, or not SOFA, or not there,
      is refused with a reason, and nothing raises.
- [ ] Directions land in the project's axes: SOFA's front (az 0, el 0) is
      +Y, its left (az 90) is −X, its right is +X, up (el 90) is +Z - tested
      on a synthetic set whose responses name their own direction.
- [ ] Normalisation is recorded and repeatable: the set's diffuse-field
      average energy is 1, two sets at different levels come out equal, and
      the factor applied is kept on the `HrirSet`.
- [ ] `builtin("sadie-d1")` loads the bundled default. Its licence is Apache
      2.0 as the file states it, and it is named in the credits.
- [ ] The bundle's size, on disk and in the repository, is recorded in the
      Notes, with the decision about how it ships.

## Implements

F-27 (the built-in half), QA-30 (the leading candidate, bundled) - *The
HRTF pipeline, 1. Load* in [05-audio-engine.md](../05-audio-engine.md),
`HrtfRef` in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
