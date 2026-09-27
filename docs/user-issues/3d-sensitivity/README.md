# Why a centimetre can swing a sound from one ear to the other

**Status:** explained; nothing changed · **Written:** 2026-09-27 ·
**Measured at:** `ade00a9` on `m3-timeline`, through SADIE II D1

**Reported:** Position X at −0.01 sounds hard left and at +0.01 hard right.
The fields are very sensitive: a small change in the numbers makes a huge
difference in the sound.

## The short answer

Nothing is broken. The channel is sitting **inside your head**.

A new channel starts at position (0, 0, 0), which is where the listener is.
There, a source has no direction of its own. Any X at all, however small,
puts it exactly to one side. Its sign alone decides which side: +0.01 is due
right, −0.01 is due left, and +0.001 is the same due right as +1000 would be.
A source at your own position is also as close as a source can be, so it is
at its loudest, and every centimetre changes its level the most.

Move the channel away from you first, for example Y = 2, two metres in
front. Then X = 0.01 is a shift of under a third of a degree, which you will
not hear.

## Why: the engine hears a direction, and a direction is a ratio

The engine places a source by two things, computed from its X, Y and Z every
block (05, *Per-block processing*; D-121):

- **Its direction**, the position divided by its distance from you:
  `(x, y, z) / r`, where `r = √(x² + y² + z²)`. The HRTF filter is chosen by
  this direction alone.
- **Its distance**, `r`, which sets a gain and nothing else (D-21).

A direction is a ratio, and a ratio of small numbers swings wildly. The
angle to the side is `atan2(x, y)`, with you at the origin facing +Y (03):

| X | Y | Angle | What moving X by 1 cm does |
|---|---|---|---|
| +0.01 | 0 | 90° right | crosses to 90° left, through you |
| +0.01 | 0.1 | 5.7° right | about 6° |
| +0.01 | 1 | 0.6° right | about half a degree |
| +0.01 | 10 | 0.06° right | nothing |

It is the same geometry as a real room. A fly at the tip of your nose moving
two centimetres goes from one ear to the other. A bird ten metres away
moving two centimetres does not move at all. The fields show metres, so they
treat every centimetre alike, but your ears do not.

**At exactly (0, 0, 0) there is no direction at all**, since `(0, 0, 0) / 0`
is undefined. The engine calls it straight ahead. So stepping X from −0.01
through 0 to +0.01 goes hard left, then centre, then hard right.

## Why "hard": the side is as extreme as hearing gets

Due left or due right is where a real head makes the most difference between
the ears, and SADIE II D1 is measurements of a real head. Measured through
the engine, white noise, levels relative to one metre straight ahead:

| Position (X, Y, Z) | Angle | Left | Right | Right − left | Delay between ears |
|---|---|---|---|---|---|
| (0, 0, 0) | "ahead" | +13.4 dB | +14.5 dB | +1.1 dB | 0 |
| (+0.01, 0, 0) | 90° right | +1.5 dB | +17.6 dB | **+16.1 dB** | **0.9 ms**, right first |
| (−0.01, 0, 0) | 90° left | +17.9 dB | +2.2 dB | **−15.7 dB** | **0.9 ms**, left first |
| (+0.001, 0, 0) | 90° right | +1.5 dB | +17.6 dB | +16.1 dB | 0.9 ms |
| (+0.01, 1, 0) | 0.6° right | −0.7 dB | +0.6 dB | +1.4 dB | 0.02 ms |
| (+0.1, 1, 0) | 5.7° right | −2.5 dB | +2.0 dB | +4.5 dB | 0.06 ms |
| (+0.5, 1, 0) | 26.6° right | −9.0 dB | +2.6 dB | +11.6 dB | 0.3 ms |
| (+1, 1, 0) | 45° right | −14.4 dB | +0.7 dB | +15.2 dB | 0.5 ms |

About 16 dB between the ears and nearly a millisecond of delay is what your
brain reads as "right beside me". A pan pot turned all the way sounds much
the same.

The rows for +0.01 and +0.001 are identical: at Y = 0 the size of X does not
matter, only its sign. And (+0.1, 0.1, 0) sounds from the same 45° as
(+1, 1, 0), because it is the same direction. It is only louder, because it
is nearer.

## Why so loud, and why the level jumps too

Level follows distance: `(1 m / r) ^ rolloff`, which with rolloff 1 is 6 dB
more at half the distance. Near you, the steps are the steepest:

| Distance | Level against 1 m |
|---|---|
| 0.2 m or nearer | **+14 dB**, held there |
| 0.5 m | +6 dB |
| 1 m | 0 dB |
| 2 m | −6 dB |
| 4 m | −12 dB |

The engine stops the rise at `min_distance`, 0.2 m, so that a source dragged
onto your head does not become infinitely loud (03, *Coordinate system*). Every
position closer than 20 cm, (0, 0, 0) included, is therefore about 14 dB
louder than the same sound one metre away. That is nearly five times the
amplitude, so a loud channel there can also reach the master limiter. Moving
from 0.2 m to 0.4 m costs 6 dB, where moving from 2 m to 2.2 m costs less
than 1 dB.

So near the origin, both the direction and the level change the most per
centimetre, and the fields start a new channel right there.

## One more small thing: the field's drag step

Dragging a position field moves it 0.01 m per pixel. Starting from 0 with Y
and Z at 0, one pixel is enough to cross from one ear to the other.

## What to do today

Think of X and Y as a floor plan, with you in the middle facing up the page
(+Y), and keep sources a metre or more away:

| To put it… | Type |
|---|---|
| in front | X 0, Y 2 |
| to the right | X 2, Y 0 |
| to the left | X −2, Y 0 |
| behind | X 0, Y −2 |
| front right, 45° | X 1.4, Y 1.4 |
| above | raise Z: Z 1 with Y 2 is about 27° up |

Set the distance first (Y), then move the direction (X). At two metres a
centimetre of X is under a third of a degree.

## Straight ahead is 1.1 dB louder on the right

The first row of the table shows a small lean to the right even straight
ahead. That is in the data. SADIE II D1's own measurement at 0° has the right
ear 1.11 dB louder than the left, and at 45° the right side's difference
between the ears is 1.8 dB larger than the left side's. That is the measured
head's own asymmetry. The engine reproduces it
exactly: a symmetric synthetic head comes out even in both ears in the tests.
Which set is the default is to be decided by listening (QA-30), and this lean
is a fair thing to listen for.

## What could change (none of it is done)

1. **Start new channels in front of you**, say at (0, 2, 0), not at the
   listener. It is a one-line change and removes the trap for every new
   channel. Positions already in a project stay where they are.
2. **Soften the middle.** Inside `min_distance`, fade the direction towards a
   centred sound, so that passing through the listener is a smooth pass
   through the middle rather than a flip from ear to ear. Real heads do have
   near-field effects the engine does not model, since the HRTF was measured
   at one distance, but this would be a design choice, not physics. It needs
   a decision and a listening check.
3. **Place by angle and distance.** Offer azimuth, elevation and metres
   alongside X, Y and Z. 04 asks for X, Y and Z, and the top and front views
   (M5) are meant to be the main way to place a source, where you can see
   how near it is to your head.
4. **A drag step that grows with distance**, so that dragging near the head
   is finer.

The first is the cheapest and would have prevented this report. The second
matters most once the M5 views make it easy to drag a source through your
head by accident.

## How this was measured

White noise at −26 dBFS on one channel, rendered at 512 frames through
SADIE II D1 with the limiter off. Levels are the RMS of each ear over 50
blocks, relative to the average of both ears with the source one metre
straight ahead. The delay between the ears is the lag of the peak of their
cross-correlation, in samples at 48 kHz. The raw-data figures are the energy
of SADIE's own measurements at those directions, before the engine.
