# Stereo placement: a stereo channel as two sources

**Status:** built in the engine and the parameters pane as [M4 phase 9](../../m4_binaural_engine/phase_9_stereo_placement.md), and heard; the views draw it at M5 · **Written:** 2026-09-27 · **Asked for:** by
the user, after hearing M4 phase 8

**Asked:** can a stereo stem's left and right each have their own 3D
position, so that the stereo image itself can be placed and animated? Either
fully separately, or in a symmetry mode where moving one side moves the
other, with a choice per axis of what is kept and what is inverted.

## Where it stands today

- A placed stereo channel is folded to **one point**, its two sides averaged
  (D-16), and since M4 phase 8 given back the loudness the folding loses
  (D-129).
- A **bypassed** stereo channel keeps its image intact, but is not placed at
  all.
- Two points with a width was considered when the spec was written, as good
  for pads and ambiences, and deferred: "downmix in v1, revisit after M5 when
  it is possible to hear what is missing" (QA-37). This is that revisit,
  brought forward.

The engine already keeps a channel's left and right apart until the moment
they are averaged. Its lane has a row per side (D-125), so splitting is a
change at the end of the path, not a new path.

## The feature

**Per channel** (D-6: a channel is the thing that has a position), a placed
channel is heard in one of three modes.

| Mode | What it is |
|---|---|
| **Single point** | Today's behaviour: the sides folded to one point, keeping their loudness. |
| **Independent** | The left and right sides are two sources, each with its own X, Y and Z, positioned and animated on its own. |
| **Linked** | Two sources, and moving either one moves the other in symmetry about a pivot point. |

As built, the pane names them *One point*, *Free* and *Linked*.

### The link

A linked pair has a **pivot point**, (0, 0, 0) by default, which is the
listener. For each of X, Y and Z the other side's coordinate is either:

- **kept**: the same offset from the pivot, so both sides move together on
  that axis; or
- **inverted**: the opposite offset from the pivot, so the two sides mirror
  each other across that axis.

As a formula: `follower = pivot + S · (leader − pivot)`, where `S` is +1 on
each kept axis and −1 on each inverted one.

With the pivot at the listener, facing +Y:

| X | Y | Z | The pair |
|---|---|---|---|
| inverted | kept | kept | the classic stereo pair, left and right of the listener |
| kept | inverted | kept | mirrored front and back |
| kept | kept | inverted | mirrored above and below ear level |
| inverted | inverted | kept | opposite each other diagonally, around the listener |
| inverted | inverted | inverted | opposite each other through the listener |
| kept | kept | kept | both sides at one point, as the folded point sounds |

Moving the pivot moves the centre of the symmetry. A wide pair centred 45° to
the right is its pivot placed there, with X inverted.

**Behaviour:**

- Whichever side you move leads, and the other follows. Only the leading
  side's position, the pivot and the three axis choices are stored and
  animated. The follower is always derived from them, so the pair can never
  drift apart.
- Switching from independent to linked snaps the follower to the mirror of
  the side moved last. Switching back to independent leaves both sides
  where they are, now free.
- Everything a placed source has, each side has: level as mixed (D-131),
  the centre (D-130), distance.

### Mono stems

A mono stem can be given the same treatment as an option: **two sources of
the same signal**, one at each point, positioned independently or linked
exactly as a stereo pair. Otherwise a mono clip stays a single point.

### The default for a new stereo channel

**Linked, X inverted, Y and Z kept, pivot at the listener, with a subtle
spread**: left is left, and right is right.

## Agreed on 2026-09-27

1. **The pivot** is selectable, and (0, 0, 0) by default.
2. **Mono stems** have the option of two sources of the same signal.
3. **Per channel**, not per clip.
4. **The default** for a new stereo channel is a subtle linked pair: X
   inverted, Y and Z kept.
5. **Engine first.** The model, the project file, the engine and the numeric
   fields in the parameters pane come first, and are working and tested
   before the graphical side, the head and the points in the views (M5), is
   built on them.

## Settled when it was built

Each open point from the design, and what M4 phase 9 did with it:

- **What a split side sounds like at the listener**: its own ear, as
  recommended (D-134). A pair at the listener is the stem as mixed, to
  within float32, and moving its sides out places them.
- **The level of a mono stem made into two sources**: the same rule as a
  stereo pair (D-133). Its sides are one signal, so together they are the
  single point, and apart the pair is still as loud as the stem. With level
  as mixed off, each copy is at `1/√2`.
- **The level of any pair.** A pair's loudness is read with the stem's own
  spectra, so widening an image keeps its level: four real stems stay within
  0.3 dB of themselves from together to 180° apart. The first plan, pink
  noise and one number for how alike the sides are, missed the drums by
  1.3 dB, and was replaced before it shipped.
- **The default spread**: none. A new channel is linked with its left at
  the listener, so both sides are there and it plays as the stem as mixed,
  left as left and right as right. Moving the left side out spreads it, and
  the right follows. How far is subtle is for the ear, and for M5's views to
  make easy.
- **Which side leads**: the left, stored as the channel's position (D-132).
  Typing a linked right side moves the left through the mirror, which comes
  to the same thing, since the mirror is its own inverse. Switching from
  free to linked keeps the left and brings the right to its mirror, not the
  side moved last, since nothing records which that was. When M5's views
  drag a side, the side grabbed can lead in the same way.
- **The fold correction** (D-129) does not apply to a pair, as expected.
- **Cost**: 32 paired stereo channels, 64 sources, take 3.2 ms a block on
  average and 5.2 ms at the 99th percentile, against 10.67 ms. The design's
  2.8 ms estimate did not include the pair's own gain, about 0.6 ms. Phase
  10's benchmark counts sources, and records 32 pairs beside them.
- **Where it went**: M4 phase 9, before the benchmark.
- **The pane**: a *Placement* section in the channel view, described with
  the table of where every spatial setting lives in
  [04-ui-spec](../../04-ui-spec.md#placement) (D-135).

## Heard

On 2026-09-27, by the user who asked for it, of the free mode's separate
control of the two sides: "really trippy, I love it."

## Still to come

- **The views** (M5): each pair drawn as two linked points, dragged, and the
  pivot with them.
- **Automation** (M6): the leading side, the free right side and the pivot
  animated. Today's automation keys are the channel's `pos.*`, `gain` and
  `pan` (03), so the right side's and the pivot's are added then.
