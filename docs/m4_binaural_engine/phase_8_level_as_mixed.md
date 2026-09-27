# M4 · Phase 8 — Level as mixed

**Status:** ✅ complete · **Plan:** [plans/phase_8_level_as_mixed.md](plans/phase_8_level_as_mixed.md)

## Goal

A placed channel keeps the level it was mixed at. Wherever it is placed, it
is as loud as the same channel played flat, until it is farther away than
the full-level distance; past that, distance makes it quieter, as it does
now. Where it is still decides everything about direction. The design, and
the measurements it rests on, are in
[level as mixed](../user-issues/3d-sensitivity/level-as-mixed.md).

"Played flat" is how the engine plays a channel it does not place: a stereo
clip to its own sides and a mono clip to both ears, as a player plays a
file. A bypassed stereo channel at centre is exactly that. A bypassed mono
channel at centre is 3 dB under it, by the pan law (D-125).

## Scope

**In, always:** the HRTF set calibrated to flat straight ahead; a stereo
file's mono point given back what folding loses; the centre, where a source
inside the minimum distance fades to its flat self rather than flipping from
ear to ear.

**In, behind the project's switch:** no boost nearer than the full-level
distance, and the same loudness in every direction. The switch in the
project view, and in the project file, on unless a project says otherwise.

**Out:** a pan law with 0 dB at centre (D-125 stands). Choosing the
full-level distance in the pane: it is `ref_distance`, in the file. The
benchmark → phase 9.

## Acceptance

- [x] Pink noise one metre straight ahead is as loud as the same noise
      played flat, within 0.1 dB, weighted as BS.1770 weights loudness over
      both ears. That holds for SADIE II D1 and the synthetic head alike.
- [x] With the switch on, a placed channel nearer than the full-level
      distance, in any measured direction, is as loud as it is straight
      ahead, within 0.1 dB. Past it, the level falls by `rolloff × 6.02` dB
      for each doubling of the distance. The difference between the ears,
      and the delay between them, are the set's own.
- [x] With the switch off, the distance law is D-21's, and each direction
      is as loud as the calibrated set makes it.
- [x] A placed stereo file's mono point is as loud as the file played flat,
      within 0.1 dB, when folding loses up to 6 dB. More than that is given
      back 6 dB. A mono file and a bypassed channel are untouched.
- [x] At (0, 0, 0) a placed channel is its flat self to both ears, with no
      filter and no delay between the ears. Moving out to the minimum
      distance, it becomes the placed source continuously, so X at −0.01 and
      +0.01 differ by less than 1 dB between the ears, not by the set's
      full side-to-side difference.
- [x] The switch is one edit in the project view, heard at the next block,
      and on in new projects and in files written before it existed.
- [x] The drum stem that distorted at (0, 0, 0), from `test-samples/`, is
      measured again. With the switch on, its peaks are within 1 dB of its
      own, and it is recorded in the Notes.
- [x] The zero-allocation test holds with a channel inside the centre and
      the switch on.

## Implements

The design in [level as mixed](../user-issues/3d-sensitivity/level-as-mixed.md);
D-128 to D-131, which amend D-21 and D-16. *Per-block processing* and *The
HRTF pipeline* in [05-audio-engine.md](../05-audio-engine.md); `Distance` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Built (2026-09-27).** Four fixed corrections, none of them following the
signal. For SADIE II D1 the calibration is +4.99 dB, and `evening` runs from
−1.7 dB to +3.8 dB over its 8802 directions. Calibration uses the response
the engine plays straight ahead, the lookup's blend there. For SADIE that is
its own 0° measurement, but for the synthetic head, which has none, the
nearest single measurement would have missed.

**The drum stem that distorted**, `FEA2_DRUMS_2.wav`, 20 s from 116 s, whose
fold is +0.51 dB, now reads:

| Where | Peak | Loudness against the stem | Limiter |
|---|---|---|---|
| The stem, and bypassed | −0.34 dBFS | 0.00 dB | 0.2 dB, the knee |
| (0, 0, 0), on | −1.04 dBFS | −0.10 dB | nothing |
| 1 m ahead, on or off | −0.65 dBFS | −0.26 dB | 0.1 dB |
| 1 m to the right, on | +1.07 dBFS | −0.46 dB | 1.4 dB at most, over 1 dB for 0.1 % of the time |
| 2 m ahead, on | −6.67 dBFS | −6.28 dB | nothing |
| (0, 0, 0), off | +12.94 dBFS | +13.88 dB | 13.2 dB, over 1 dB for 75 % |

With the switch on, the stem stays within half a decibel of its own
loudness wherever it is placed. At its side it touches the limiter by
1.4 dB, which is the difference between the ears doing its work, as the
design said it would. With the switch off, (0, 0, 0) is louder than it was
before this phase: the set is now 5 dB hotter, and the distance law still
adds 14 dB there. That is the physical law as designed.

**Found by the continuity test: a centre that rang.** As first built, the
centre scaled the whole far-ear filter's ITD, flat share included. A source
standing still 1 cm to the side had a biggest sample-to-sample step of 0.024
on a tone where flat gives 0.0065. At 2 cm, where the delay came out a whole
3 samples, it was clean. A fractional delay of a response reaching up to
Nyquist is a sinc that rings through the whole transform and wraps. The
measured responses fall away near Nyquist and stay compact, so a source
moving along an arc at a metre did not ring. Flat's share of the delay is now
rounded to whole samples, and D-130 says so.

**The fold is read from spectra.** First written by filtering, it took
2.2 s for a three-minute stereo stem, to a decode of 0.34 s, which would
have made every import eight times slower. Read from 4096-frame spectra it
takes 0.2 s and agrees within 0.002 dB, on four stems from bass to one
partly out of phase. The filtered measure stays, as the reference a test
holds the fast one to.

**Block time**, 32 sources through SADIE at 512 frames, four of them inside
the centre, master stage included: 1.41 ms mean and 2.14 ms at the 99th
percentile with the switch on, 1.47 ms and 2.80 ms off. Phase 5's figure,
before the limiter, was 1.47 ms.

**Tests that moved.** Phase 5's impulse pair and distance law now switch
level-as-mixed off, since they are about the pair as measured and D-21's
own law. Inside the minimum distance the distance law's "no louder" is read
from the channel meter, since the filter now fades there. One sweep result
was a false catch: a mutation that deleted a line left an `if` with only a
comment under it, and the "caught" was a syntax error. The sweep now
reports a run with no failing test as broken.

**Known, and left as it is.** A mono channel bypassed at centre is 3 dB
under flat, by D-125's constant-power pan law. A stereo one is exactly
flat.

Seventeen mutations, all caught: the plan's sixteen, and flat's share
delayed fractionally, which the continuity test caught. The phase adds 44
tests; the suite is 2448.
