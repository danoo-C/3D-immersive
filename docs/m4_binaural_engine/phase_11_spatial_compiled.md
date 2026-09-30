# M4 · Phase 11 — The spatial path, compiled

**Status:** ✅ · **Plan:** [plans/phase_11_spatial_compiled.md](plans/phase_11_spatial_compiled.md)

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

- [x] The kernel is the Python render to float32 rounding, block after
      block, for points, linked and free pairs, sources inside the centre,
      level as mixed on and off, the crossfade off, and across a seek and a
      snapshot swap. *`test_spatial_compiled.py`, within 2e-6, output and
      meters.*
- [x] It is compiled on the worker that prepares the bank, never on the
      audio thread. One compiled signature serves every arrangement a
      snapshot can build, so no block after the bank arrives compiles
      anything. *`spatial.warm` on the HRTF worker; one signature, tested.*
- [x] `process()` still makes no array and keeps nothing (D-106), with the
      kernel running. *Only once kernels ran without numba's runtime
      (Notes).*
- [x] Measured with `contention`: playing and scrolling miss no block at
      1 ms. Repainting is recorded, better than phase 10 but not yet clean.
      N-1's block times are recorded beside phase 10's. *Playing missed none
      at 1 ms in either clean run. Scrolling missed none in one and 10 in the
      other: a single lap with a stall, not waits for the GIL. The run
      taken just after WSL started is recorded too (Notes).*
- [x] numba and rocket-fft are runtime dependencies: in `pyproject.toml`
      and `uv.lock`, attributed in THIRD-PARTY-NOTICES.md, and in 02's
      table of dependencies.

## Implements

D-137's way out, chosen by the user as numba kernels (phase 10's Outcome,
option A); D-138, D-139; *Realtime safety checklist* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**N-1's block times with the kernel**, on DESKTOP-HAF0IOD as phase 10
measured them: SADIE II D1 at 512 frames, 3000 blocks each in three
rounds, two runs, in ms, with phase 10's p99 beside them:

| Sources | As | p50 | p99 | Phase 10's p99 |
|---|---|---|---|---|
| 1 | 1 point | 0.10, 0.10 | 0.18, 0.22 | 0.34, 0.24 |
| 8 | 8 points | 0.24, 0.24 | 0.41, 0.43 | 0.99, 0.58 |
| 16 | 16 points | 0.41, 0.41 | 0.76, 0.79 | 1.99, 1.49 |
| **32** | **32 points** | **0.78, 0.76** | **1.27, 1.20** | 3.04, 2.99 |
| 64 | 32 linked pairs | 1.30, 1.30 | 2.91, 3.80 | 5.82, 5.46 |

32 sources take 11 to 12% of the budget, where they took 28 to 29%. The
rest of the block is still Python, so this is not yet the whole saving.

**With the window loaded** (`contention`, three rounds of 8 s, in turn),
blocks missed of about 2250, or of the number given:

| Load | 5 ms | 1 ms |
|---|---|---|
| playing | 3 | 0 |
| scrolling | 1 | 10 |
| repainting | 1161 of 1208 | 1263 of 1408 |

That is the second of two runs. The first, taken 14 minutes after WSL had
started, missed 80 and 205 playing and 32 and 45 scrolling, with its third
round clean. A third run of playing and scrolling alone, with Python's
collections watched, missed nothing in all twelve laps. The 10 missed
while scrolling were one lap, and a 5 ms lap held one block for 64 ms:
single stalls, not waits for the GIL. One full collection in that third
run took 50 ms, and a collection holds the GIL, so one landing during
playback costs blocks. Nothing yet calls `gc.freeze()` after a project
loads, as 05's checklist asks. That belongs with phase 12, since even a
fully compiled block needs the GIL to enter its callback. Repainting
blocks take 16 to 19 ms at the median where phase 10's took 58 to 67, as
the spike found. The rest of the block is phase 12's.

**numba's runtime cost 48 bytes an array.** With it on, every array
handed to a kernel got a 48-byte reference record, freed when the call
ended: 2.8 KiB a block for the spatial path, over D-106's line, which the
zero-allocation test caught. Calling the compiled entry point directly
did not help, because the records are made while the arguments are read,
not while their types are checked. The kernels run without the runtime
(`audio/compiled.py`), which a kernel that makes no array does not need.
Without it, a slice assignment of one array into another has no compiled
form, so the kernel copies with a loop. A kernel that tried to make an
array would not compile, which holds D-106 at compile time.

**numba's cache keeps stale code.** It checks a cached kernel against its
own module's file only. A scratch caller, cached before its callee in
another file was edited, went on returning the old result: 20 where 30
was right. The spatial kernel calls the lookup's walk in another file, so
on import `compiled.py` hashes the audio package's sources, and when they
have changed it clears the package's cached kernels before any is loaded.

**What compiling costs.** From a cold cache, `warm` takes 2.2 s for SADIE
at 512 frames, and preparing the bank about 1 s more, since the walk
compiles for its first Python call. From a warm cache, `warm` takes
0.02 s. The parallel suite took 34.9 s straight after the cache was
cleared and 36.1 and 36.3 s warm. Earlier the same day it took 28.7 and
31.4 s, so the compile is lost in this machine's drift.

**Bounds checked once.** The whole suite passes with `NUMBA_BOUNDSCHECK=1`
and a cache of its own. A read past an array's end raises there, and
without the check it silently returns whatever memory holds.

**From a cold cache, the suite compiled eight times at once.** After the
sweep cleared the cache, each xdist worker's HRTF worker compiled the
kernel at the same moment on a loaded machine, and a test waiting ten
seconds for a bank gave up. CI starts cold on every run, so it would fail
that way every time. So `pytest_configure` compiles the kernels in the
controller, or in a serial run, before any worker starts, and the workers
load them from the cache. The suite then passed at 41.9 s cold and 38.2 s
warm, on a day it ran anywhere from 29 to 38 s. The spatial path's
zero-allocation run takes 6.5 and 7.2 s, where phase 10's took 7.6 and 7.9,
run in turn.
