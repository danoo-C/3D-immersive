# Handoff: 2026-09-27, M4 phase 5 (the spatial engine)

Written at the end of a session so work can pick up on 2026-09-28. **Delete
this file, and `handoff_sweep_phase5.py`, once phase 5 is committed.**
Neither is tracked.

## Where things stand

- **Branch:** `m3-timeline`. The last commit is `75f8327 m4 phase 5: planned
  - the engine, spatial (D-121, D-122)`. M4 phases 1–4 are committed and
  complete.
- **Phase 5 code is written and tested but not committed.** It is feature
  complete. The mutation sweep passed: 19 of 19 mutations were caught.
- **Last full-suite result:** 2344 passed, 26 s. That was before the two
  new lookup tests below, which pass on their own (16 passed in
  `tests/test_lookup.py`). ruff and mypy are clean.
- **Still to do for phase 5:** fix one flaky test, check one coverage gap,
  write the docs, and commit. Steps 1–5 below.

## To do tomorrow, in order

### 1. Fix the flaky allocation test (found tonight; the cause is known)

`tests/test_lookup.py::test_weighing_a_block_of_32_makes_no_array` fails
about 1 run in 18 under `-n 8`. The failure is `assert (426 - 0) <= 0` on
the "kept nothing" check.

**Cause, measured with a tracemalloc probe:** the bytes are not the
lookup's. The test runs tracemalloc in-process, and tracemalloc traces
everything in the process. The surviving allocations came from:
- `shibokensupport/feature.py:95`, 376 B: PySide6's lazy signature and
  feature loader, triggered by an earlier Qt test in the same xdist worker;
- `execnet/gateway_base.py:534`, 354 B: xdist's message read, arriving
  mid-measure.

None of them came from `lookup.py`. The code under test is fine.

**Fix, pick one:**
- Move the measure into a subprocess, as `tests/test_realtime.py` does.
  This is the most robust option and costs about 1 s of startup.
- Or keep it in-process and filter the snapshot diff to the lookup's own
  file: `snapshot.filter_traces([tracemalloc.Filter(True, lookup.__file__)])`
  compared with a baseline snapshot. This leaves the global `peak` check
  exposed to the same noise, though that check has not flaked.

The recommendation is the subprocess, for the same reason the realtime test
already uses one. Other in-process tracemalloc tests could have the same
exposure. `grep -rn "tracemalloc.start" tests/` found only
`test_realtime.py` (already a subprocess) and this one.

### 2. Check one coverage gap: the snapshot swap

Phase 5's acceptance says: *"No sample is discontinuous across a seek **or
a snapshot swap**: the first block after either does not crossfade from a
stale filter."*

- **Seek:** tested (`test_the_first_block_after_a_seek_crossfades_from_nothing_stale`)
  and mutation-checked. The engine sets `space.fresh = True` on SEEK
  (`engine.py` ~line 486).
- **Swap:** relies on `Space.fresh` defaulting to `True` (`spatial.py`
  line 105), because a new snapshot has a new `Space`. **No test or
  mutation covers it yet.** To do:
  - Add a test that the first block after `engine.install(new snapshot)`
    uses `H` on both halves.
  - Add a mutation `fresh: bool = False` to the sweep, and confirm it is
    caught.
  - Check the same way that the tail carried at take-up (`_take_up` copies
    the old `Space.tail` when shapes match) is tested. A mutation that drops
    the copy should be caught.

### 3. Run the checks

```
cd /home/dano/IT/3d_imersive
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests
.venv/bin/mypy src tests
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q          # full suite, ~26 s
.venv/bin/python handoff_sweep_phase5.py                         # every mutation should say "caught"
.venv/bin/python handoff_sweep_phase5.py "resolution from the constant"   # or one by name
```

The sweep script edits source files in place and restores each one in a
`finally`. Run it on a clean tree, and look at `git diff` afterwards.

### 4. Close phase 5's docs (09-workflow)

**`docs/m4_binaural_engine/phase_5_spatial_engine.md`:**
- Change the status to ✅ complete.
- Tick all 7 acceptance boxes. The swap box gets ticked after step 2.
- Fill in Notes (numbers under *Findings*):
  - the 32-source timing;
  - the crossfade A/B;
  - the D-122 FFT finding;
  - the lookup resolution bug;
  - the flake.

**`docs/m4_binaural_engine/plans/phase_5_spatial_engine.md`:**
- Change the status to ✅ complete.
- Write the Outcome:
  - built as planned;
  - all 15 named mutations caught, plus 4 more (two feed, two lookup
    resolution);
  - what phase 6 needs (below).

**`docs/m4_binaural_engine/README.md`:**
- Phase 5 row → ✅.
- Add a **Phase 5.** paragraph to Notes, in the style of phases 1–4.

**`docs/05-audio-engine.md`, *Per-block processing* (line ~104):**
- Add an "as built" paragraph after the bullets:
  - Positions come from the snapshot plus `POSITION` commands (D-121);
    `automation.eval` is M6.
  - Windowed copies are ordered all fading-out, then all fading-in, rather
    than interleaved `0::2`/`1::2` (D-122: contiguous halves).
  - float32/complex64 with `norm="ortho"`.
  - The accumulator is `nfft` long; it drains while stopped.
- Correct *Cost estimate* (line ~180). It says "well under a millisecond".
  The measured figures are 1.47 ms mean and 2.61 ms p99 for 32 sources
  against a 10.67 ms budget. That is still a wide margin, but not "under a
  millisecond". Python's per-channel call overhead is the reason, as the
  plan's risk predicted.

**`docs/02-architecture.md`:**
- Layout, under `audio/` (line ~71): add
  `spatial.py  each non-bypassed channel heard from where it is (D-121, D-122, M4)`.
- In the D-105 paragraph (line ~329), add that a position is the ring's
  kind of change too, as a `POSITION` command tagged with the generation
  (D-121), and that bypass, distance settings and the bank are the
  snapshot's.

D-121 and D-122 are **already written** in `docs/01-requirements.md`, lines
273–274. The doc-system high-water is F-60 / D-122, and nothing new needs a
number.

### 5. Commit (local only; the user pushes)

Stage **only** these paths. Never the dotfiles (`.bashrc`, `.zprofile`,
`.claude/`, etc.), `HANDOFF.md`, `handoff_sweep_phase5.py`, or
`src/immersive/assets/themes/danooc.3dimtheme`. That last one was untracked
before this session started; it looks like the user's own theme, so leave
it alone.

```
src/immersive/audio/spatial.py  src/immersive/audio/engine.py  src/immersive/audio/feed.py
src/immersive/audio/scheduler.py  src/immersive/audio/hrtf/lookup.py  src/immersive/audio/hrtf/bank.py
src/immersive/ui/main_window.py
tests/test_spatial.py  tests/test_feed.py  tests/test_lookup.py  tests/test_realtime.py
docs/...  (the files from step 4)
```

Message style, following the earlier ones: `m4 phase 5: complete - the
engine, spatial`. End it with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Earlier phases
used a commit per step, then a "complete" commit. One commit for the whole
phase is fine here, since the steps were never committed separately.

### 6. Then M4 phase 6: bypass and the master bus

Same workflow: plan → decisions (next is **D-123**) → build → sweep →
close. See `docs/m4_binaural_engine/phase_6_bypass_and_master.md`. Scope:
- a pan law and balance for bypassed channels (05, *HRTF bypass*, *Pan
  law*, and the time-alignment caveat);
- master gain;
- the limiter: a −0.3 dBFS ceiling, 1.5 ms lookahead compensated
  internally, 50 ms release, a 2 dB knee (D-54).

**The limiter's algorithm is the plan's first decision** (the README's
"Questions the plans must settle"). It must stay allocation-free in
`process()`, so extend the realtime subprocess test to cover it.

## What the uncommitted phase 5 code does

- **`audio/spatial.py`** (new): `Space`, one per snapshot, built on the UI
  thread. Every buffer is preallocated.
  - `render()`, per block:
    - distance gain, ramped per sample;
    - the channel meter, tapped after distance and before the HRTF
      (D-117);
    - `lookup.weigh` and `Lookup.blend` for the signed ITD;
    - per channel, a 3-vertex filter blend per ear, and the far ear
      delayed by a phase ramp;
    - the input-windowed crossfade (D-37), then one batched `rfft`;
    - a per-ear multiply-and-sum over channels in the frequency domain,
      then 2 `irfft`s and an overlap-add tail.
  - `drain()` runs while stopped, so a pause decays and a resume does not
    replay.
  - `fresh` skips the crossfade on the first block.
  - `crossfade=False` is a test-only switch for the A/B.
- **`audio/engine.py`:**
  - The ring widened to 6 columns (`WIDTH = 6`), with a new `POSITION = 5.0`
    command and `send_position(generation, channel, x, y, z)`.
  - POSITION applies only when its generation matches. SEEK sets
    `space.fresh`.
  - `_mix` downmixes spatial lanes to a mono point, `(L+R)/2`, into
    `space.src`.
  - `process` calls `space.render` while playing and `space.drain` while
    stopped. `_take_up` carries the tail across a swap when shapes match.
- **`audio/scheduler.py`:**
  - The snapshot gained `positions (channels, 3)`, `slots` (−1 = flat) and
    `space`.
  - `build(..., bank=None)`: a channel is spatial when there is a bank and
    it is not bypassed.
- **`audio/feed.py`:**
  - Sends positions as it sends gains; a full ring means a reinstall.
  - `set_bank()` rebuilds.
  - Bypass and the distance settings are part of `structure()`.
- **`ui/main_window.py`:** `_hrtf_prepared` hands the bank to the feed.
- **`audio/hrtf/lookup.py` and `bank.py`:** the resolution fix (below).
  The cache `FORMAT` is now 2, so existing phase-4 caches are read as a
  miss and rebuilt once, which takes about 6.4 s.

## Findings this session (for phase 5's Notes)

- **Timing, SADIE at a block of 512** (budget 10.67 ms):

  | Sources | Block time |
  |---|---|
  | 1 | 0.13 ms |
  | 8 | 0.38 ms |
  | 16 | 0.72 ms |
  | 32 | mean 1.47 ms, p99 2.61 ms, worst 3.03 ms |

  Cost grows linearly with channels, which is the per-channel Python call
  overhead the plan named as a risk. The margin is fine, and nothing needs
  batching yet. Phase 8 benchmarks it properly.
- **Crossfade A/B** (440 Hz band-limited sawtooth orbiting at 1 rev/s):
  sidebands were −75.9 dB crossfaded against −43.7 dB plain, a **32.2 dB
  cut** (S0 measured 33.7 dB; the acceptance needs ≥ 20).
- **Zero allocation**, 32 spatial channels moving by `POSITION` every
  block: kept 0, worst peak 1692 B (the line is 2048).
  - It needs **two** warm-up cycles. A float freelist grew by 32 B once, at
    block 132 of 800, after one warm-up.
- **D-122, the FFT finding:** numpy 2's `rfft` with the default norm uses
  the float64 loop for float32 input, allocating 789 KB a block despite
  `out=`. `norm="ortho"` keeps it in float32 (about 1.5 KB). Strided
  operands or mixed dtypes also make numpy buffer, so everything is
  contiguous and of one dtype.
- **A real bug found by the sweep: the lookup's resolution.** `Lookup` read
  its cube-map resolution from the module constant `CELLS` at query time,
  so an index built at a different resolution would index past its own
  cell table. That could happen with a cached index read after the
  constant changed, or with a test fixture that patched it.
  - Fix: `Lookup.resolution` is stored; `assemble()` checks
    `len(offsets) == 6*r*r + 1`; `_cell` and `_sides` take the resolution;
    the bank cache stores it (`FORMAT = 2`).
  - New tests: `test_an_index_keeps_its_own_resolution` and
    `test_cells_that_do_not_fit_their_resolution_are_refused`.
- **The flaky tracemalloc test** is step 1 above.

## Mutation sweep: 19 of 19 caught

| # | Mutation | Caught by |
|---|---|---|
| 1 | ITD on the near ear | impulse pair; ahead/either side |
| 2 | ITD blended from its magnitude | ahead/either side |
| 3 | no ITD | impulse pair |
| 4 | first vertex only | impulse pair; crossfade |
| 5 | no distance gain | distance law; meter after distance |
| 6 | distance not clamped | distance law |
| 7 | no crossfade | crossfade A/B |
| 8 | `H_prev` not reset on a seek | first block after a seek |
| 9 | tail not carried | crossfade A/B |
| 10 | tail replayed after stop | stopped, not replayed |
| 11 | stereo left only | stereo point is the average |
| 12 | bypass spatialised | bypassed as before; bank and bypass rebuild |
| 13 | stale position applied | a position sent is heard next block |
| 14 | default-norm FFT | impulse pair; the zero-allocation test |
| 15 | meter before distance | meter after distance; distance law |
| + | feed never sends positions | position edit sends a command |
| + | feed ignores bypass | bank and bypass rebuild |
| + | resolution from the constant | an index keeps its own resolution |
| + | resolution not checked | cells that don't fit are refused |

Mutation 12 also "failed" the lookup's weighing test once. That was the
flake from step 1, not a real catch.

The script is `handoff_sweep_phase5.py`, copied from
`/tmp/claude-1000/sweep17.py`, which may not survive a restart. Add
`fresh: bool = False` (step 2) before re-running.

## Issues and cautions

- **Sandbox:** keep commands sandboxed. With the sandbox off, `$TMPDIR` is
  `/tmp`, so use literal paths and never `rm` through a variable or glob.
  One such `rm` deleted `/tmp/tmp*` in an earlier session.
- **CI has never run** (the GitHub account has a billing lock). The docs
  saying CI is green are wrong. Local runs are the only signal.
- **Suite timing drifts ±1–2 s** from run to run; don't read anything into
  a single run's time.
- **Suite cost:** SADIE's decomposition is expensive, so tests keep it to
  one consolidated test. The spatial tests use a synthetic `head()` bank
  (the `bank` module fixture in `tests/test_spatial.py`) with a coarse
  index. Keep it that way.
- **The SADIE SOFA** is fetched into `src/immersive/assets/hrtf/`, which is
  gitignored. A fresh clone runs `launch.py --install` to fetch it.
- **Large diffs:** each phase has been one to three commits. Phase 5's diff
  is about 335 lines of changes plus two new files.

## Remaining M4 after phase 5

| Phase | What | Notes |
|---|---|---|
| 6 | bypass pan law and balance, master gain, limiter | limiter algorithm = first decision |
| 7 | the pane's spatial fields, including position X/Y/Z moved here from M5 | the fields exist, disabled, naming M5 (M3 phase 7); make them live, one edit per change |
| 8 | benchmark, `sys.setswitchinterval` | "zero xruns" on WSL means timings with a margin; the live count belongs on the listening machine |
| 9 | heard | only the user can do this: native Windows/Linux, headphones; QA-30 picks the default dataset by listening |

## The user's own open items (waiting on a listening session)

- M2 phase 7 and M3 phase 10 listening boxes, on native Windows or Linux
  with headphones. One sitting covers both (M3 phase 10's Notes).
- M4 phase 9 needs the same machine and headphones.
