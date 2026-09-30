# M4 · Phase 12 — The whole block, compiled

**Status:** not started · **Plan:** not written yet

## Goal

`process()` waits for the GIL once a block. It does its bookkeeping in
Python: taking up a snapshot or a voice, draining the ring, and cutting the
block into pieces where a loop wraps. It then hands everything else to one
compiled kernel. That kernel reads the lanes with their fades and gains,
runs the audition, the spatial path from phase 11, the master and the
limiter, and fills the meters and the output. This is the engine phase 10
emulated with a sleep, which missed no block at 1 ms while the window
repainted without pause.

## Scope

**In:** the lanes' reads, fades, clip gains and gain ramps, mono and
stereo, bypass and pan; the audition and its fall; the master gain and the
limiter; the meters; a stopped transport's drain; all of it in kernels
called once a block, and equal to the Python it replaces.

**Out:** a cheaper repaint of the window → M5. Automation evaluated per
block → M6, which writes its curves into the same kernel.

## Acceptance

- [ ] The engine's output is the Python engine's to float32 rounding
      through every path the zero-allocation test takes: fades of both
      shapes, clip gain, mono and stereo, a missing sample, loops that wrap
      inside a block, the repeat, an audition replaced and stopped, bypass
      and pan, the master and the limiter, pairs and the centre.
- [ ] With the window repainting continuously, 32 moving sources at 1 ms
      miss no more than one block in a thousand, where phase 10's engine
      missed 413 of 417. The counts at 5 ms and 1 ms are both recorded.
- [ ] `process()` still makes no array and keeps nothing, and nothing
      compiles on the audio thread.
- [ ] N-1's block times are recorded, and 32 sources stay under half the
      budget.

## Implements

D-137's way out (phase 10's Outcome, option A), D-138, D-139.

## Notes

Appended while building.

**From phase 11: collections.** With the spatial path compiled, the
sporadic misses left while playing or scrolling were single stalls of 30
to 64 ms, and one full collection was seen to take 50 ms. A collection
holds the GIL, and a fully compiled block still needs the GIL to enter
its callback. So this phase's plan should settle `gc.freeze()` after a
project loads, which 05's checklist asks for and nothing does yet. It
should also measure what collections cost with the window playing.
