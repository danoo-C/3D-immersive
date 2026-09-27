# Stereo placement: a stereo channel as two sources

**Status:** agreed, and being built as [M4 phase 9](../../m4_binaural_engine/phase_9_stereo_placement.md) · **Written:** 2026-09-27 · **Asked for:** by
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

## Open, to settle when it is planned

- **What a split side sounds like at the listener.** Inside the minimum
  distance a source fades to its flat self (D-130), which today is the
  signal to both ears. For a split pair, the left side's flat self could be
  the left ear alone, and the right side's the right ear alone. Then a
  linked pair at the listener is exactly the stem as mixed, as bypass plays
  it, and moving the sides outward places it. That would also give the
  default its "left is left, right is right" at (0, 0, 0) without a
  position of its own. Recommended.
- **The level of a mono stem made into two sources.** Two copies of one
  signal add up differently depending on how close their points are. The
  rule should keep level as mixed: the pair as loud as the stem played flat.
  The likely answer is each copy at half amplitude, so the pair collapsed
  to one point is exactly the single point. It is to be measured when
  built.
- **The default spread**, in metres: set by ear.
- **The fold correction** (D-129) does not apply to a split channel, since
  nothing is folded. Each side is calibrated as a source of its own.
- **Cost.** A split channel is two sources. From the measured 44 µs per
  source, 32 split stereo channels would take about 2.8 ms a block, against
  10.67 ms. The benchmark's "32 sources" should then count sources, not
  channels.
- **Where it goes.** Since the engine comes first, it fits as an M4 phase
  before the benchmark, so the benchmark measures it. The other place is
  the first phase of M5. The views then draw two linked points per channel
  (M5), and automation animates the leading position and the link (M6).
- **The pane**: both sides' X, Y and Z, the mode, the three axis choices
  and the pivot, following the pane's rules for several channels.
