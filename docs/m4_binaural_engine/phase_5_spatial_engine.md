# M4 · Phase 5 — The engine, spatial

**Status:** ✅ complete · **Plan:** [plans/phase_5_spatial_engine.md](plans/phase_5_spatial_engine.md)

## Goal

The engine plays every channel that is not bypassed through the HRTF: each
channel's block, downmixed to a mono point (D-16), scaled by its distance
(D-21), windowed twice for the crossfade (D-37), transformed in one batched
FFT, multiplied by its interpolated filter with its ITD as a non-negative
phase ramp on the far ear, and **summed over sources in the frequency
domain** before four inverse transforms and an overlap-add (05, *Per-block
processing*). It does this without allocating, as the flat engine does.

## Scope

**In:** positions reaching the audio thread (the plan's first decision);
distance gain with its per-sample ramp; the lookup, the gather and weighting
of the bank, the ITD ramp; the input-windowed crossfade with `H_prev` reset
on a seek and on a snapshot swap; the overlap-add tail and its reset; the
channel peaks tapped before the HRTF (D-117); the zero-allocation test held
over it all.

**Out:** bypassed channels and the master bus → phase 6. Setting a
position from the pane → phase 7.

## Acceptance

- [x] An impulse at a measured direction comes out as that direction's
      minimum-phase pair with its ITD on the far ear, to within float32.
- [x] A source at the front is equal in both ears, one at +X is louder and
      earlier in the right, and one at −X the reverse.
- [x] Halving the distance past `ref_distance` raises the level by
      `rolloff × 6.02` dB, and inside `min_distance` it stops rising.
- [x] A band-limited 440 Hz sawtooth orbiting at 1 rev/s has block-rate
      sidebands at least 20 dB lower with the crossfade than with it
      disabled by a test-only switch - S0's measure and S0's line, where it
      measured 33.7 dB - so the crossfade is provably running (the
      roadmap's named test, measured). *Amended while planning: as first
      written this compared against S0's uncrossfaded figure, a number from
      another engine; the A/B within this one is the measure S0 used.*
- [x] No sample is discontinuous across a seek or a snapshot swap: the
      first block after either does not crossfade from a stale filter.
- [x] `process()` allocates nothing and keeps nothing with 32 spatial
      sources moving, by the zero-allocation test.
- [x] Four channels summed in the frequency domain equal the four convolved
      alone and added, to within float32.

## Implements

D-16, D-21, D-37, D-70, D-106, D-117 - *Per-block processing* and
*Parameter smoothing* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**Built (2026-09-27).** `audio/spatial.py`'s `Space`, one per snapshot and
built with it on the UI thread, holds every buffer the path writes. The
engine downmixes each spatial lane to its mono point and hands the block
over; while stopped, the space only drains its tail. Block time, SADIE II
D1 at 512 frames, against a budget of 10.67 ms:

| Sources | Block time |
|---|---|
| 1 | 0.13 ms |
| 8 | 0.38 ms |
| 16 | 0.72 ms |
| 32 | 1.47 ms mean, 2.61 ms at the 99th percentile, 3.03 ms worst |

It grows with the channels. The transforms are constant, as 05 says, but
the filter's blend, the ITD ramp and the windows are numpy calls per
channel, which is the risk the plan named. The margin is wide, so nothing
is batched yet. 05's *Cost estimate*, which said under a millisecond, is
corrected, and phase 9 measures it with the UI running.

The crossfade, A against B: a band-limited 440 Hz sawtooth orbiting at
1 rev/s has block-rate sidebands at −75.9 dB crossfaded and −43.7 dB
without, a cut of 32.2 dB. S0 measured 33.7, and the line is 20.

Nothing is kept with 32 spatial channels moving by `POSITION` every block
and one bypassed beside them, and the worst block raises the peak by
1692 bytes, under the 2048 line. The measure needs two warm-up cycles, not
one: CPython's float freelist grew by 32 bytes once, at block 132 of 800.

D-122 was found here, by measuring: numpy 2's `rfft` with the default norm
ran float32 input through its float64 loop, 789 KB a block despite `out=`.

Found by the sweep: `Lookup` read its cube map's resolution from the module
constant at query time, so an index built at another resolution would
index past its own cell table. A cached index read after the constant
changed would have done it, and so would a test's patched one. The index
now stores its resolution, `assemble()` refuses cells that do not fit it,
and the bank's cache records it. The cache's `FORMAT` is 2, so a phase 4
entry reads as a miss and is rebuilt once, in about 6.4 s.

Found while closing: `test_weighing_a_block_of_32_makes_no_array` failed
about one run in 18 under `-n 8`, keeping 426 bytes. tracemalloc traces the
whole process, and the bytes were PySide6's signature loader, woken by an
earlier Qt test in the same worker, and xdist's message read, not the
lookup's. It measures in an interpreter of its own now, as `test_realtime`
does. And the swap's half of the seek-or-swap acceptance had no test. It
has one now, measured against engines that never swapped, and it catches
a new space that does not start fresh and a tail not carried across.

Twenty-one mutations, all caught: the plan's fifteen, two in the feed, two
in the lookup's resolution and two at the swap. The phase adds 21 tests;
the suite is 2347.
