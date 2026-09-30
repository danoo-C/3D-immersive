# Plan — M4 · Phase 11 — The spatial path, compiled

**Written:** 2026-09-29 · **Status:** ✅ built

## Approach

**The kernel is the Python render, rewritten as loops.** `Space.render`
becomes a thin method. It hands the space's arrays to `_render`, a
module-level function under `@njit(nogil=True, cache=True)`, and then marks
the space no longer fresh. `_render` does what `render`, `_placed`,
`_filter`, `_pair_gains`, `_delay` and `drain` did, in the same order and in
the same float32 arithmetic. It uses explicit loops where the Python
vectorised with numpy calls, since a loop in numba is compiled, not
interpreted. The FFTs are rocket-fft's `r2c` and `c2r`: pocketfft, which
numpy also uses, writing into `spectra` and `inverse` with the scale that
`norm="ortho"` applied (D-122). The only work left in Python is the call.

**One walk over the sphere.** The lookup's walk (D-119) moves into
`lookup.py` as numba functions. `Lookup.weigh` calls them, and so does the
kernel, so there is one implementation, not a Python one and a compiled
one. The tuples the Python walk read are dropped, and `candidates` reads
the arrays.

**The Python render is kept as the reference.** It moves to
`tests/reference_spatial.py`, unchanged, as a function of a `Space`. The
tests play the same arrangement twice, once through each, and compare the
output and the meters block by block.

**What the kernel is given.** It takes the space's arrays as they are, plus
four made once in `Space.build`: each source's channel and side, the pairs
as `[P, 2]`, and the bank's evening gains, or ones where a bank has none.
Every array is C-contiguous with a fixed dtype, and every flag is a Python
bool, so the kernel has one signature (D-139).

**Compiled on the worker.** `spatial.warm(bank)` builds a small space from
the bank, one point and one pair, and renders it once. That compiles the
kernel, or loads it from numba's cache. `ui/hrtf.py`'s worker calls it
after `prepare`, before the bank is handed to the window.

### What the spike found

Measured before this plan, as phase 10's prototypes were:

- numba 0.67.0, llvmlite 0.49.0 and rocket-fft 0.3.1 install as wheels
  beside numpy 2.4.6 on Python 3.13.
- The spatial path as one kernel equalled the Python render within 3.6e-7,
  with meters within 1.5e-8, over 60 blocks. That held for 32 points, 16
  linked pairs with level as mixed on and off, and 8 points.
- 32 sources took 0.88 ms a block at the mean against Python's 1.53, and
  1.48 ms at p99 against 2.24.
- With the kernel in the window's engine (`contention`, two rounds of
  8 s), playing and scrolling missed no block at either interval.
  Repainting missed 785 of 812 blocks at 5 ms and 930 of 1037 at 1 ms,
  taking 15 to 20 ms at the median, against phase 10's 58 to 67. What is
  left is the rest of the block, which is phase 12's.
- The first compile took 5.5 s from a cold cache and 0.44 s from a warm one.

## Decisions settled here

**D-138**: the engine's block is compiled by numba and releases the GIL
while it runs; the spatial path first. **D-139**: kernels compile on the
worker that prepares the bank, have one signature, and are cached by numba
beside the module.

## Steps

1. **The dependencies and the walk.** numba and rocket-fft in
   `pyproject.toml`, `uv.lock`, THIRD-PARTY-NOTICES.md and 02. The lookup's
   walk as numba functions, with `Lookup.weigh` calling them. Tests:
   `test_lookup.py` as it stands, since containment, weights, SADIE and
   the ITD's continuity all go through `weigh`.
2. **The kernel.** `_render`, `Space.build`'s index arrays, and the thin
   `render`. The Python render moves to `tests/reference_spatial.py`.
   Tests: the kernel equals the reference, output and meters, block by
   block, for points, linked and free pairs, sources inside the centre,
   level as mixed on and off, the crossfade off, and across a seek and a
   snapshot swap. Then the existing suite, which hears the kernel now.
3. **Compiled on the worker.** `warm`, called by the HRTF worker. Tests:
   after `warm`, rendering every arrangement above compiles nothing new;
   the window's bank arrives already warm.
4. **Measured.** The zero-allocation test with the kernel; `blocks`;
   `contention` for playing, scrolling and repainting; the suite's time.
   Recorded in the Notes.
5. **The sweep and the close.** The named mutations; the suite once with
   `NUMBA_BOUNDSCHECK=1` and a cache of its own, since an out-of-range
   index in a kernel reads memory instead of raising; the docs, the
   acceptance, the Notes and the Outcome.

## Files

`pyproject.toml`, `uv.lock`, `THIRD-PARTY-NOTICES.md` — the dependencies
`src/immersive/audio/hrtf/lookup.py` — the walk, compiled
`src/immersive/audio/spatial.py` — `_render`, `warm`, the index arrays
`src/immersive/ui/hrtf.py` — `warm` on the worker
`tests/reference_spatial.py` — new: the Python render, as it was
`tests/test_spatial_compiled.py` — new
`docs/02-architecture.md` — the dependency table

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the crossfade's halves swapped, last block's filters fading in | the kernel equals the reference |
| 2 | a pair's side in the centre fading to both ears | equals the reference: pairs in the centre |
| 3 | the evening gains ignored with level as mixed on | equals the reference: level as mixed on |
| 4 | a pair's gain without its shared term | equals the reference: pairs |
| 5 | the ITD's delay on the near ear | equals the reference |
| 6 | the space left fresh after a block | equals the reference, across blocks |
| 7 | the overlap-add tail not moved up a block | equals the reference |
| 8 | the meter read before the gain | equals the reference: the meters |
| 9 | the inverse scaled by `1/n`, not `1/sqrt(n)` | equals the reference |
| 10 | the transform along the wrong axis | equals the reference |
| 11 | the walk crossing the edge opposite the largest weight | `test_lookup`: containment |
| 12 | `warm` not called on the worker | the window's bank arrives warm |
| 13 | the pairs given as `int32` *(amended: `warm`'s positions as `float32`, see the Outcome)* | rendering every arrangement compiles nothing new |

## Risks and unknowns

- **An index out of range reads memory rather than raising.** numba checks
  no bounds by default. The reference comparison covers the paths, and the
  sweep step runs the suite once with bounds checked.
- **Compiling costs the suite.** Each xdist worker compiles, or loads from
  the cache, once. After a change to a kernel, the first run pays the
  compile in every worker at once. The sweep purges `__pycache__`, and
  numba's cache with it, so every mutation run compiles.
- **A numba release can lag numpy.** numba 0.67 takes numpy below 2.6,
  which caps numpy for the project until numba moves (D-138).

## Out of scope for this plan

| Not here | Where |
|---|---|
| The lanes, the audition, the master, the limiter, and the stopped drain in kernels | phase 12 |
| A cheaper repaint of the window | M5 |
| `NUMBA_CACHE_DIR` for a frozen build | M8 (D-139) |

## Outcome

Built as planned: the walk compiled and shared, the spatial path as one
kernel held to the Python it replaced, compiled on the worker, measured.
What the plan did not foresee:

- **`audio/compiled.py`**, the one place a kernel's options live. It was
  needed twice over. numba's runtime cost every array argument a 48-byte
  record, 2.8 KiB a block, over D-106's line, so kernels run without it,
  and then cannot make an array at all. And numba's cache keeps a kernel's
  stale code when a kernel it calls changes in another file, so the
  module clears the package's cached kernels whenever a source changes.
  Both are in the phase's Notes, with what was measured.
- **Two slice copies became loops.** Without the runtime, a slice
  assignment of one array into another has no compiled form.
- **Named mutation 13 was wrong.** "The pairs given as `int32`" cannot be
  caught and cannot do harm: `warm` builds its space with the same
  `Space.build`, so it compiles the very type the engine will call. The
  real hazard is `warm` giving the kernel a type the engine does not, so
  the sweep made `warm`'s positions `float32` instead.

The kernel equals the reference within 2e-6, output and meters, in every
arrangement tested. 32 sources take a p99 of 1.2 to 1.3 ms a block, where
they took 3.0. With the window loaded, playing and scrolling miss almost
nothing: 0 to 3 blocks in 2250, and one run of 10, which was a single
stall. Repainting still misses most blocks, at 16 to 19 ms each, because
the rest of the block is still Python.

Nineteen mutations were run: the thirteen named, the thirteenth corrected
as above, and six more. All were caught but one at first. *The GIL kept*
survived: a thread counting beside a kernel that held the GIL still got
the switch interval's slices just before and after it, tens of thousands
of counts, which cleared a bare threshold. The test now holds the count to
a third of the thread's own pace over a quarter-second kernel, and catches
it. Separately, the suite once with bounds checked: clean.

The first full run after the sweep failed a window test waiting for its
bank. Eight workers had compiled the kernel cold at once. The kernels are
now compiled once in the test controller before the workers start
(Notes).

What phase 12 needs: the rest of the block in kernels, called once a
block, through `compiled.kernel`, held to the Python it replaces in the
same way. Also `gc.freeze()` after load, since one full collection took
50 ms (phase 12's Notes).
