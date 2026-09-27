# M4 · Phase 9 — Stereo placement

**Status:** planned · **Plan:** [plans/phase_9_stereo_placement.md](plans/phase_9_stereo_placement.md)

## Goal

A placed stereo channel can be heard as two sources, its left side and its
right side, each at its own position: freely, or linked in symmetry about a
pivot with each axis kept or mirrored. A mono channel can be made two
sources of the same signal. The engine, the model, the project file and the
parameters pane's numeric fields are built and tested here. The views that
draw the two points, and dragging them, come at M5, on this foundation. The
design, and what was agreed, are in
[stereo placement](../user-issues/stereo-placement/README.md).

## Scope

**In:** a channel's placement mode (one point, free, linked), its right
side, its pivot and its three mirrored axes, and mono as two sources, in the
model and the project file; each side's position reaching the engine as a
position does now; a paired channel as two spatial sources; a pair as loud
as its stem as mixed, at any separation; a pair at the listener heard as the
stem as mixed; the channel view's placement fields, and where every spatial
setting of this milestone is set.

**Out:** the views' points and dragging → M5. Animating either side or the
pivot → M6. The benchmark → phase 10.

## Acceptance

- [ ] A linked pair's right side is the left side mirrored about the pivot
      on each inverted axis and kept on the others. A free pair's two sides
      are each where they were put. One point is today's behaviour, and a
      file without a placement opens as one point.
- [ ] A new channel is a linked pair, X mirrored, Y and Z kept, about the
      listener.
- [ ] A paired stereo channel at the listener is the stem as mixed: its
      left to the left ear and its right to the right, to within float32.
- [ ] A pair is as loud as its stem as mixed, within 0.2 dB, for sides
      together, 30°, 90° and 180° apart, whether the stem's sides are the
      same signal or unrelated ones, with level as mixed on.
- [ ] A mono channel made two sources, placed apart, is heard from both
      points. At the listener it is the mono clip to both ears.
- [ ] Moving a side, the mode, the pivot or a mirrored axis is one edit,
      undoable, and heard at the next block. A position is sent as a command
      and a mode as a snapshot.
- [ ] The zero-allocation test holds with paired channels moving, and the
      block time with 32 paired channels is recorded.

## Implements

The design in [stereo placement](../user-issues/stereo-placement/README.md);
QA-37's revisit of D-16; D-132 to D-135.

## Notes

Appended while building.
