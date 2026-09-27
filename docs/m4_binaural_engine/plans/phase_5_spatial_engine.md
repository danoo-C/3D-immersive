# Plan — M4 · Phase 5 — The engine, spatial

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

The flat engine stays as it is for every channel that is bypassed, and for
every channel while there is no bank. Every other channel takes the spatial
path, which is 05's *Per-block processing*, built to D-106's rule.

**How it gets there (D-121).**
- **Snapshot**: now carries each channel's position, whether it is spatial
  (a bank, and not bypassed), the project's distance settings, the bank,
  and every buffer the spatial path writes, all allocated on the UI thread
  and sized to its spatial channels and the bank's `nfft`.
- **Positions**: change through the ring as `POSITION` commands, tagged
  with the generation. The ring grows to six numbers a command.
- **Feed**: sends positions as it sends gains. It takes the bank through
  `set_bank()`, which rebuilds, and treats bypass and the distance settings
  as structure.
- **Window**: hands the feed the bank when the preparer delivers it.

**What a block does, per spatial channel**, after the lane is filled and
its gain ramped as today:
1. **A mono point** (D-16): the two sides averaged into the channel's row
   of `src`. A mono clip is already both sides, so it comes through
   unchanged.
2. **Distance** (D-21): `(ref / max(r, min)) ** rolloff`, ramped across
   the block from the last block's value. The channel's meter is tapped
   here, before the HRTF (D-117).
3. **Where it is heard from**: the position's direction weighed by the
   lookup, and the ITD blended signed (`Lookup.blend`). The filter is
   `H = Σ wₖ · filters[vₖ]`, per ear, with the far ear multiplied by a
   phase ramp of the ITD's size, so both delays are non-negative (05).
4. **The crossfade** (D-37): the source windowed twice, fading out
   against `H_prev` and in against `H`. Every channel's two copies go
   through **one** batched `rfft`. The products are summed over channels
   in the frequency domain, per ear. Two `irfft`s follow, and an
   overlap-add accumulator of `nfft` samples carries the tail. `H_prev`
   becomes `H`.

**The transforms (D-122)** are float32 into complex64 with `norm="ortho"`,
the only way numpy 2's public FFT takes its float32 loop, and the two
scalings cancel. Every array the path touches is contiguous and of one
dtype: each ear's filters are their own `[S, bins]` array, and the windowed
copies are ordered all-out then all-in, so each half is one block of rows.

**Edges.**
- A seek, or a snapshot taken up, sets `H_prev = H` for the first block,
  so nothing crossfades from a stale filter (05). The tail is kept, since
  it is sound already begun.
- Stopped, the accumulator is still drained into the bus and shifted, so
  a pause lets the last few milliseconds decay rather than cutting them,
  and a resume does not replay them.
- A position at the origin is taken as straight ahead, at `min_distance`.

## Decisions settled here

**D-121**: positions travel as gains do, in the snapshot and by ring
commands, and the ring grows to six numbers.

**D-122**: float32 and complex64, `norm="ortho"`, contiguous and one dtype.

## Steps

1. **The plumbing.** The ring at six numbers, `POSITION`, the snapshot's
   spatial fields and buffers, the feed's positions and `set_bank()`, and
   the window handing the bank over. Tests:
   - a position sent is in place at the next block;
   - one for another generation is dropped;
   - bypass and rolloff rebuild the snapshot and a position does not;
   - with no bank, every channel is flat and plays as before.
2. **The spatial block.** Everything under *What a block does*, and the
   edges. Tests:
   - an impulse at a measured direction comes out as that direction's
     minimum-phase pair with its ITD on the far ear, to within float32;
   - the front is equal in both ears, +X is louder and earlier on the
     right, and −X the reverse;
   - halving the distance past `ref_distance` raises the level by
     `rolloff × 6.02` dB, and inside `min_distance` it stops rising;
   - four channels together equal the four alone, added;
   - no discontinuity at a seek or a swap: the first block's filter is
     `H` on both halves;
   - a bypassed channel comes out as it did before this phase;
   - stopped, the tail drains and is not replayed;
   - a channel's meter reads its level after distance.
3. **Measured.**
   - **The crossfade**, S0's way: a band-limited 440 Hz sawtooth orbiting
     at 1 rev/s. Its block-rate sidebands with the crossfade are at least
     20 dB below those with it switched off by a test-only switch (S0 cut
     them by 33.7 dB), which also proves it is running.
   - **The zero-allocation test** holds with 32 spatial channels moving by
     `POSITION` every block.
   - **32 channels' block time**, recorded.

## Files

`src/immersive/audio/engine.py` — the ring, `POSITION`, the spatial block
`src/immersive/audio/scheduler.py` — the snapshot's spatial fields and
buffers
`src/immersive/audio/feed.py` — positions, `set_bank()`, structure
`src/immersive/ui/main_window.py` — the bank to the feed
`tests/test_spatial.py` — new; `tests/test_engine.py`, `tests/test_feed.py`,
`tests/test_realtime.py` — extended

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the ITD on the near ear | +X earlier on the right |
| 2 | the ITD blended from its magnitude (phase 3's ninth) | a source crossing the median plane |
| 3 | no ITD at all | the impulse's pair with its ITD |
| 4 | the weights not applied (first vertex only) | four-channel equality / the impulse |
| 5 | distance gain not applied | the rolloff law |
| 6 | the distance not clamped at `min_distance` | stops rising inside `min_distance` |
| 7 | no crossfade (`H` on both halves) | the sideband A/B |
| 8 | `H_prev` not reset on a seek | the first block after a seek |
| 9 | the tail not carried | the impulse's tail across the block boundary |
| 10 | the tail replayed after a stop | stopped, the tail is not replayed |
| 11 | stereo not averaged (left only) | a stereo channel's point is the average |
| 12 | a bypassed channel spatialised | a bypassed channel as before |
| 13 | a position for another generation applied | dropped when stale |
| 14 | an FFT with the default norm (float64 loop) | the zero-allocation test |
| 15 | the meter tapped before distance | the meter after distance |

## Risks and unknowns

- **Python's per-call overhead per source.** About twenty numpy calls a
  channel for the filter, its ITD and its windows: at 32 channels a few
  hundred calls, perhaps a millisecond. Measured in step 3. If it is too
  much, the filters are built for all channels at once with gathers into
  one buffer, which the plan leaves until a measurement asks.
- **Numerical agreement with a direct convolution** is float32's, 10⁻⁶ of
  full scale. The tests compare against a float64 reference at that
  tolerance.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Pan and balance for bypassed channels, master gain, the limiter | phase 6 |
| The pane's position fields | phase 7 |
| The N-1 benchmark with the UI repainting | phase 9 |

## Outcome

Built as planned, and D-121 and D-122 held. The fifteen named mutations
were all caught, though not all by the test named for them. The tail not
carried (9) was caught by the sideband A/B. The default-norm FFT (14) was
caught by the zero-allocation test and by the impulse's pair as well. Six
more were caught: the feed never sending a position, the feed ignoring
bypass, and two in the lookup's resolution, which was a real bug and is
fixed (the phase's Notes). The last two are at a swap: a new space that
does not start fresh, and its tail not carried across. Step 2's "no
discontinuity at a swap" had no test until the sweep was checked against
the acceptance at the end, and it has one now.

What phase 6 needs: a bypassed channel already plays flat, as it did before
this phase, into the same `bus_l` and `bus_r` the spatial path adds into.
The pan law and balance go on its lanes in `_mix`, and master gain and the
limiter on the bus after both paths. The limiter runs inside `process()`,
so the realtime subprocess test must cover it; `run_spatial` already has a
bypassed channel beside the 32 spatial ones. 05's *Time alignment caveat*
stands as written: a spatial channel is heard 0 to about 1 ms after a
bypassed one, and v1 leaves it so.
