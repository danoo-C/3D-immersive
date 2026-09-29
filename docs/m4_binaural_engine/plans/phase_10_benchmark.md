# Plan — M4 · Phase 10 — The benchmark, and the switch interval

**Written:** 2026-09-29 · **Status:** in progress

## Approach

**One module, three measurements.** `immersive/benchmark.py`, beside
`app.py` because it wires the window, the player and the engine as `app.py`
does, and run as `python -m immersive.benchmark`:

- **`blocks`**, N-1's timings. No window and no device. SADIE, the set the
  application ships, is prepared at the block given (512 by default). Each
  arrangement is played for 3000 blocks after 100 to warm up, in three
  rounds taken in turn, since timings on this machine drift between runs.
  It reports p50, p99, the worst block, and how many blocks were over
  budget, beside the machine's name, CPU, system, Python and numpy.
- **`contention`**, D-39's measurement. The application's window, 32
  sources playing, and a **stand-in stream**: a thread that calls the
  engine's callback on the device's clock, as PortAudio would. The UI
  thread does one of three things: plays (its own 30 Hz tick), scrolls
  the timeline (7 px every 16 ms, a hand on the scroll bar), or repaints
  the whole window continuously (the roadmap's condition, and the worst
  case). Each is run at 5 ms and at 1 ms, in turn, for several rounds.
- **`live`**, the count phase 11 needs. The same window on the real
  output, `--device` and `--block` as the application takes them, 32
  sources moving for a minute, and the engine's own xrun count at the end.

**What is measured, in each.** A source is a slot: a paired channel is two
(phase 9). Every arrangement has the finished graph. Level as mixed is on,
as a new project has it. The limiter is on, the master gain is at unity,
and one bypassed stereo channel plays beside the sources. It is not a
source, since it never enters the FFT (05, *It is cheaper*). Every source
moves every block, each on an orbit of its own radius and height, and one
in eight orbits inside the centre (D-130). The arrangements are 1, 8, 16
and 32 sources as points, and 32 linked pairs, 64 sources. In the window,
the UI thread sends the positions at 30 Hz, since the ring has one
producer and it is the UI thread.

**The stand-in stream's deadline.** Block `n` is started on the device's
clock and is due one block later: the tightest stream a device can open,
so a miss here is a miss on any device. A block that is late is one miss,
and the clock is set again from when it finished, as a device plays on
after an underrun. Without that, one long stall would be counted again in
every block after it. The time recorded for a block runs from when it was
due to start until it was done. It holds the wait to be woken, every wait
for the GIL, and the block itself, which is what the device sees.

**The suite's short form** runs `blocks` for 32 sources and 500 blocks
through `test_spatial`'s synthetic head. That head costs what SADIE costs:
the same `nfft` of 1024, and the same per-block time within noise (1.56 to
1.63 ms mean against 1.59 to 1.66, measured while planning). It prepares in
a fraction of a second, where SADIE takes 6.4 s cold, and every test's
cache starts cold. The test fails when p99 passes 60% of the budget.

**The switch interval** is set at the top of `app.run`, before the output
is even looked for. It is not set in `build_application`, which every test
calls, so the suite keeps CPython's default.

### What the prototypes found

The measurement was prototyped before this plan, as a plan should surface
what is unclear, and it has already answered D-39's question. **The answer
is not the one D-39 expected.**

- **The engine waits for the GIL once per numpy call, not once per block.**
  numpy releases the GIL inside every ufunc loop over 500 elements. A
  block's rows are 512 samples and its spectra 513 bins, so nearly every
  call in `process` releases it. When the UI thread is running Python, each
  release can cost the audio thread a whole switch interval to get it
  back. With the main thread in a pure Python loop, one block of 32
  sources took 444 ms at 5 ms, 92 ms at 1 ms, and 31 ms at 0.2 ms: about
  90 waits a block. One source took 58, 15 and 4.6 ms.
- **In the window, 1 ms made no difference.** With 32 points and the
  window repainting continuously, nearly every block was missed at both
  intervals, 312 of 314 at 5 ms and 343 of 346 at 1 ms, at about 50 ms a
  block. Scrolling missed 0 to 9 blocks in 750, and playing hands off 0 or
  1, with no difference between the intervals at either.
- **An engine that waits once a block is what D-39 assumed, and there it
  works.** With `process` replaced by a 1.5 ms sleep, which releases the
  GIL once, scrolling missed nothing at either interval. Continuous
  repainting missed 34 blocks in 1120 at 5 ms and 10 at 1 ms.
- **The window is part of it.** A full repaint of the window with 32
  channels takes about 55 ms. About 29 ms of that is Qt drawing
  stylesheeted widgets, and about 24 ms is Python: 123 meter paints, 244
  header paints and 128 `NumericField.event` calls each time.
- **The GIL cannot be switched off yet.** PySide6 6.11.2 ships only
  `abi3` wheels, which a free-threaded interpreter cannot load. numpy,
  cffi, soxr, h5py and netCDF4 all ship `cp314t`.

So the phase's third acceptance line takes its second branch: D-39 is
reopened with the numbers (D-137). The numbers in the Notes are the full
runs, not these.

## Decisions settled here

**D-136**: how N-1 is measured, what counts, and why the benchmark ships in
the package.
**D-137**: D-39 reopened. The switch interval stays at 1 ms, set in
`app.run`, because it bounds the few waits an engine that waits once a
block would have. It is not what keeps the numpy engine on time with a
busy UI, and N-2 is at risk until the audio thread stops queueing for the
GIL at every numpy call. What to do about that is a scope question for the
user, listed with a recommendation in the Outcome.

## Steps

1. **The block times, and the short form.** `benchmark.py` with `blocks`,
   the arrangement, the timings and the machine's name. Tests:
   - 32 sources as points, through the synthetic head, 500 blocks: p99
     under 60% of the budget;
   - the arrangement is what it says: 32 pairs are 64 slots, the bypassed
     channel is not a slot, level as mixed and the limiter are on, and
     every source moves between two blocks;
   - the timings' percentiles and the over-budget count, from known times;
   - the budget is a block at 48 kHz, and the check is at the fraction
     asked, just under and just over.
   Then the full run, recorded.
2. **The switch interval.** `app.run` sets it first. Tests:
   - it is 1 ms, set before the player exists, so before any stream can
     open;
   - `build_application` does not set it.
3. **The stand-in stream and the loaded window.** The clock, the stream and
   `contention`. `Engine.generation`, so the UI thread can name the
   snapshot a position is worked out against without holding a feed. Tests:
   - the clock: a block that finishes late is a miss; one that starts late
     and finishes after its time is a miss; one long block is one miss,
     not a cascade;
   - the stream calls the engine's callback at a block's size, and stops;
   - in the window, 32 sources play and move, each load runs at the
     interval named, and the interval is put back.
   Then the full run, recorded, and D-137's numbers.
4. **The live count.** `live`: the real backend through `settle`, the
   window shown, a minute, and the engine's xruns. Tests, with the stand-in
   backend: the report is the engine's own count, and an unusable output is
   reported, not raised. The procedure goes into phase 11's Notes.
5. **The sweep, and the close.** The named mutations; the docs (01, 02, 05,
   06, 08, phase 11); acceptance, Notes, Outcome.

## Files

`src/immersive/benchmark.py` — new
`src/immersive/app.py` — the switch interval
`src/immersive/audio/engine.py` — `generation`
`tests/test_benchmark.py` — new
`tests/test_app.py` — new
`docs/01-requirements.md` — D-136, D-137; D-39's row notes the reopening
`docs/02-architecture.md` — `benchmark.py` in the layout
`docs/05-audio-engine.md`, `docs/08-environment.md` — the switch interval's
row corrected, and how the benchmark is run
`docs/06-roadmap.md` — the risk register's row for realtime dropouts
`docs/m4_binaural_engine/phase_11_heard.md` — the live count's procedure

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | p99 taken as the mean | the percentiles from known times |
| 2 | the over-budget count taking `>=` for `>`, or counting the warm-up | the percentiles from known times |
| 3 | a pair counted as one slot | 32 pairs are 64 slots |
| 4 | level as mixed off in the arrangement | the arrangement: level as mixed on |
| 5 | positions sent once, not every block | every source moves between two blocks |
| 6 | the bypassed channel spatialised, or missing | the bypassed channel is not a slot |
| 7 | the budget from 44.1 kHz | the budget is a block at 48 kHz |
| 8 | the check at the whole budget, not the fraction | just under and just over the fraction |
| 9 | the switch interval set after the player is made | set before the player exists |
| 10 | the switch interval not set | it is 1 ms |
| 11 | a miss judged from when the block started, not when it was due | a block that starts late is a miss |
| 12 | no re-anchoring after a miss | one long block is one miss |
| 13 | a load run at the other state's interval | each load runs at the interval named |
| 14 | the interval not put back after `contention` | the interval is put back |
| 15 | `live` reporting the stand-in's misses, not the engine's xruns | the report is the engine's own count |
| 16 | `Engine.generation` the playing snapshot's, not the next one's | positions sent after an install are heard |

## Risks and unknowns

- **A timing test in a parallel suite.** Eight workers share six cores.
  The short form's 60% line is 6.4 ms, and 32 sources take about 3 ms at
  p99 alone. If eight workers push it over, the line is right and the test
  is wrong: run it in an interpreter of its own, as the zero-allocation
  test is.
  *Amended in step 1:* they did push it over, to 12 to 15 ms, and an
  interpreter of its own would not have helped, since the load is the other
  workers. Even the thread's own CPU time reached 11 ms at p99, because a
  busy sibling hyperthread slows it too. Single-threaded BLAS in every
  worker brought it to 8.6 to 10.7 ms, still over. So the test is marked
  `timing`: skipped, with its reason, under more than one worker, and run
  alone by `pytest -m timing`, as CI now does after the parallel run. A
  serial suite runs it too. pytest-benchmark switches itself off under
  xdist for the same reason.
- **The contention runs are slow and noisy.** They are measured by hand,
  not in the suite, and in interleaved rounds. The suite tests the stand-in
  and the loads' plumbing with short runs, not the effect.
- **The finding is bigger than the phase.** The phase's own acceptance
  expects this branch, so it is recorded, not fixed here (*Out*: optimising
  past N-1). N-1's timings pass. What fails is N-2, and it gets worse from
  M5, when the views repaint during playback.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Moving the audio thread off the GIL: an engine process, a native `process`, or fewer releases and a lighter window | the user's call, in the Outcome; a phase or milestone of its own |
| `gc.freeze()` after load (05, *Realtime safety checklist*) | not measured as a cause here; with the above |
| The live count on the listening machine | phase 11 |
| Making the window's repaint cheaper | M5, where the views add to it; noted there |

## Outcome

Filled in at the end.
