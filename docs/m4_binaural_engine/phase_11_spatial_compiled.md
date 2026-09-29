# M4 · Phase 11 — The spatial path, compiled

**Status:** in progress · **Plan:** [plans/phase_11_spatial_compiled.md](plans/phase_11_spatial_compiled.md)

## Goal

The spatial path's block runs as one compiled kernel that releases the GIL
for all of its work, instead of waiting for it again at every numpy call
(D-137). Everything a placed source goes through is in it: the lookup, the
filters, the centre, a pair's gain, the crossfade, both FFTs and the
overlap-add. It is compiled by numba off the audio thread, and it sounds
exactly as the Python it replaces did, to float32 rounding. This is the
first half of taking the engine's block off the GIL, the half that holds
most of the waits. Phase 12 does the rest.

## Scope

**In:** numba and rocket-fft as dependencies (D-138); `Space.render` as a
kernel, the Python render it replaces kept as the tests' reference;
compiling it where the bank is prepared (D-139); the zero-allocation test
over it; the benchmark's numbers with it.

**Out:** the rest of the block, meaning the lanes, fades and gains, the
audition, the master and the limiter, and a stopped transport's drain →
phase 12. A cheaper repaint of the window → M5.

## Acceptance

- [ ] The kernel is the Python render to float32 rounding, block after
      block, for points, linked and free pairs, sources inside the centre,
      level as mixed on and off, the crossfade off, and across a seek and a
      snapshot swap.
- [ ] It is compiled on the worker that prepares the bank, never on the
      audio thread. One compiled signature serves every arrangement a
      snapshot can build, so no block after the bank arrives compiles
      anything.
- [ ] `process()` still makes no array and keeps nothing (D-106), with the
      kernel running.
- [ ] Measured with `contention`: playing and scrolling miss no block at
      1 ms. Repainting is recorded, better than phase 10 but not yet clean.
      N-1's block times are recorded beside phase 10's.
- [ ] numba and rocket-fft are runtime dependencies: in `pyproject.toml`
      and `uv.lock`, attributed in THIRD-PARTY-NOTICES.md, and in 02's
      table of dependencies.

## Implements

D-137's way out, chosen by the user as numba kernels (phase 10's Outcome,
option A); D-138, D-139; *Realtime safety checklist* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
