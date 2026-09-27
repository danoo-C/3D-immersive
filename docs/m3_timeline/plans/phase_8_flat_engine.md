# Plan — M3 · Phase 8 — The engine, flat

**Written:** 2026-09-26 · **Status:** ✅ complete

## Approach

Three layers, as `02` places them, and one more for crossing the threads.

**`audio/dsp.py`: arithmetic on blocks.** Decibels to linear gain, fade
tables from `FadeShape.gain`, a gain ramp across a block. Qt-free,
device-free, and tested sample by sample.

**`audio/scheduler.py`: what plays.** An immutable `Snapshot`, built on the
UI thread from the project and the session's decoded audio (D-17). For each
channel it holds the clips in order: where each starts and ends, its
samples, its linear gain, and its fade tables with D-42's implicit edges
already decided. `fill()` writes one channel's part of a block into a
preallocated buffer. The snapshot is never written after it is built, and
nothing in it is a model object.

**`audio/engine.py`: the seam.** `Engine.process(out)` takes up the newest
snapshot and drains the command ring. It fills each channel and ramps each
channel's gain across the block. It sums everything into a stereo bus,
records the bus's peaks, and advances the playhead. `Engine.callback` is
what the stream calls: it counts underflows and then calls `process`.
Nothing on this path reads the model, locks, logs or formats a string.

**`audio/feed.py`: the UI thread's side (D-105).** A `Feed` watches the
document and the session's audio and decides, after every change, which of
two things the engine is told:
- the structure changed (clips, samples, clip gain, fades, the channels'
  order), so a new snapshot is built and handed over;
- only a channel's gain, mute or solo changed, so a command goes through
  the ring.
It keeps every snapshot it has handed over until the engine has moved past
it, and releases them itself, on the UI thread. Phase 9 connects it to the
window; here it is tested against a `Document`, with no window.

The alternative was a snapshot for everything, gain included: one mechanism
instead of two. It was rejected because gain is what a person changes
continuously while listening, and each step would rebuild every clip's
tables. The spec also asks for the ring, and M4 will send positions through
it at the same rate.

## Decisions settled here

**Snapshot or command (D-105).** This is the question the milestone left
here. Structure goes in the snapshot. A channel's gain, mute and solo are
folded by `audible()` on the UI thread into one linear gain per channel and
sent as a command, tagged with the snapshot's generation; a command for
another generation is dropped. A seek is a command too, so it cannot race a
swap. Mute therefore ramps to silence like any gain change, instead of
clicking.

**What "allocates nothing" means (D-106).** No memory kept from one block
to the next, and no numpy array created inside a block. The test runs
hundreds of blocks under `tracemalloc`: traced memory ends where it began,
and no block raises the peak by 2 KiB, a quarter of one side of a
2048-frame block. Measured while planning: small Python objects (views,
integers, argument tuples) raise it by at most about 1 KiB, and a block
temporary by 8 KiB or more. The measurement also found a trap: a ufunc
that broadcasts, such as a `(B, 1)` ramp over a `(B, 2)` block, allocates
17 KiB even with `out=`. So lanes are planar, one contiguous row per ear,
and a ramp is applied row by row with its views made once.

**Per-block lookup, not a cursor.** `05` describes a cursor advanced along
each channel's clips. A binary search on the clips' ends at the top of each
block is as cheap at these sizes (tens of clips, one search per channel per
block), and it holds no state. A seek or a swap then needs no cursor reset,
and there is no reset to get wrong. `05` is amended to say so.

**How a fade is sampled.** A fade-in of length `L` is `gain(k / L)` at its
`k`th sample, so its first sample is silent and the one after it is whole.
A fade-out is the same curve backwards, `gain((L - 1 - k) / L)`, so its last
sample is silent. The implicit edge fade (D-42) is linear and 32 samples
long, never more than half the clip, and only where the explicit fade on
that edge is empty and the edge is not the file's own.

**A block of another size is silence, and is counted.** The stream is
opened with a fixed block size, and PortAudio then delivers exactly that.
A callback asked for any other number of frames writes silence, leaves the
playhead where it is, and counts it with the underflows, rather than
guessing how to play part of a block.

## Steps

1. **What plays: `dsp.py` and `scheduler.py`.** Fade tables, gain
   conversion, the `Snapshot` and its build, and `fill()`.
   *Test (headless):* a clip plays its sample from `offset` for `length` at
   `start`, exact to the sample across block boundaries at 256, 512 and
   2048, including a clip that starts and ends inside one block; a
   whole-sample clip at 0 is bit-transparent; an edge away from its file's
   start or end fades over 32 samples, and an explicit fade replaces it;
   linear and equal-power fades follow `FadeShape.gain`; clip gain in dB; a
   mono clip reaches both ears and a stereo clip keeps its sides; a missing
   sample plays silence beside a clip that plays.

2. **The engine: `engine.py`.** `process()`, the snapshot swap, the command
   ring with its generation tag, gains ramped across a block, seeking,
   peaks per side and the underflow count.
   *Test (headless):* the bus is the sum of the channels at their gains;
   mute and solo silence exactly what `audible()` says; a gain change ramps
   across one block, and no step between samples is larger than the ramp's;
   a snapshot handed over mid-play takes effect at the next block, whole,
   and the old one is still alive after the swap; a command tagged for an
   older snapshot is dropped; after a seek the next block starts at the new
   playhead; peaks are the bus's; underflows are counted, and so is a
   block of the wrong size, which is silence.

3. **The feed: `feed.py`.** The document watched from the UI thread. A
   structural edit builds and hands over a snapshot, and a gain, mute or
   solo edit sends a command. Samples arriving in the store rebuild the
   snapshot. Snapshots are released on the UI thread once the engine is
   past them.
   *Test (headless):* moving a clip hands over one snapshot and no command;
   changing a gain sends one command and no snapshot; Undo of each does
   the same; soloing one channel sends a zero to every other; a sample
   decoded after its clip was placed makes the clip heard; a reorder
   followed by a gain lands the gain on the right channel; an old snapshot
   is freed by the feed's `release()`, never by `process()`, checked with a
   weak reference.

4. **Allocating nothing.** The D-106 test over an arrangement with fades,
   gains ramping, a mute, a seek and a swap. Whatever it finds is fixed.
   *Test:* traced memory after 500 blocks is what it was; no block raises
   the peak by 2 KiB; the same with `-O`, if the asserts' removal changes
   anything.

5. **Written down, and timed.** `05`'s *Scheduler* (the lookup and fade
   sampling), *Metering* (how the peaks are handed over) and *Realtime
   safety checklist* (D-106's definition). `02`'s *Crossing from UI to
   audio* (the generation tag, and who frees a snapshot). The time
   `process()` takes for a block of 512 with eight channels of clips,
   recorded as a first number beside S0's, not as M4's benchmark.

## Files

```
docs/01-requirements.md                     amended — two decisions
docs/02-architecture.md                     amended — crossing threads; feed.py
docs/05-audio-engine.md                     amended — scheduler, metering, checklist
docs/doc-system.md                          amended — high-water mark
src/immersive/audio/dsp.py                  new
src/immersive/audio/scheduler.py            new — the snapshot and fill()
src/immersive/audio/engine.py               new — the seam
src/immersive/audio/feed.py                 new — the UI thread's side
tests/test_dsp.py                           new — headless
tests/test_scheduler.py                     new — headless
tests/test_engine.py                        new — headless
tests/test_feed.py                          new — headless
tests/test_realtime.py                      new — the allocation test
tests/test_layering.py                      amended — audio/ stays Qt-free
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A ufunc that allocates behind `out=` | a block-sized temporary ninety times a second, invisible in review | found while planning, for broadcasting; the D-106 test runs over every path, and planar lanes avoid the case |
| A snapshot freed in the callback | a destructor, and possibly the garbage collector, on the audio thread | the feed holds every snapshot it handed over until the engine has moved on; a weak reference shows the old one alive after the swap |
| A command applied to the wrong channel after a reorder | a gain change heard on a neighbour | commands carry the snapshot's generation; the engine drops a stale one, and the snapshot was built with the current gains anyway |
| Structural and gain changes told apart wrongly | a gain edit that rebuilds everything, or a clip edit the engine never hears | the feed compares a structure key built from the project, and tests pin both directions |
| A seek racing a swap | a block that plays the old snapshot at the new position, or the reverse | the seek is a command, drained after the swap within one block |
| Bit-transparency lost to arithmetic | D-42's exemption broken by a multiply by 1.0 or a sum with silence | both are exact in IEEE floats; a test compares bytes, not values |
| Equal-power fades read as cut short | `gain(k/L)` never reaches 1 inside the fade | 1 is where the fade ends; the sample after it is whole, and a test reads it |
| What PortAudio really delivers | a block size or buffer layout the stand-in does not have | the stand-in follows `sounddevice`'s documentation as M2's does; the real device is phase 10's listening |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| a clip read from its start rather than `offset` | caught by reading the samples |
| the overlap ending at the block rather than the clip | a clip plays past its end |
| a block's lookup starting after a clip that began in the last one | a clip loses its tail at a block boundary |
| the implicit fade applied at the file's own start | bit-transparency lost |
| the implicit fade added to an explicit one | a fade twice as steep |
| a fade-out read forwards | a clip fades in at its end |
| clip gain applied as a linear factor | -6 dB plays at -6 times |
| a mono clip to the left ear only | the right silent |
| the gain stepped at the block's start | a click, and the ramp test fails |
| mute folded in after the ramp | a mute that clicks |
| solo ignored on the engine's side | a soloed mix that plays everything |
| a stale command applied | a gain on the wrong channel after a reorder |
| the swap after the drain | a new snapshot's first block with the old gains |
| the snapshot dropped by the engine on swap | freed on the audio thread |
| a seek that keeps the playhead | the next block continues where it was |
| a gain edit rebuilding the snapshot | a snapshot per step of a drag |
| a clip edit sent as a command | the engine never hears it |
| peaks taken before the channel gain | a meter reading what is not heard |
| an underflow not counted | xruns hidden |
| a broadcasting multiply in `process()` | caught by the allocation test |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Opening the real stream, play and stop | phase 9 |
| `gc.freeze()` after a project loads | phase 9, where a project is first played |
| The meter's hold and decay, and its drawing | phase 10 |
| HRTF, distance, the bypass path and its pan law | M4 |
| Master gain and the limiter | M4 |
| The thirty-two-source benchmark, and D-39 | M4 |
| Automation read per block | M6 |

## Outcome

Five steps in the planned order, and all twelve acceptance boxes are
ticked. Sixty-one mutations: nineteen of the twenty named in advance and
forty-two found on the way, all killed. Four survived at first, each for a
missing test. A sixty-second was malformed, equivalent by construction,
and is not counted. The twentieth named, "mute folded in after the ramp",
has no line to break: mute is a gain by D-105, and a test holds that it
ramps. 2020 tests.

### What the plan got right

**Measuring before deciding.** The allocation experiment in the plan found
the broadcasting trap before any engine code existed. Step 2 was written
planar from the start, and step 4's test found nothing to change in it.

**The feed as a class of its own.** Deciding snapshot or command, holding
references and releasing them is UI-thread logic, tested with a
`Document` and no window. Phase 9 only has to call `update`.

**Generation tags.** The reorder test that needed them was written from
the plan's risk table, and passed first time.

### What the plan did not see

**A carry that could count in a snapshot never played.** Two snapshots
installed within one block, as the feed does when samples arrive just
after an edit, would have indexed one snapshot's gains by another's
places. `Snapshot.based_on` settles it.

**A local that could free an array on the audio thread.** `_take_up` now
lets go of the old levels before the swap. No single-threaded test can
reach it.

**That the measuring would allocate.** The test's harness kept 64 bytes of
its own, and a list of results kept 20 KiB. The readings go into arrays
made beforehand.

**That the structure key needed a test per field.** Clip gain, fades and
the channels' order all survived their mutations until each had a test,
and the reorder needed two channels that play alike to be told apart
only by their ids.

### Deviations

| Planned | Actual |
|---|---|
| A seek through the ring, drained after the swap | as planned; `seek()` also says when the ring is full, for phase 9 |
| The same test with `-O` | not run: `process()` has no asserts to remove |
| `tests/test_layering.py` amended | unchanged: its rule already covers `audio/`, and the new modules import no Qt |
| Twenty mutations | sixty-one |

### What phase 9 needs to know

- **Wiring:** `Engine(block)` with `--block`'s size. `Feed(engine,
  store.audio)` is called after every document change and when samples
  arrive (`_loaded` and `_imported`). The stream's callback is
  `engine.callback`.
- **Transport:** `engine.playhead` is where the next block starts;
  `engine.seek()` moves it and returns False when the ring is full. A
  stopped stream drains nothing, so seeks while stopped need another way
  in, or the ring to be drained when playback starts.
- **Meter and xruns:** `engine.take_peaks()` for the meter, and
  `engine.xruns` for the status bar.
- **Garbage collection:** `gc.freeze()` after a project loads is phase 9's,
  where a project is first played.
- **Audition:** it still opens its own stream. One stream or two is
  phase 9's question.
