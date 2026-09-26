# M3 · Phase 8 — The engine, flat

**Status:** ✅ complete · **Plan:**
[plans/phase_8_flat_engine.md](plans/phase_8_flat_engine.md)

## Goal

`audio/engine.py` exists, and with it the seam `02` calls *the* seam.
Given a snapshot of the arrangement and a playhead, `process()` fills a
stereo block from the arrangement:

- clip reads at their offsets;
- clip gain;
- explicit fades, and the implicit 32-sample fades at clip edges (D-42);
- channel gain, mute and solo (D-62).

There is no spatialisation: a mono clip goes to both ears, and a stereo
clip plays as it is. A structural edit reaches the engine as a new snapshot,
swapped in whole. Gain, mute and solo reach it through a command ring,
drained at the top of each block, and a gain change ramps across the block
rather than stepping. Everything is tested block by block, headless, against
a stand-in stream, and `process()` allocates nothing.

## Scope

**In:** `audio/engine.py`, `audio/scheduler.py` and `audio/dsp.py`, as
[02](../02-architecture.md) places them; the snapshot, built on the UI
thread from the model and the session's decoded audio (D-17), handed over
with one reference swap and released on the UI thread; the command ring for
parameter changes; the per-channel scheduler cursor (`05`, *Scheduler*);
fade envelopes from precomputed tables; gains smoothed per sample (`05`,
*Parameter smoothing*); seeking, which resets the cursors; a missing sample
playing silence; xruns counted from the stream's status; the bus's peak per
side, written for phase 10's meter (`05`, *Metering*); the zero-allocation
test that `05`'s *Realtime safety checklist* names.

**Out:** the window, the transport and the playhead → phase 9. The meter's
drawing → phase 10. HRTF, distance, the bypass path and its pan law → M4.
Master gain and the limiter → M4. The thirty-two-source benchmark and
D-39 → M4.

## Acceptance

- [x] A clip plays its sample from `offset` for `length`, at `start` on the
      timeline, exact to the sample across block boundaries, at blocks of
      256, 512 and 2048 frames.
- [x] A whole-sample clip at 0 with no gain and no fades is bit-transparent
      (D-42's exemption).
- [x] An edge away from its file's own start or end gets a 32-sample linear
      fade, and an explicit fade there replaces it rather than adding to it.
- [x] Explicit fades follow their shape, linear or equal-power, and clip and
      channel gain apply in dB.
- [x] Mute and solo silence exactly the channels `model.audible()` says.
- [x] A gain change during playback ramps across one block, and no sample
      steps by more than the ramp allows.
- [x] A structural edit during playback takes effect at a block boundary,
      whole: no block mixes two snapshots, and the old snapshot is released
      on the UI thread.
- [x] After a seek, the next block starts at the new playhead's samples.
- [x] A missing sample plays silence, and the rest of the arrangement plays.
- [x] A mono clip reaches both ears; a stereo clip keeps its sides.
- [x] `process()` allocates nothing after warm-up, asserted under
      `tracemalloc`.
- [x] Underflows the stream reports are counted.

## Implements

D-17, D-42, D-62 — *Scheduler*, *Parameter smoothing*, *Metering* and
*Realtime safety checklist* in [05-audio-engine.md](../05-audio-engine.md),
*Threading* and *Signal flow per block* in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.

**A snapshot for what plays, a ring for how loud (D-105).** The question
the milestone left here. Clips, samples, clip gain, fades and the
channels' order are an immutable snapshot, handed over by assigning one
reference. A channel's gain, mute and solo are folded on the UI thread by
`audible()` into one linear gain and sent through the ring, tagged with
the snapshot's generation. After a reorder a channel's index means someone
else, so a command for another generation is dropped. Mute is therefore a
gain of nothing, and ramps like one.

**Nothing is freed on the audio thread.** The engine never holds the only
reference to a snapshot: the feed keeps every one it handed over, and lets
go of them on the UI thread once the engine is past them. Two hazards were
found by reading the code rather than by a test. A second snapshot
installed before the engine played the first carried channel places that
counted in a snapshot the engine had never taken up, which would have
raised inside the callback. A snapshot now records the generation its
places count in. And a local in `_take_up` still held the old snapshot's
array after the swap, so it could have been the last reference and freed
the array on the audio thread as the function returned. The second needs
two threads to happen, which no test here has.

**"Allocates nothing" had to be defined (D-106).** In Python a slice is a
view and an integer past 256 is an object, so nothing cannot mean no
object at all. It means no memory kept from block to block, and no numpy
array made in one. Measured while planning: small objects raise
`tracemalloc`'s peak by under 1 KiB, and a block temporary by 8 KiB or more.
The measuring found a trap too: a ufunc that broadcasts allocates 17 KiB
behind `out=`. So the engine is planar, one contiguous row per ear. The
test runs 500 blocks of 2048 frames through every path; the worst raises
the peak by 980 bytes, and nothing is kept. Its own harness first kept 64
bytes, two integers made after the reading that measured them, found with
a `process()` that did nothing.

**A binary search, not a cursor.** `05` named a cursor advanced along each
channel's clips. A search on their ends at the top of each block is as
cheap, and keeps no state, so a seek or a swap has nothing to reset. `05`
is amended, as it is for the gain ramp: linear across one block, where it
first said one-pole, because a one-pole never arrives.

**Timed**, eight channels of faded clips, half stereo: 0.057 ms a block of
512 on average and 0.10 ms at p99, against 10.7 ms. The flat path is about
1% of the budget; M4's convolution is where the rest will go.

The phase adds 81 tests. The suite is 2020: 25.7 s serially, 8.6 s in
parallel, 3.9 s in the fast lane.
