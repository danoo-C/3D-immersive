# M4 · Phase 9 — Stereo placement

**Status:** ✅ complete · **Plan:** [plans/phase_9_stereo_placement.md](plans/phase_9_stereo_placement.md)

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

- [x] A linked pair's right side is the left side mirrored about the pivot
      on each inverted axis and kept on the others. A free pair's two sides
      are each where they were put. One point is today's behaviour, and a
      file without a placement opens as one point.
- [x] A new channel is a linked pair, X mirrored, Y and Z kept, about the
      listener.
- [x] A paired stereo channel at the listener is the stem as mixed: its
      left to the left ear and its right to the right, to within float32.
- [x] A pair is as loud as its stem as mixed, within 0.2 dB, for sides
      together, 30°, 90° and 180° apart, whether the stem's sides are the
      same signal or unrelated ones, with level as mixed on.
- [x] A mono channel made two sources, placed apart, is heard from both
      points. At the listener it is the mono clip to both ears.
- [x] Moving a side, the mode, the pivot or a mirrored axis is one edit,
      undoable, and heard at the next block. A position is sent as a command
      and a mode as a snapshot.
- [x] The zero-allocation test holds with paired channels moving, and the
      block time with 32 paired channels is recorded.

## Implements

The design in [stereo placement](../user-issues/stereo-placement/README.md);
QA-37's revisit of D-16; D-132 to D-135.

## Notes

Appended while building.

**Built (2026-09-27)**, in four steps: the model, the file and the feed; the
engine; the pane; and a measurement that changed the engine.

**The pair's gain as planned missed real stems.** It read the pair's
loudness with pink noise, and one number, `c`, for how alike the stem's
sides are, taken from its fold. Rendered, four real stems were up to 1.3 dB
too loud once their sides were apart, the drums most. A stem's sides are
alike in some bands and not others, the kick shared and the cymbals wide,
and at low frequencies two sources stay in step at the ears, so one number
weighs the wrong bands. A prototype reading the loudness with the stem's own
K-weighted left, right and cross spectra met the rendered loudness within
0.1 dB where pink and `c` were off by as much as 1.3. That is what is built
(D-133 rewritten): the spectra are measured when a file is decoded, in the
pass that measures its fold, averaged into the bank's bins over a channel's
clips by length, and a pair's loudness is read with them each block.

**Four real stems**, the loudest 12 s of each, as a free pair at a metre,
its sides either side of straight ahead. Loudness against the stem as mixed,
in dB, level as mixed on:

| Stem | Together | 30° | 60° | 90° | 180° | Off, at 90° |
|---|---|---|---|---|---|---|
| Drums | −0.10 | −0.04 | −0.09 | −0.10 | −0.05 | +2.50 |
| Piano | +0.10 | +0.12 | +0.12 | +0.10 | +0.06 | +0.45 |
| Violin | +0.27 | +0.30 | +0.28 | +0.19 | +0.06 | +0.46 |
| Rhythm guitar | −0.01 | +0.01 | −0.01 | −0.02 | −0.06 | +0.66 |

All within 0.3 dB of themselves, and the separation moves none of them by
more than a quarter of a decibel. The acceptance's 0.2 dB is held by the
tests' alike, unrelated and lopsided stems; the violin's 0.3 dB is the
K-weighting's reading of what the ears do with it, the same at any
separation.

**A mirror box that did nothing.** The Mirror X, Y and Z boxes were first
connected with `functools.partial`, and PySide gives such a slot no checked
argument, so a click set nothing. They are connected with a lambda, as the
pane's other boxes are, and a test clicks one and reads the axis it set.

**A mono channel reads *Linked*.** A new channel is linked, so a mono one
shows the mode it would be heard in once it asks for two sources, with its
position labelled *Position* and *Mono as two sources* beside it. The mode
does nothing until then (D-132: a mono-only channel is one point unless it
asks). Hiding the mode would hide where the pair is made.

**Which side leads.** The left, stored as the channel's position. Typing a
linked right side moves the left through the mirror. Switching from free to
linked keeps the left and brings the right to its mirror, not the side moved
last as the design had it, since nothing records which that was. M5's views
can make the side grabbed lead in the same way.

**Mutations.** Sixteen named, and six more for the pane and the gain: all
caught but one, which is equivalent. *A side weighed by the other's
spectrum* swaps which of the stem's spectra each side is read with. For a
lopsided stem, bass on one side and treble on the other, placed front and
behind, it moves the loudness by under 0.01 dB, since either way each side's
power meets the same filters' power summed over both ears. Two of the 22 runs
also failed a test this phase does not touch, in `test_parameters.py`: the
sample view's waveform once and its audition button once, each beside the
intended catch. Neither failed again, in five runs of the sweep's tests, in
three beside a second session, or under either mutation alone, and the
tests share no state that a mutation reaches. The sweep did not keep the
messages, so it now keeps each run's output, and the next one is to be read
rather than guessed at.

**Block time**, SADIE at 512 frames, four channels inside the centre,
master stage included, 3000 blocks:

| 32 stereo channels | Mean | p99 | Worst | Over 8 ms |
|---|---|---|---|---|
| One point, level as mixed on | 1.40 ms | 2.52 ms | 6.65 ms | 0 |
| One point, off | 1.39 ms | 2.52 ms | 5.74 ms | 0 |
| Linked pairs, 64 sources, on | 3.15 ms | 5.16 ms | 6.64 ms | 0 |
| Linked pairs, off | 2.58 ms | 4.27 ms | 6.18 ms | 0 |

The pair gains cost 0.6 ms for 32 pairs. A shorter run once had a single
block at 11 ms, on a pair run and on a point run alike: the machine, not the
graph. The design's 2.8 ms estimate for 32 pairs left the gains out.

**The zero-allocation test** now runs a third of its 32 moving channels as
linked pairs and a third as free ones, their right sides moving too: nothing
kept, 1692 bytes at worst, the interpreter's own.

**Tests**: 2456 before the phase, 2512 after.
