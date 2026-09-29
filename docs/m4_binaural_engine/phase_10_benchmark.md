# M4 · Phase 10 — The benchmark, and the switch interval

**Status:** ✅ · **Plan:** [plans/phase_10_benchmark.md](plans/phase_10_benchmark.md)

## Goal

N-1 is measured, not argued: **32 moving sources at a 512-frame block**,
the finished graph with distance, crossfade, bypass and the limiter all
running. It is done here as timings with a margin, and on the listening
machine as a live xrun count. `sys.setswitchinterval(0.001)` is set in
`app.py` before the stream opens (D-39), and measured the way the roadmap
insists: while the UI is actively repainting, since an idle UI shows no
difference and proves nothing.

## Scope

**In:** a benchmark script and a test that runs a short form of it; `p50`,
`p99` and worst per-block times for 1, 8, 16 and 32 sources, a source
being a slot, so a paired channel counts two (phase 9), and for 32 paired
channels, 64 sources, recorded beside them; a stand-in
audio thread calling `process` on a real-time schedule while the window
repaints offscreen, counting missed deadlines with and without the switch
interval; the switch interval itself; what the live count must be, written
into phase 13 for the listening machine.

**Out:** optimising past N-1 → only if it fails (05, *If Python is not
enough*).

## Acceptance

- [x] 32 moving spatial sources at 512 frames take a p99 per-block time
      under half the 10.7 ms budget on this machine, recorded with the
      machine's name. *3.04 and 2.99 ms in two runs, 28 to 29% of the
      budget, on DESKTOP-HAF0IOD (Notes).*
- [x] The short form runs in the suite and fails if p99 passes 60% of the
      budget - loose enough for a loaded machine, tight enough to catch a
      regression of kind rather than degree. *`test_benchmark.py`, marked
      `timing`: a serial suite runs it, and a parallel one leaves it to
      `pytest -m timing`, as CI does (Notes).*
- [x] With the UI repainting continuously, the stand-in audio thread misses
      fewer deadlines with the switch interval than without it, both
      counts recorded. If it does not, D-39 is reopened with the numbers.
      *It does not: 360 of 365 blocks missed at 5 ms, 413 of 417 at 1 ms.
      D-39 is reopened by D-137, which keeps the interval and says why it
      is not enough.*
- [x] `app.py` sets the switch interval before any stream opens, tested.
      *`test_app.py`.*

## Implements

N-1, D-39 - *Cost estimate*, *Realtime safety checklist* and *If Python is
not enough* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**N-1's block times** on DESKTOP-HAF0IOD: 11th Gen Intel Core i5-11400H at
2.70 GHz, Linux 6.18.33.2-microsoft-standard-WSL2, Python 3.13.12, numpy
2.4.6. SADIE II D1 at 512 frames, whose block lasts 10.67 ms, with 3000
blocks each in three rounds. Two runs, in ms:

| Sources | As | p50 | p99 | Worst | Over budget |
|---|---|---|---|---|---|
| 1 | 1 point | 0.17, 0.17 | 0.34, 0.24 | 0.94, 0.51 | 0, 0 |
| 8 | 8 points | 0.47, 0.46 | 0.99, 0.58 | 6.23, 1.08 | 0, 0 |
| 16 | 16 points | 0.83, 0.81 | 1.99, 1.49 | 6.32, 2.54 | 0, 0 |
| **32** | **32 points** | **1.52, 1.50** | **3.04, 2.99** | 6.18, 10.39 | 0, 0 |
| 64 | 32 linked pairs | 3.14, 3.05 | 5.82, 5.46 | 13.00, 6.91 | 2, 0 |

N-1 is met with room, at 28 to 29% of the budget where the line is 50%. 32
pairs, 64 sources, sit just over that line, which N-1 does not draw for 64.
A single block now and then over 6 ms, once 10 and once 13, comes from WSL,
not the graph: it lands on a point run and a pair run alike.

**The short form could not share the machine.** Under `pytest -n 8` the
suite's own workers put its p99 at 12 to 15 ms, with the median at 6 to 8
where it is 1.5 alone. The thread's own CPU time was no steadier, at up to
11 ms, since a busy sibling hyperthread slows it too. Single-threaded BLAS
in every worker brought it to 8.6 to 10.7 ms, still over. So it is marked
`timing` and skipped, with its reason, under more than one worker. A serial
suite runs it, and CI now runs `pytest -m timing` after the parallel run.
pytest-benchmark switches itself off under xdist for the same reason.

**The switch interval, with the window loaded** (`contention`, three rounds
of 8 s per load and interval, taken in turn, after one lap not counted).
Blocks missed of about 2250, or of the number given:

| Load | The engine, 5 ms | The engine, 1 ms | Waiting once a block, 5 ms | Waiting once a block, 1 ms |
|---|---|---|---|---|
| playing | 3 | 7 | 0 | 0 |
| scrolling | 1 | 3 | 0 | 1 |
| repainting | **360 of 365** | **413 of 417** | 23 | **0** |

While the window repainted, a block of the engine took 67 ms at the median
at 5 ms, and 58 ms at 1 ms. "Waiting once a block" is `--one-wait`: a sleep
as long as the engine's median block in its place, which releases the GIL
once. That is what D-39 assumed the engine did.

**Why the interval does not help: the engine waits at every numpy call.**
numpy releases the GIL inside every ufunc loop over 500 elements, and a
block's rows are 512 samples and its spectra 513 bins. When the audio
thread lets the GIL go, a UI thread running Python takes it, and the audio
thread waits up to the interval to get it back. With the main thread in a
pure Python loop, one block of 32 sources took 444 ms at 5 ms, 92 ms at
1 ms and 31 ms at 0.2 ms: about 90 waits a block. One source took 58, 15
and 4.6 ms. The interval sets how long each wait is. It cannot set how many
there are.

**The window is part of it.** A full repaint of the window with 32 channels
takes about 55 ms. About 29 ms of that is Qt drawing the stylesheeted
widgets, and about 24 ms is Python: each repaint makes 123 meter paints,
244 header paints and 128 calls to `NumericField.event`. The views at M5
will repaint during playback, so this grows.

**Hands off, the misses are sporadic.** Three and seven in 2250 blocks, at
no particular interval. They are not the page turning: four laps of 20 s,
turning the page twice each, missed none. The first seconds of playing a
project the window has just built are heavier than any after: the first,
uncounted lap missed 52 blocks in 261 at 5 ms, which is why it is not
counted.

**The GIL cannot be switched off yet.** PySide6 6.11.2 ships only `abi3`
wheels, which a free-threaded interpreter cannot load. numpy, cffi, soxr,
h5py and netCDF4 all ship `cp314t` (08, *The thing genuinely worth
watching*).

**No live count here.** Inside the sandbox this machine has no output
device, and `live` says so. The count is phase 13's, on native Windows,
and its Notes say how to take it.
