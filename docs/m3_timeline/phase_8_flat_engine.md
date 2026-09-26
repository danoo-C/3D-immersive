# M3 · Phase 8 — The engine, flat

**Status:** in progress · **Plan:**
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

- [ ] A clip plays its sample from `offset` for `length`, at `start` on the
      timeline, exact to the sample across block boundaries, at blocks of
      256, 512 and 2048 frames.
- [ ] A whole-sample clip at 0 with no gain and no fades is bit-transparent
      (D-42's exemption).
- [ ] An edge away from its file's own start or end gets a 32-sample linear
      fade, and an explicit fade there replaces it rather than adding to it.
- [ ] Explicit fades follow their shape, linear or equal-power, and clip and
      channel gain apply in dB.
- [ ] Mute and solo silence exactly the channels `model.audible()` says.
- [ ] A gain change during playback ramps across one block, and no sample
      steps by more than the ramp allows.
- [ ] A structural edit during playback takes effect at a block boundary,
      whole: no block mixes two snapshots, and the old snapshot is released
      on the UI thread.
- [ ] After a seek, the next block starts at the new playhead's samples.
- [ ] A missing sample plays silence, and the rest of the arrangement plays.
- [ ] A mono clip reaches both ears; a stereo clip keeps its sides.
- [ ] `process()` allocates nothing after warm-up, asserted under
      `tracemalloc`.
- [ ] Underflows the stream reports are counted.

## Implements

D-17, D-42, D-62 — *Scheduler*, *Parameter smoothing*, *Metering* and
*Realtime safety checklist* in [05-audio-engine.md](../05-audio-engine.md),
*Threading* and *Signal flow per block* in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.
