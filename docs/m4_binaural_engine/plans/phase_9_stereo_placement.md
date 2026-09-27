# Plan — M4 · Phase 9 — Stereo placement

**Written:** 2026-09-27 · **Status:** planned

## Approach

**The model (D-132).** `Placement` on each channel: `mode` (one point, free,
linked), `right`, `pivot`, `mirrored` (X, Y, Z), `mono`. `Channel.position`
stays the channel's point, and a pair's left side. Two functions in the
model answer everything else:

- `paired(channel, pool)`: whether it is heard as two sources, meaning its
  mode is not one point and it holds a stereo clip or asks for mono as two.
- `sides(channel)`: its two positions. Free is `right`; linked is the mirror
  of the left about the pivot.

`new_channel` makes a linked pair mirroring X. The project file writes the
placement on each channel, and reads a missing one as one point.

**Reaching the engine.** Each side's position travels as a position does now
(D-121). `POSITION` gains a side, 0 or 1, in the ring's seventh column, which
it left unused. The snapshot's `positions` become `(channels, 2, 3)`. The
feed sends each changed side. Whether a channel is paired is structure,
since it changes how many sources there are. The mode, the mono switch and
the clips are all in `structure()` already or join it. The pivot, the
mirrored axes and the right side only move positions, so they travel as
commands.

**The engine.** A paired channel is two slots in the `Space`, left then
right. The mix already combines each channel's rows into two sides before
anything else (D-125), and for a placed channel the four factors are its
gain. So a pair's left slot is the channel's left row and its right slot its
right, where one point averages them. `render` becomes two passes over the
slots:

1. directions, distance targets and reach; the lookup; the filters, with the
   centre's flat share on a side's own ear (D-134); then each pair's gain
   (D-133), from its two filters, into its two targets;
2. the ramped gains onto the rows, and the meters: a pair's left slot is its
   channel's left meter and its right slot the right.

**The pair's gain (D-133)** uses the pink weights' square roots, kept on the
`Space`: each filter times them, then `np.vdot`. Three shared loudnesses per
ear, contiguous and complex64, so nothing is made. `c` per channel comes
from `build`, out of its clips' folds, length-weighted.

**Where it is set (D-135).** The channel view gains a *Placement* section:

- **Mode**: *One point*, *Free*, *Linked*.
- **Left X, Y, Z**: `position`, labelled *Position X, Y, Z* when the channel
  is not a pair.
- **Right X, Y, Z**: free, its own; linked, derived, and typing there moves
  the left side through the mirror.
- **Pivot X, Y, Z** and **Mirror X, Y, Z**, for a linked pair.
- **Mono as two sources**.

A field is shown only where it means something. Several channels follow the
pane's rules: `—` where they differ, and a value set for all. The section is
greyed with its reason when every selected channel is bypassed (D-127).

## Decisions settled here

**D-132**: the placement in the model; `position` is the left side; linked
by the mirror formula; new channels a linked pair; old files one point.
**D-133**: a pair as loud as its stem at any separation, from the filters'
shared loudness and the stem's correlation; `1/√2` with level as mixed off.
**D-134**: in the centre, each side to its own ear.
**D-135**: where every spatial setting is set, now and when the views come.

## Steps

1. **The model, the file and the feed.** `Placement`, `paired`, `sides`,
   `new_channel`, the project file, and the feed sending each side through
   the ring's side column. Tests:
   - the mirror formula for each axis choice, about the listener and about
     a pivot, from either side;
   - free sides stay where they were put; one point has no second side;
   - a channel with only mono clips is not a pair unless it asks;
   - round trip, and a file without placement is one point;
   - a pivot, axis or right-side edit sends positions, and a mode edit
     sends a snapshot.
2. **The engine.** Paired slots, the two passes, the centre's own ear, and
   the pair's gain. Tests:
   - a pair at the listener is the stem as mixed, to float32;
   - a pair is as loud as the stem as mixed within 0.2 dB, at 0°, 30°, 90°
     and 180° apart, for alike and unrelated sides;
   - off, each side is at `1/√2`;
   - a mono channel as two sources is heard from both points;
   - each side is heard from where it is: left pulled to the left, right to
     the right;
   - a pair's meters read its two sides.
3. **The pane.** The Placement section. Tests:
   - each field is one edit, undoable;
   - typing a linked right side moves the left through the mirror;
   - the fields shown follow the mode and whether the channel is a pair;
   - several channels read `—` where they differ;
   - greyed when every channel is bypassed.
4. **Measured.** Loudness against separation for real stems, the
   zero-allocation test with pairs moving, and the block time for 32 pairs.

## Files

`src/immersive/core/model.py` — `Placement`, `paired`, `sides`
`src/immersive/core/io/project_io.py` — the placement in the file
`src/immersive/audio/engine.py` — `POSITION`'s side, pairs in `_mix`
`src/immersive/audio/scheduler.py` — positions per side, pairs, `c`
`src/immersive/audio/spatial.py` — pairs, the two passes, the pair's gain,
the centre's own ear
`src/immersive/audio/feed.py` — each side's position, pairing as structure
`src/immersive/ui/parameters/views.py` — the Placement section
`tests/test_stereo_placement.py` — new; `tests/test_model.py`,
`tests/test_project_io.py`, `tests/test_feed.py`, `tests/test_parameters.py`,
`tests/test_realtime.py` — extended

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the mirror inverting the wrong axis | the formula, each axis choice |
| 2 | the mirror about the listener, ignoring the pivot | the formula about a pivot |
| 3 | a mono-only channel paired without asking | not a pair unless it asks |
| 4 | placement not read from the file | round trip; a file without it is one point |
| 5 | a new channel one point | a new channel is a linked pair |
| 6 | `POSITION`'s side ignored | each side heard from where it is |
| 7 | a pivot edit sent as a snapshot | a pivot edit sends positions |
| 8 | the pair folded as one point | each side heard from where it is |
| 9 | the centre's flat share to both ears | the pair at the listener is the stem as mixed |
| 10 | no pair gain (sides at unity) | as loud as the stem, apart |
| 11 | the pair gain without its shared term | as loud as the stem, together |
| 12 | `c` taken as 0 | alike sides together |
| 13 | the pair gain applied with level as mixed off | off, `1/√2` |
| 14 | a pair's two meters one side | a pair's meters read its two sides |
| 15 | a stereo clip in a pair still folded | as loud as the stem, apart and unrelated |
| 16 | typing a linked right side moving nothing | typing the right moves the left |

## Risks and unknowns

- **The pair's gain is exact for pink noise.** Music is not pink, so the
  real stems' loudness against separation is measured in step 4, not
  assumed.
- **Shapes change.** `positions` gains a side axis, and `slots` a pairing.
  Tests that read `positions[channel]` follow it.
- **The pane grows.** That is why it gets a section, and why fields show only
  where they mean something.

## Out of scope for this plan

| Not here | Where |
|---|---|
| The two points in the views, dragging them and the pivot | M5 |
| Animating a side, the pivot or the axes | M6 |
| A per-clip placement | not asked for: a channel is the thing that is placed (D-6) |
| The benchmark | phase 10 |

## Outcome

Filled in at the end.
