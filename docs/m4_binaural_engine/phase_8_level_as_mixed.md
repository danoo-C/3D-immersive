# M4 · Phase 8 — Level as mixed

**Status:** planned · **Plan:** [plans/phase_8_level_as_mixed.md](plans/phase_8_level_as_mixed.md)

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

- [ ] Pink noise one metre straight ahead is as loud as the same noise
      played flat, within 0.1 dB, weighted as BS.1770 weights loudness over
      both ears. That holds for SADIE II D1 and the synthetic head alike.
- [ ] With the switch on, a placed channel nearer than the full-level
      distance, in any measured direction, is as loud as it is straight
      ahead, within 0.1 dB. Past it, the level falls by `rolloff × 6.02` dB
      for each doubling of the distance. The difference between the ears,
      and the delay between them, are the set's own.
- [ ] With the switch off, the distance law is D-21's, and each direction
      is as loud as the calibrated set makes it.
- [ ] A placed stereo file's mono point is as loud as the file played flat,
      within 0.1 dB, when folding loses up to 6 dB. More than that is given
      back 6 dB. A mono file and a bypassed channel are untouched.
- [ ] At (0, 0, 0) a placed channel is its flat self to both ears, with no
      filter and no delay between the ears. Moving out to the minimum
      distance, it becomes the placed source continuously, so X at −0.01 and
      +0.01 differ by less than 1 dB between the ears, not by the set's
      full side-to-side difference.
- [ ] The switch is one edit in the project view, heard at the next block,
      and on in new projects and in files written before it existed.
- [ ] The drum stem that distorted at (0, 0, 0), from `test-samples/`, is
      measured again. With the switch on, its peaks are within 1 dB of its
      own, and it is recorded in the Notes.
- [ ] The zero-allocation test holds with a channel inside the centre and
      the switch on.

## Implements

The design in [level as mixed](../user-issues/3d-sensitivity/level-as-mixed.md);
D-128 to D-131, which amend D-21 and D-16. *Per-block processing* and *The
HRTF pipeline* in [05-audio-engine.md](../05-audio-engine.md); `Distance` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
