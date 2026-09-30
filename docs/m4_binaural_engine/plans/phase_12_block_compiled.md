# Plan — M4 · Phase 12 — The whole block, compiled

**Written:** 2026-09-30 · **Status:** ✅ built

## Approach

**One kernel a block.** `Engine.process` keeps in Python the bookkeeping,
which makes no numpy call and so never lets the GIL go: taking up a
snapshot or a voice, draining the ring, and cutting the block into the
pieces a loop wraps at. Everything after that is `_block`, one kernel,
called once. It takes the engine's own arrays, the snapshot's, the
space's, the limiter's and the voices', and in order it:

1. clears the bus;
2. reads each lane's clips into its rows, a piece at a time, with their
   fades and gains, then applies the channel's four factors, ramped
   (D-125), and sends the result to the space as a point or a pair, or to
   the bus and the channel's meter;
3. renders the space (phase 11's kernel, called inside this one), or when
   stopped, drains its tail;
4. sounds the audition, and a voice that is falling;
5. applies the master gain, ramped, and the limiter;
6. reads the master meter, and writes the block out.

What the engine carries from block to block as numbers (the master's
level, the limiter's switch and release, each voice's read position) is
kept in small arrays the kernel writes, and the Python attributes read
from them.

**A sample is read through its address (D-140).** A snapshot has any
number of samples and fade tables, one array each, and without numba's
runtime a kernel can be handed neither a list of arrays nor a view of one
it builds (phase 11's Notes). So the snapshot builds one table, a row per
clip: where it sits on the timeline, where it starts in its sample, the
sample's address, frames and channels, and each fade table's address and
length, with the clip's gain beside it. A kernel reads a float32 at an
address through `compiled.read`, a two-line intrinsic, which a spike
showed reads correctly, allocates nothing and caches. Every address is of
an array the snapshot holds, and the feed holds the snapshot until the
engine has let it go (D-105), so no block can read an array after it is
freed. A missing sample is address 0, and plays silence as it does now.

**Compiled before any stream opens (D-141, amending D-139).** The flat
path plays before the HRTF bank arrives, so the block kernel cannot wait
for the bank to be warmed. `engine.warm()` plays one block of a tiny
arrangement through a scratch engine, which compiles the block kernel or
loads it from numba's cache. The HRTF worker calls it where it called
`spatial.warm`, so a launch usually has it compiled before anyone presses
Play. The player calls it too, before it opens a stream: once compiled
it costs nothing, and if the worker has not finished, Play waits for the
compile on the UI thread before any audio thread exists. The kernel is
handed arrays of the same kinds whether there is a space or not, empty
ones when there is none, so there is one signature.

**The references.** The Python block as it stands, `_mix`, `fill`,
`_audition`, `_master` and the limiter, moves to
`tests/reference_engine.py`. The engine's output is held to it through
every path the zero-allocation test takes. `fill()` and `Limiter.process`
stay callable from Python, as thin calls into the kernels the block uses,
so `test_scheduler.py` and `test_limiter.py` go on testing what plays.

**Collections.** Phase 11 saw one full collection take 50 ms, which holds
the GIL. The plan measures what collections cost with the window playing,
and settles `gc.freeze()` after a project loads (05's checklist) on the
numbers, as a decision of its own.

## Steps

1. **The lanes as a table, and `fill` compiled.** `compiled.read`; the
   snapshot's clip table; `_fill`. Tests: `test_scheduler.py` as it is,
   and `_fill` against the reference over the zero-allocation test's lanes.
2. **The limiter compiled.** `_limit`, with its state in arrays. Tests:
   `test_limiter.py` as it is, and `_limit` against the reference, block
   after block, the switch fading both ways.
3. **The block.** `_block`, with `Engine.process` calling it once. Tests:
   the engine against the reference through every path; the flags and the
   zero-allocation test.
4. **Compiled before any stream.** `engine.warm`, on the HRTF worker and
   in the player before it opens a stream. Tests: one signature with a
   space and without one; the player's stream opens only after the kernel
   exists.
5. **Collections, and the measurements.** Collections measured with the
   window playing, then the decision. `contention` at both intervals, `blocks`,
   the zero-allocation test.
6. **The sweep and the close.**

## Decisions settled here

**D-140**: a kernel reads a sample, or a fade table, through its address,
from a table the snapshot builds, and the snapshot holds every array it
names. **D-141**: the block kernel is compiled before any stream opens: on
the HRTF worker, and by the player before opening a stream. It amends
D-139, whose "on the bank's worker" alone would leave the flat path
compiling on the audio thread. Collections are settled by step 5's
measurement, and recorded then under the next number.

## Files

`src/immersive/audio/compiled.py` — `read`
`src/immersive/audio/scheduler.py` — the clip table; `fill` as a kernel
`src/immersive/audio/limiter.py` — `_limit`
`src/immersive/audio/engine.py` — `_block`, `warm`
`src/immersive/audio/spatial.py` — its arguments as one tuple; `drain`
compiled
`src/immersive/audio/player.py` — `warm` before a stream opens
`src/immersive/ui/hrtf.py` — `engine.warm` in place of `spatial.warm`
`tests/reference_engine.py` — new: the Python block, as it was
`tests/test_block_compiled.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | a clip's gain not applied | the engine equals the reference |
| 2 | a fade table read from the wrong end | the engine equals the reference: fades |
| 3 | a stereo clip's right read from its left | equals the reference: stereo |
| 4 | a clip whose sample is missing read anyway | equals the reference: a missing sample |
| 5 | a piece's rows not cleared where a loop wraps | equals the reference: loops |
| 6 | a gain ramp's end on the old gain | equals the reference: gains ramping |
| 7 | a mono clip written over a stereo one, not added | equals the reference: mono and stereo together |
| 8 | a point fed its left side only | equals the reference: points |
| 9 | the falling voice at full level | equals the reference: an audition replaced |
| 10 | the master ramp's end on the old gain | equals the reference: the master |
| 11 | the limiter's release not carried across blocks | `test_limiter.py`; equals the reference |
| 12 | the limiter's switch not faded | `test_limiter.py`; equals the reference |
| 13 | the master meter read before the limiter | equals the reference: the meters |
| 14 | the player opening a stream before warming | the stream opens only after the kernel exists |
| 15 | `warm` without a space, so a second signature | one signature with a space and without |

## Risks and unknowns

- **Reading by address is unchecked.** A wrong index reads whatever memory
  holds, and bounds checking cannot see it. So the table is built from
  the arrays themselves, never computed apart from them, every read is
  clamped to the clip's own span as the Python's slices were, and the
  reference comparison covers every path, clips cut at both ends included.
- **This is most of the engine.** The existing engine, scheduler, limiter
  and bypass tests are what hold it, with the reference.
- **The kernel's first compile grows.** Measured in step 5. It is paid on
  the worker, or once at the first Play.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Automation evaluated per block | M6, into this kernel |
| A cheaper repaint of the window | M5 |
| `NUMBA_CACHE_DIR` for a frozen build | M8 (D-139) |

## Outcome

Built as planned in its shape: the lanes as a table read by address,
`fill` and the limiter compiled, then the whole block as one kernel,
compiled before any stream, and collections settled on the numbers. What
the plan did not foresee:

- **`carray` needs the runtime too.** The spike tried it first. Without
  numba's runtime a kernel cannot return an array it made, not even a view.
  So `compiled.read` loads one float32 from an address, and nothing else is
  made.
- **Reading `ndarray.ctypes` every block kept memory**, 48 bytes a block
  while a voice sounded. A voice works out its address when it is made.
- **The spatial twins had to move.** The block kernel calls the spatial
  kernel directly, so phase 11's tests, which put the Python render on
  `Space.render`, would have compared the kernel with itself. They now
  compare the engine with the whole Python block.
- **The HRTF worker compiles the block kernel before the bank**, not
  after: it takes 9 s from a cold cache and needs no bank.
- **Collections were not what phase 11 thought.** With the block compiled,
  steady playback makes none. The freeze after a load (D-142) is insurance
  for edits made during playback, measured at 67 ms for one full
  collection.

With the window repainting without pause, 32 moving sources miss 1 block
in 2255 and 0 in 2256 at 1 ms. 32 sources take 8% of the budget.

Nineteen mutations were run: the fifteen named and four more. All were
caught the first time. "A missing sample read anyway" was caught rather
than crashing: a missing sample has no frames, so the read's clamp read
nothing, and the silence was the wrong silence. The suite also passes
with bounds checking on.

What phase 13 needs: the live count on the listening machine, hands off
and loaded, as its Notes describe. The engine it hears is the compiled one.
The first launch after an install compiles for 9 s on the HRTF worker, so
wait for the HRTF set to be ready before judging the first seconds.
