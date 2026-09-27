# Plan — M4 · Phase 8 — Level as mixed

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

Four corrections, all worked out before a block plays (D-128). A block does
the same work it does now, except for a channel inside the centre.

**Loudness** is one small module in `core/io/loudness.py`, since both the
decoder (core) and the bank (audio) need it. It holds BS.1770's two K-weighting
biquads at 48 kHz, a K-weighted power of a signal in the time domain, and the
weighting's response at any frequencies, so a filter's loudness to pink noise
can be read straight from its spectrum.

**The calibration (D-128)** happens in `bank.prepare`, after the transform. Each
direction's pink-noise loudness is read from its two filters' spectra, and
compared with flat's, which is a response of 1 in every bin to both ears. The
filters are scaled so the direction nearest straight ahead matches flat. The
factor is kept on the `Bank`, as `calibration`, in dB. Each direction's
loudness against the front's becomes `Bank.evening`, `[M]`, the gain that
makes it the front's. None of this is cached: it is the transform's to do, a
few tens of milliseconds, and cached it would be one more thing to
invalidate.

**The fold (D-129)** happens in `decode`: for a stereo file,
`sqrt(((P_L + P_R) / 2) / P_M)`, capped at 2, as `Decoded.fold`, 1 by default.
`build` multiplies a stereo clip's gain by it on a spatial channel only.

**The centre (D-130)** is in `Space`. `_placed` also returns how far into the
centre a source is, `w = min(r / min_distance, 1)`. When `w < 1`, `_filter`
blends each ear's filter towards 1 and scales the delay by `w`. At the origin
the direction is still called straight ahead, but at `w = 0` the direction no
longer matters.

**The switch (D-131)** is `Distance.keep_level`, read and written as the
other distance settings are. Absent, it reads as true. The feed already
treats the distance settings as structure, so a toggle rebuilds the snapshot.
`Space` takes it at build:

- the distance gain is `min(1, (ref / r) ^ rolloff)` when on;
- when on, a second weights array, `loudness = weights · evening[vertices]`,
  is what `_filter` blends with. `Lookup.blend` of the ITD keeps the plain
  weights.

The project view gains a *Level as mixed* check box under the limiter, one
edit, and it names what it does in its tooltip.

## Decisions settled here

**D-128**: loudness by BS.1770, the set calibrated to flat straight ahead,
fixed.
**D-129**: a placed stereo clip given back its fold loss, per file, capped at
+6 dB.
**D-130**: the centre fades to flat inside the minimum distance.
**D-131**: the switch, on by default: no near boost, and the same loudness
in every direction.

## Steps

1. **Loudness, and the set calibrated.** `core/io/loudness.py`; `Bank`'s
   `calibration` and `evening`. Tests:
   - the K-weighting is BS.1770's: its response at 1 kHz, its shelf, and a
     997 Hz sine's loudness;
   - pink noise straight ahead, through the engine, is as loud as flat
     within 0.1 dB, for the synthetic head and, where it is fetched, SADIE;
   - `evening` is 1 straight ahead, and each direction's loudness times its
     gain is the front's.
2. **The fold.** `Decoded.fold`, and `build` applying it. Tests:
   - a stereo file of two unrelated sides, placed, is as loud as played flat
     within 0.1 dB;
   - one whose sides are opposite gets exactly +6 dB;
   - a mono file's fold is 1, and a bypassed stereo channel is still
     bit-identical.
3. **The centre, and the switch.** `Space`, `Distance.keep_level`, the file,
   the pane. Tests:
   - at (0, 0, 0) the output is the channel played flat, to float32;
   - X at ±0.01 differs between the ears by under 1 dB, and at ±0.2 by the
     set's own difference;
   - moving from the centre to 0.3 m has no sample step past the crossfade's;
   - on: nearer than 1 m in any measured direction is as loud as straight
     ahead within 0.1 dB, and at 2 m and 4 m it is 6.02 and 12.04 dB down;
   - on: the delay between the ears is the set's, untouched by the gains;
   - off: phase 5's distance law and the direction's own loudness;
   - the switch is one edit, heard at the next block, and true when a file
     lacks it.
4. **Measured.** The drum stem at (0, 0, 0), on and off. The zero-allocation
   test with a channel in the centre and the switch on. Block time with 32
   sources, on.

## Files

`src/immersive/core/io/loudness.py` — new
`src/immersive/core/io/media.py` — `Decoded.fold`
`src/immersive/audio/hrtf/bank.py` — `calibration`, `evening`
`src/immersive/audio/spatial.py` — the centre, the switch
`src/immersive/audio/scheduler.py` — the fold on spatial channels
`src/immersive/core/model.py`, `src/immersive/core/io/project_io.py` —
`keep_level`
`src/immersive/audio/feed.py` — `keep_level` as structure
`src/immersive/ui/parameters/views.py` — the check box
`tests/test_loudness.py` — new; `tests/test_level_as_mixed.py` — new;
`tests/test_bank.py`, `tests/test_spatial.py`, `tests/test_realtime.py`,
`tests/test_project_io.py`, `tests/test_parameters.py` — extended where
calibration moves an expected number

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | no K-weighting (flat power) | the weighting's response; calibration within 0.1 dB |
| 2 | calibration not applied | pink ahead as loud as flat |
| 3 | calibrated to the first direction, not the front | pink ahead as loud as flat |
| 4 | `evening` not used with the switch on | every direction as loud as ahead |
| 5 | `evening` used with the switch off | off: the direction's own loudness |
| 6 | `evening` applied to the delay too | the delay is the set's |
| 7 | the near boost kept with the switch on | nearer than 1 m as loud as ahead |
| 8 | the near boost dropped with the switch off | off: phase 5's law |
| 9 | the fold not applied | two unrelated sides as loud as flat |
| 10 | the fold uncapped | opposite sides get +6 dB |
| 11 | the fold on a bypassed channel | bypassed stereo bit-identical |
| 12 | the centre's delay not scaled | ±0.01 under 1 dB between the ears |
| 13 | the centre's filter not blended | (0, 0, 0) is flat |
| 14 | the centre's width the reference, not the minimum | at ±0.2 the set's own difference |
| 15 | `keep_level` not read from the file | a file without it reads true, and one with false reads false |
| 16 | `keep_level` not structure to the feed | the switch heard at the next block |

## Risks and unknowns

- **Expected numbers move.** Phase 5's tests compare the engine with a
  direction's pair, and the pair is now calibrated. Those tests take
  `bank.calibration` into their expectation, and the ones about D-21's law
  switch level-as-mixed off, since they are about the law.
- **SADIE's front is not symmetric** (1.1 dB, the first report). Calibration
  matches the two ears' sum, so the lean stays, as it should: it is the set.
- **A mono stem bypassed at centre is 3 dB under flat**, by the pan law. It
  is recorded here and in the phase doc, and not changed.

## Out of scope for this plan

| Not here | Where |
|---|---|
| A 0 dB-centre pan law | D-125 stands |
| The full-level distance as a field | `ref_distance`, in the file, until asked for |
| The pane warning about a stem that folds badly | the design's note; not yet asked for |
| The benchmark | phase 10 |

## Outcome

Built as planned, in three steps and a measurement, with two changes the
building asked for:

- **Calibration uses the blend straight ahead**, not the nearest single
  measurement. It is the same for SADIE, which measured 0°, but the
  synthetic head has no measurement there. The nearest one's mutation also
  survived at first, because the synthetic head's pole is as loud as its
  front. A head louder in front now tells them apart.
- **Flat's share of the centre's delay is whole samples** (D-130 amended):
  the exact fractional delay rang, as the phase doc's Notes describe.

The fold was first built by filtering, which was eight times slower than
decoding. It is now read from spectra.

All sixteen named mutations were caught, the third only once the
front-heavy head was there to catch it. The drum stem that distorted at (0, 0, 0) now plays within half
a decibel of its own loudness, and does not reach the limiter there.

What the benchmark, now phase 10, needs: the graph as it ships. With the switch on, a block
costs what it did at phase 5, and the benchmark should run with it on,
since that is what a project has.
