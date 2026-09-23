# S0 · Phase 1 — SOFA load

**Status:** ✅ complete · **Plan:**
[plans/phase_1_sofa_load.md](plans/phase_1_sofa_load.md)

## Goal

`spikes/binaural_spike.py` can acquire a full-sphere SOFA set, load it, print
its licence and geometry, resample every HRIR to 48 kHz and level-normalise the
set — leaving a float32 array and a matching array of unit direction vectors in
memory. Nothing is convolved yet; this phase ends at a dataset you can trust
the shape and the level of.

## Scope

**In:** a fetch-and-cache helper (download once into a gitignored directory
under `spikes/`, reuse thereafter); a convention check that the file really is
`SimpleFreeFieldHRIR`; conversion of the measurement positions to unit vectors
in the project's coordinate frame per
[03-data-model.md](../03-data-model.md); `soxr` resampling to 48 kHz; level
normalisation; an `--info` mode that prints the summary.

**Out:** ITD and minimum phase → [phase 2](phase_2_itd_minimum_phase.md).
Triangulation → [phase 3](phase_3_interpolation.md). Choosing the *bundled
default* dataset → QA-30, at M4; this phase only picks something to run on.
Any `.sofa` loading inside the package → M4, `audio/hrtf/sofa.py`.

## Acceptance

- [x] `python spikes/binaural_spike.py --info` prints the dataset name, the
      licence string as stored in the SOFA metadata, `M`, `N`, the original
      sample rate, and the azimuth and elevation ranges.
- [x] The licence line is printed from the file, not from a constant in the
      script — a hardcoded licence is how the wrong one gets shipped.
- [x] Coverage is genuinely full-sphere: at least one measurement above +60°
      elevation and at least one below −30°, asserted rather than eyeballed.
- [x] After resampling, the HRIR array is float32, shape `[M, 2, N48]`, at
      48 kHz, and contains no NaN or Inf.
- [x] After normalisation, the mean broadband RMS over all directions and both
      ears sits within 0.5 dB of the stated target, and the printed value says
      so.
- [x] The second run does no network I/O: the cached file is reused, and the
      script runs to completion with the network unavailable.
- [x] The cached dataset is not committed — `git status` is clean after a run.

## Implements

F-27 and §1 *Load* of [05-audio-engine.md](../05-audio-engine.md). The
coordinate frame and the SOFA azimuth/elevation convention come from
[03-data-model.md](../03-data-model.md). Feeds QA-30.

## Notes

**The dataset is Apache 2.0.** SADIE II D1 carries "Copyright 2018, University
of York, Licensed under the Apache License, Version 2.0" in its own
`GLOBAL_License`. That is permissive enough to bundle, which is the constraint
QA-30 cares about and the one several candidate sets fail. Recorded here as
evidence for that decision, which is still M4's to make.

**`Data_Delay` is zero for this set**, so the unknown the plan flagged is
closed: phase 2 has no stored per-measurement delay to fold into the ITD. It is
still read and printed, because the next dataset may not be zero.

**Coverage is a true full sphere** — 8802 positions, −90° to +90° elevation,
256 taps, already at 48 kHz. With N = 256, phase 4's
`next_pow2(512 + 256 + max_itd - 1)` lands on 1024, which is exactly the `nfft`
the cost estimate in [05-audio-engine.md](../05-audio-engine.md) assumes. One
fewer thing for phase 4 to discover.

**The resampler check in the plan was wrong**, and the way it was wrong is
worth keeping. `soxr` preserves the *continuous-time* waveform, so the discrete
sum of squares is not conserved across a rate change — an impulse resampled
44.1 → 48 kHz gains +0.15 dB of sample-domain energy, and its sample sum scales
by exactly 48000/44100. Nothing is broken: what a filter must preserve is its
frequency response, `|H(f)|` scaled by `1/rate`, and that holds to 0.06 dB
across 100 Hz–15 kHz. The check was rewritten to assert the property we
actually depend on. A phase-2 or phase-4 test that asserts energy conservation
across a rate change will fail for this reason and not because of a bug.

**Level.** Normalising mean per-ear energy to 0.5 (unity power across the pair)
makes this set peak at 1.065 — over full scale. The target is therefore 0.25,
a fixed −3 dB of headroom, and the peak is asserted rather than assumed.
