# M4 · Phase 1 — The HRTF set

**Status:** ✅ complete · **Plan:** [plans/phase_1_hrtf_set.md](plans/phase_1_hrtf_set.md)

## Goal

`audio/hrtf/sofa.py` loads a `SimpleFreeFieldHRIR` SOFA file into an
`HrirSet`: every measurement's direction as a unit vector in the project's
axes, both ears' impulse responses at 48 kHz, and the file's licence and
title as it states them. Loudness is normalised, so that switching sets does
not change how loud the mix is. The default set - SADIE II D1, the spike's
and QA-30's leading candidate - is fetched at install, as 02 and 08 already
decided, and loads by its id, `sadie-d1`, the id every project already
names.

## Scope

**In:** the loader, headless; checking the convention and refusing any other
with a reason; mapping SOFA's spherical positions to the project's axes;
resampling a set not at 48 kHz with `soxr`; the level normalisation; the
default set's registry and its fetch, by `launch.py --install`, checked by
SHA-256; `--check` saying whether it is there; its licence in the credits
file; tests against small synthetic SOFA files written by the tests, and
against the real set where it has been fetched.

**Out:** anything done to the responses beyond resampling and scaling →
phase 2. Choosing among candidate sets by ear → phase 10.

## Acceptance

- [x] `load(path)` returns an `HrirSet` with `M` unit directions, `M × 2 ×
      N` float32 responses at 48 kHz, the source rate, and the licence and
      title read from the file, never from a constant.
- [x] A set measured at 44.1 kHz comes back at 48 kHz, with the same
      measurement count and its tap count scaled by the rate.
- [x] A file that is not `SimpleFreeFieldHRIR`, or not SOFA, or not there,
      is refused with a reason, and nothing raises.
- [x] Directions land in the project's axes: SOFA's front (az 0, el 0) is
      +Y, its left (az 90) is −X, its right is +X, up (el 90) is +Z - tested
      on a synthetic set whose responses name their own direction.
- [x] Normalisation is recorded and repeatable: the mean per-ear energy is
      0.25 - the spike's target, a fixed 3 dB of headroom - two sets at
      different levels come out equal, the factor applied is kept on the
      `HrirSet`, and SADIE II D1's loudest direction stays under full scale.
- [x] `launch.py --install` fetches the default set, checks its SHA-256, and
      puts it where the application finds it; a file that does not match is
      deleted and the install says so. `--check` says whether it is there.
- [x] `builtin("sadie-d1")` loads it, and its licence is Apache 2.0 as the
      file states it. Not fetched, it is refused with the command that
      fetches it. It is named in the credits file, and never committed.

## Implements

F-27 (the built-in half), QA-30 (the leading candidate, bundled) - *The
HRTF pipeline, 1. Load* in [05-audio-engine.md](../05-audio-engine.md),
`HrtfRef` in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Amended before the phase started.** As first written, this phase shipped
the set in the repository and normalised to an energy of 1. Planning found
that 02 and 08 had already decided the datasets are *fetched, not
committed*: the SOFA is gitignored and shipped as a build artifact. It also
found that S0 measured 1 as too loud, since at 0.5 per ear SADIE II D1
peaks over full scale. The Goal, Scope and three acceptance lines were
corrected to both.

**Built (2026-09-27).** Three steps, as planned.

- **The fetch**, stdlib only, which `launch.py` loads by path without
  importing the package. It writes beside the final name and moves the file
  there only on a matching digest. The sweep found the one thing its first
  tests could not see: a download killed part-way, by Ctrl+C, skips every
  clean-up. A half-file with the set's own name would then have been found
  by the loader. A test kills one now.
- **The loader.** SADIE II D1 loads in 0.16 s: 8802 directions, 256 taps,
  already at 48 kHz, `Data_Delay` zero throughout. Normalised to 0.25 per
  ear by a factor of 0.784, it peaks at 0.75, under full scale as S0 said
  it would. Its front lands on the project's +Y.
- **The credits** have SADIE II D1's row: fetched, never committed. 08 says
  how the fetch behaves and what `--check` reports.

**Fetched, not committed, and why the alternative lost.** A derived file
was measured first: the responses as float32 and the positions, 14 MB
compressed, and exact, since the set's 24-bit samples survive float32. It
would have loaded in 0.11 s, against the SOFA's 0.16. Nothing there
outweighs 02 and 08's decision, nor 14 MB in the repository's history for
good, nor a file whose provenance would be a script rather than its
publisher.

Twenty-eight mutations over the phase, all caught, two only after a test
was added or tightened. Normalising to 0.5 was caught at first only by the
real set's test, which skips where the set is not fetched. The synthetic
test now pins S0's 0.25 as a literal. The phase adds 24 tests, and the
suite is 2267.
