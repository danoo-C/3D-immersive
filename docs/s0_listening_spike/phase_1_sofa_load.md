# S0 · Phase 1 — SOFA load

**Status:** not started · **Plan:** not written yet —
`plans/phase_1_sofa_load.md`

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

- [ ] `python spikes/binaural_spike.py --info` prints the dataset name, the
      licence string as stored in the SOFA metadata, `M`, `N`, the original
      sample rate, and the azimuth and elevation ranges.
- [ ] The licence line is printed from the file, not from a constant in the
      script — a hardcoded licence is how the wrong one gets shipped.
- [ ] Coverage is genuinely full-sphere: at least one measurement above +60°
      elevation and at least one below −30°, asserted rather than eyeballed.
- [ ] After resampling, the HRIR array is float32, shape `[M, 2, N48]`, at
      48 kHz, and contains no NaN or Inf.
- [ ] After normalisation, the mean broadband RMS over all directions and both
      ears sits within 0.5 dB of the stated target, and the printed value says
      so.
- [ ] The second run does no network I/O: the cached file is reused, and the
      script runs to completion with the network unavailable.
- [ ] The cached dataset is not committed — `git status` is clean after a run.

## Implements

F-27 and §1 *Load* of [05-audio-engine.md](../05-audio-engine.md). The
coordinate frame and the SOFA azimuth/elevation convention come from
[03-data-model.md](../03-data-model.md). Feeds QA-30.

## Notes

Appended while building.
