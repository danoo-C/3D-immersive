# M4 · Phase 12 — The whole block, compiled

**Status:** ✅ · **Plan:** [plans/phase_12_block_compiled.md](plans/phase_12_block_compiled.md)

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

- [x] The engine's output is the Python engine's to float32 rounding
      through every path the zero-allocation test takes: fades of both
      shapes, clip gain, mono and stereo, a missing sample, loops that wrap
      inside a block, the repeat, an audition replaced and stopped, bypass
      and pan, the master and the limiter, pairs and the centre.
      *`test_block_compiled.py` and `test_spatial_compiled.py`, output and
      meters, block by block.*
- [x] With the window repainting continuously, 32 moving sources at 1 ms
      miss no more than one block in a thousand, where phase 10's engine
      missed 413 of 417. The counts at 5 ms and 1 ms are both recorded.
      *1 in 2255 and 0 in 2256 at 1 ms; 11 and 5 at 5 ms (Notes).*
- [x] `process()` still makes no array and keeps nothing, and nothing
      compiles on the audio thread. *Nothing kept, 936 bytes at worst; the
      kernel is warmed on the HRTF worker and before any stream opens, with
      one signature.*
- [x] N-1's block times are recorded, and 32 sources stay under half the
      budget. *0.81 and 0.84 ms at p99, 8%.*

## Implements

D-137's way out (phase 10's Outcome, option A), D-138, D-139.

## Notes

Appended while building.

**With the window loaded** (`contention`, three rounds of 8 s, in turn,
two runs), blocks missed of about 2250:

| Load | 5 ms | 1 ms |
|---|---|---|
| playing | 0, 0 | 0, 0 |
| scrolling | 0, 1 | 0, 0 |
| repainting | **11, 5** | **1, 0** |

A repainting block now takes 2.5 to 2.9 ms at the median and 6.3 to 9.8
at p99, where phase 10's took 58 to 67 ms. The one callback waits for the
GIL once, and at 1 ms that wait is short: D-39 does what it said, now that
the engine is the one it assumed.

**N-1's block times**, SADIE II D1 at 512 frames, two runs, in ms:

| Sources | As | p50 | p99 | Phase 11 | Phase 10 |
|---|---|---|---|---|---|
| 1 | 1 point | 0.05, 0.05 | 0.08, 0.12 | 0.18, 0.22 | 0.34, 0.24 |
| 8 | 8 points | 0.13, 0.13 | 0.21, 0.25 | 0.41, 0.43 | 0.99, 0.58 |
| 16 | 16 points | 0.24, 0.23 | 0.44, 0.38 | 0.76, 0.79 | 1.99, 1.49 |
| **32** | **32 points** | **0.46, 0.46** | **0.81, 0.84** | 1.27, 1.20 | 3.04, 2.99 |
| 64 | 32 linked pairs | 1.09, 1.04 | 2.34, 2.14 | 2.91, 3.80 | 5.82, 5.46 |

32 sources take 8% of the budget.

**The zero-allocation runs** keep nothing, and the worst block raises
traced memory's peak by 936 bytes on the flat path and 872 on the spatial
one, against the 2 KiB line. On the way there, one run kept 48 bytes a
block while a voice sounded. Reading `ndarray.ctypes` for the voice's
address every block made objects, so a voice now works out its address
when it is made, on the UI thread.

**A sample is read by address** (D-140). Without numba's runtime a kernel
takes neither a list of arrays nor a view it makes itself, as `carray`
turned out to need: "only accept returning of array passed into the
function as argument". So `compiled.read` is a two-line intrinsic that
loads a float32 from an address. The snapshot's table is built from the
arrays, each read stops at the sample's own frames, and a clip claiming
more than its file has plays silence past it, where the Python raised.

**Collections** (D-142). With the block compiled, two minutes of playing
and scrolling made no collection at all, frozen or not. One full
collection of the 32-channel window's heap, 212,000 objects, takes 67 ms,
and after a freeze next to nothing. So a launch freezes after it shows the
window and after each New and Open, unfreezing first.

**What compiling costs.** The block kernel takes 9.0 s from a cold cache
and 0.55 s from a warm one. It needs no bank, so the HRTF worker compiles
it before preparing the set, and the player waits for it only if a Play
comes first. The suite took 45.4 s straight after a change, with the
compile in the test controller, and 35.6 s warm.

**From phase 11: collections.** With the spatial path compiled, the
sporadic misses left while playing or scrolling were single stalls of 30
to 64 ms, and one full collection was seen to take 50 ms. A collection
holds the GIL, and a fully compiled block still needs the GIL to enter
its callback. So this phase's plan should settle `gc.freeze()` after a
project loads, which 05's checklist asks for and nothing does yet. It
should also measure what collections cost with the window playing.
