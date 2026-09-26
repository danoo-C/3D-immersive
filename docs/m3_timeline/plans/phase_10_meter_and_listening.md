# Plan — M3 · Phase 10 — The master meter, and the arrangement heard

**Written:** 2026-09-26 · **Status:** built — waiting to be heard

## Approach

One meter, drawn in two places, from peaks the engine already half
publishes. Four layers, each testable without the one above it.

**The engine: a peak per channel, beside the bus's.** `Engine.take_peaks()`
already hands the UI thread the bus's highest sample per side since the
last frame. Each `Snapshot` gains a `peaks` array, `(channels, 2)` of zeros,
made on the UI thread like everything else in it. In `_mix`, once a
channel's lane has had its gain applied (and so its mute and solo), the
engine raises that channel's two peaks with the same `abs`, `max` and
compare it uses for the bus, into the scratch row it already has.
`take_channel_peaks()` reads the current snapshot's array, zeros it, and
pairs each row with its lane's `channel_id`, so an edit that reorders
channels cannot hand one channel another's level. A block that lands between
the read and the reset is one frame of a meter, as 05 already says of the
bus. The zero-allocation test's cycle already mixes channels; it now takes
their peaks too.

**`ui/metering.py`: the ballistics, without Qt (D-118).** A `Ballistics` per
meter, fed a linear peak per side each frame, with a clock passed in:
- the bar rises at once and falls at 24 dB/s;
- the hold marks the highest level for 1.5 s, then falls at the same rate;
- the clip latch sets when a sample passes 1.0, and only `clear()` unsets it.

Levels are dBFS, floored at −60. It is tested by stepping the clock, which
is the phase's acceptance line about the hold.

**`ui/widgets/meter.py`: the widget.** A `Meter` draws a `Ballistics`,
horizontal or vertical, two bars side by side:
- the level in `meter.level`, and the part above −6 dBFS in `meter.hot`;
- the hold as a line in `meter.hold`;
- on the background `meter.background`;
- for the master only, a clip light at the end: `meter.clip` with a `!` in
  `meter.clip.text` when latched, cleared by a click.

`meter` is a painted group (D-92), and its keys are read with
`group_color()` when it paints, so a theme switch repaints it.

**The window: two places.** The master meter sits in the status bar between
the xrun counter and the notice count, 04's order. Each `ChannelHeader`
gets a vertical meter at its right edge, with no clip light. The window's
30 Hz `tick` feeds both:
- the bus's peaks to the master;
- each channel's peaks to its header, found by channel id;
- zeros to any header the snapshot does not hold yet, so every meter falls
  when nothing plays.

Without an output there is no tick, and the meters stay empty.

The alternative for the channel meters was having the timeline panel poll
the engine itself. It was rejected because the window already owns the one
look at the audio thread per frame, and two lookers would take the peaks
from each other.

## Decisions settled here

**Channel meters exist, and what they measure (D-117).** A channel's
contribution to the bus, after its gain, mute and solo, and from M4 before
the HRTF. No clip light on a channel; the master is the one.

**How meters move (D-118).** −60 to 0 dBFS in dB, instant rise, a fall of
24 dB/s, a 1.5 s hold, *hot* above −6 dBFS, and a latch above 1.0 marked
`!` and cleared by a click.

## Steps

1. **Channel peaks from the engine.** `Snapshot.peaks`, the channel peaks in
   `_mix`, and `take_channel_peaks()`. Tests:
   - a channel at a known level and gain reads that level, and a muted one
     reads 0;
   - two channels read their own, by id, and still do after a reorder;
   - taking resets;
   - stopped, nothing rises;
   - the zero-allocation test takes channel peaks each block and stays
     clean.
2. **Ballistics and the meter widget.** `ui/metering.py` and
   `ui/widgets/meter.py`, and the `meter` group in `04` and the bundled
   theme. Model tests, by a stepped clock:
   - instant rise, and a 24 dB/s fall;
   - the hold for 1.5 s, then falling;
   - a latch above 1.0 but not at it, until `clear()`.

   Widget tests:
   - a known level drawn at its length, −30 dBFS halfway;
   - the hot part coloured differently from the level below it;
   - the clip light's `!` when latched, and a click clears it;
   - no clip light unless asked for;
   - no hex.
3. **The master meter in the status bar**, fed by `tick`. Tests:
   - its place between the xruns and the notice count;
   - a stand-in playing a known level draws it;
   - a sample past full scale latches it, and a click clears it;
   - stopped, it falls.

   A screenshot of it holding a peak, and latched, looked at.
4. **The channel meters in the headers.** Tests:
   - a known level on one channel at a known gain draws there;
   - a muted channel falls to nothing;
   - a channel driven past full scale lights only the master's clip light;
   - a newly added channel's meter is fed, and falls.

   A screenshot of the person's 23 stems arranged and playing through the
   stand-in, meters at their different levels, looked at.
5. **Written down, closed.** Update `04` (*Master meter*, the channel
   header, the `meter` row), `05` (*Metering*) and `02` (`meter.py`,
   `metering.py`). Then the Notes and the Outcome. The listening box stays
   open for the person, with what to do written into the phase's Notes.

## Files

`src/immersive/audio/scheduler.py` — `Snapshot.peaks`
`src/immersive/audio/engine.py` — the channel peaks, `take_channel_peaks()`
`src/immersive/ui/metering.py` — new: `Ballistics`
`src/immersive/ui/widgets/meter.py` — new: `Meter`
`src/immersive/ui/timeline/headers.py` — a meter in each header
`src/immersive/ui/timeline/panel.py` — a channel's meter by id, if needed
`src/immersive/ui/main_window.py` — the master meter, feeding both in `tick`
`src/immersive/ui/theme.py` — `meter` in `PAINTED`
`src/immersive/assets/themes/vscode_dark.3dimtheme` — the `meter` group
`docs/02-architecture.md`, `docs/04-ui-spec.md`, `docs/05-audio-engine.md`
`tests/test_engine.py`, `tests/test_realtime.py`, `tests/test_theme.py` — extended
`tests/test_metering.py`, `tests/test_meter.py`, `tests/test_meters_in_the_window.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | a channel's peak taken before its gain | known level at a known gain; muted reads 0 |
| 2 | `take_channel_peaks()` does not reset | taking resets |
| 3 | peaks paired with channels by position, not id | two channels after a reorder |
| 4 | the bar falls at once | a 24 dB/s fall |
| 5 | the hold not held | the hold for 1.5 s |
| 6 | the hold held for ever | falling after 1.5 s |
| 7 | the latch at 1.0 rather than above it | a latch above 1.0 but not at it |
| 8 | the latch cleared by the next quiet frame | until `clear()` / until clicked |
| 9 | a channel meter given a clip light | no clip light unless asked for |
| 10 | the hot threshold elsewhere than −6 dBFS | the hot part coloured differently |
| 11 | the scale linear, not dB | −30 dBFS drawn halfway |
| 12 | the master meter placed after the notice count | its place in the status bar |
| 13 | meters fed only while playing | stopped, it falls |
| 14 | a header the snapshot lacks never fed | a new channel's meter falls |
| 15 | a literal colour in the meter | the no-hex test |
| 16 | a channel peak that allocates on the audio thread | the zero-allocation test |

## Risks and unknowns

- **Thirty-two headers repainting thirty times a second.** Each meter
  repaints only its own few pixels, and only when its bar or hold moved, so
  a silent channel costs nothing. Looked at with the 23 stems.
- **The header has little room.** A vertical strip of 7 px at its right
  edge takes that from the name, which is elided already. If it crowds the
  M/S/⊘ buttons the strip goes, rather than shrinking the buttons.
- **The audio thread's cost** is two `abs` and two `max` of one block per
  audible channel, beside a gain ramp that already touches every sample.
  The zero-allocation test holds the line, and the realtime cycle is where
  it would show.

## Out of scope for this plan

| Not here | Where |
|---|---|
| A limiter to keep the master out of the red | M4 (D-54) |
| Meters after the HRTF, per channel | never, by D-117's cost; M4 taps before it |
| RMS or loudness (LUFS) metering | not asked for; peaks answer "is it clipping" |
| A channel clip light | never, by D-117 |

## Outcome

Built as planned, all five steps, with no step reverted and no decision
reopened. The plan's approach held: the engine had most of the master's
peaks already, and adding the channels' took one array on the snapshot and
four lines in `_mix`. The zero-allocation test stayed clean with the peaks
taken every block.

The risks did not arrive. The header had room for a 9 px strip, since its
name was already elided. The 23 channels repainting at thirty frames a
second showed nothing a person would notice, offscreen, because a silent
channel's meter never repaints. That is a claim for native hardware too,
and the listening test is where to watch it.

What the plan got wrong was only in its tests. Every channel in them was
mono until a mutation showed it. And one spy, bound in a loop, watched the
wrong header, which only the linter saw.

What M4 needs: the channel peaks are raised after a lane's gain. When
distance attenuation joins the gain there, the meters follow it for
nothing. The HRTF comes after that point and must stay after it (D-117).
The master meter will show the limiter's work once D-54's limiter sits on
the bus.
