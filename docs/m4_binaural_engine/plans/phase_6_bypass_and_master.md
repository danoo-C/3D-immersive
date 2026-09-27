# Plan — M4 · Phase 6 — Bypass and the master bus

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

A bypassed channel already plays flat, its stereo kept, since phase 5 sends
only the other channels through the HRTF. This phase gives it its pan, and
puts a master stage between the bus and the output. The bus's order becomes:

1. every channel, flat or spatial, and the audition, summed as today;
2. the master gain, ramped;
3. the limiter: the bus delayed by the lookahead, and limited while it is
   on;
4. the master meter, then the output.

**Pan (D-125).** 05's pan law is for a mono clip and its balance for a
stereo one, and one channel can hold both. So the lane gains a third row.
`fill()` writes a mono clip into it once, and a stereo clip into the two
rows it already has. A channel's gain becomes four factors: mono to left,
mono to right, left, right. The UI thread works them out as it works out
the gain today, with mute and solo folded in:

- **bypassed**: the mono pair is `g·cos θ` and `g·sin θ` with
  `θ = (p + 1)·π/4`, and the stereo pair is `g·(1 − p)` on the left when
  `p > 0` and `g·(1 + p)` on the right when `p < 0`, else `g`;
- **anything else** (spatial, or flat for want of a bank): all four are
  `g`, so a mono clip still reaches both ears whole and the spatial mono
  point is what it was.

The engine combines the rows per channel before the channel's meter and the
bus: left is `left·sl + mono·ml`, right is `right·sr + mono·mr`, each factor
ramped across the block from where the last block left it. A spatial
channel then downmixes left and right to its point, as it does now. The
`GAIN` command carries the four factors, and the ring widens to seven
numbers.

**The master (D-126).** `Snapshot.master` holds the master gain as a factor
and the limiter's switch, built from `project.master`. A `MASTER` command,
tagged with the generation, changes both. The engine keeps the gain and the
switch as the last block left them, and ramps both to the snapshot's,
across a block. The switch ramps as a fade from the unlimited signal to the
limited one, or back.

**The limiter (D-123)**, in `audio/limiter.py`, a block at a time with no
array made:

1. the louder side's level, `20·log10` of the larger `|L|` or `|R|`;
2. the reduction each sample needs, from the soft knee: none below
   −1.3 dBFS, `(x + 1.3)² / 4` in the knee, and `x + 0.3` above its top
   at +0.7 dBFS, where `x` is the level in dBFS;
3. held forward over 73 samples, the sliding maximum by doubling;
4. released: `r = max(h, a·r_prev)` with `a = e^(−1/(0.05·48000))`, as a
   running maximum of `h·a^-n`, carried across blocks;
5. averaged over the last 72 samples, by running sums, which is the attack;
6. `10^(−r/20)` on the audio delayed by 72 samples.

The histories carried across a block are the 72 samples of audio, the 72
reductions still to be held, the 72 released values the average needs, and
the release's last value. None is reset at a seek or a swap: the limiter is
the output's, not the timeline's.

**The latency (D-124).** The delay runs whether the limiter is on or off,
so `Engine.latency` is always 72 frames and a switch moves nothing in time.
M7's render drops the first `latency` frames and plays `latency` more at
the end. Tests that read the engine's output sample for sample read it
through a helper that knows the latency.

## Decisions settled here

**D-123**: the limiter's algorithm: knee, hold, release, average, in
decibels of reduction, vectorised.

**D-124**: the lookahead is a stated, constant latency, not a graph running
ahead of its output. The phase's acceptance is amended to say so.

**D-125**: a channel's gain is four factors, and mono clips have a row of
their own.

**D-126**: the master gain and the switch travel as channel gains do, and
the audition passes through them.

## Steps

1. **Pan, and the master's gain.** The mono row, the four factors through
   `gains()`, the snapshot and the ring; `Snapshot.master` and `MASTER`; the
   feed sending both. Tests:
   - a bypassed stereo channel at centre is bit-identical to its samples at
     unity gain, with a bank installed, so it never met a transform;
   - a bypassed mono channel hard left is silent on the right, and centred
     it is −3.01 dB on each side;
   - a channel holding a mono clip and a stereo clip pans each by its own
     law;
   - a pan change ramps across one block;
   - pan does nothing to a channel that is not bypassed;
   - the master gain ramps across one block, and a stale `MASTER` is
     dropped;
   - the feed sends a pan edit and a master edit as commands, not
     snapshots.
2. **The limiter.** `audio/limiter.py`, then the engine's master stage and
   `Engine.latency`. Tests:
   - no sample passes −0.3 dBFS for hot noise, a sine at +6 dBFS, and a
     single-sample spike landing first in a block;
   - below the knee the output is the input delayed by exactly 72 samples,
     bit for bit;
   - the static curve at points below, in and above the knee;
   - a peak on one side reduces the other side equally;
   - after a peak, the reduction falls by `e` in 50 ms, across blocks;
   - the reduction begins 72 samples before the peak it is for;
   - the output is delayed by 72 samples with the limiter off as on;
   - a switch mid-signal ramps across a block;
   - off, a signal past full scale passes untouched and the master meter
     latches; on, the meter reads after the limiter;
   - the audition is limited too;
   - master gain before the limiter: +12 dB of gain still meets the
     ceiling.
3. **Measured.** The zero-allocation test with bypassed mono and stereo
   channels panning, the master gain moving and the limiter working on
   every block. The limiter's block time recorded.

## Files

`src/immersive/audio/limiter.py` — new: the limiter
`src/immersive/audio/engine.py` — the mono row, four factors, `MASTER`,
the master stage, `latency`
`src/immersive/audio/scheduler.py` — `fill()`'s mono row, `gains()`'s four
factors, `Snapshot.master`
`src/immersive/audio/feed.py` — pan and master edits as commands
`tests/test_limiter.py` — new; `tests/test_engine.py`,
`tests/test_scheduler.py`, `tests/test_feed.py`, `tests/test_spatial.py`,
`tests/test_realtime.py` — extended, and read through the latency

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the pan law linear, not constant power | centred mono at −3.01 dB |
| 2 | a stereo clip panned by the mono law | centred stereo bit-identical |
| 3 | the mono row dropped from a bypassed channel | hard left silent on the right |
| 4 | pan applied to a channel that is not bypassed | pan does nothing there |
| 5 | the four factors stepped, not ramped | a pan change ramps |
| 6 | the master gain stepped, not ramped | the master gain ramps |
| 7 | a stale `MASTER` applied | dropped when stale |
| 8 | the master gain after the limiter | +12 dB still meets the ceiling |
| 9 | no hold (a window of 1) | no sample passes, for noise and the spike |
| 10 | the average over fewer samples than the hold | no sample passes |
| 11 | the release instant | the reduction falls by `e` in 50 ms |
| 12 | the release not carried across a block | the same, across blocks |
| 13 | a hard knee | the static curve in the knee |
| 14 | each side detected alone | a peak on one side reduces both |
| 15 | the delay only while the limiter is on | delayed alike off and on |
| 16 | the switch stepped | a switch ramps |
| 17 | the meter read before the limiter | the meter reads after it |
| 18 | the audition summed after the master stage | the audition is limited |
| 19 | the ceiling without its rounding margin | no sample passes |

## Risks and unknowns

- **Every test that reads the engine's output sample for sample moves by
  72 samples.** That is most of `test_engine.py` and `test_spatial.py`. They
  read through one helper that drops the latency, as M7's render will, so
  the expectations stay as they are rather than each being shifted by hand.
- **The allocation traps are numpy's**, found while planning: `np.clip` with
  Python bounds keeps memory, and `np.cumsum` and a mixed-dtype ufunc
  allocate behind `out=`. The limiter avoids them, and its own test measures
  it in a fresh interpreter, as `test_realtime` does.
- **The limiter's cost** was 34 µs a block at 512 frames in the prototype.
  It runs every block, playing or not, since the audition and the spatial
  tail pass through it.

## Out of scope for this plan

| Not here | Where |
|---|---|
| The pan, master gain and limiter fields | phase 7 |
| A per-channel delay to align bypassed channels with spatial ones | not in v1 (05, *Time alignment caveat*) |
| The render dropping the latency | M7 |
| Inter-sample peaks, oversampling | not in v1: the −0.3 dB ceiling is 05's answer |

## Outcome

Built as planned, in two steps and a measurement. The four decisions held.
The first port of the prototype got the knee wrong: it started 2 dB under the
ceiling instead of 1, and took the excess from the ceiling instead of from
the knee's top, so it limited at −1.3 dBFS. The static-curve test caught it on
its first run.

The named mutations were all caught, though not all by the test named for
them:

- **An average shorter than the hold (10)** is still brickwall. A window
  inside the hold's still covers the peak. What it breaks is the attack, and
  the test that the reduction begins 72 samples before its peak caught it.
  An average scaled wrong, at half the reduction, is what the ceiling tests
  catch.
- **"Each side detected alone" (14)** became "only the left side detected".
  The test was first written with its peak on the left, where that passes,
  so it now runs a peak on each side.
- Six more were caught, 25 in all: the master ramping in from unity on a
  project's first snapshot, the feed never sending the master, a looped fill
  not cleared, an average at half the reduction, and the hold's and the
  delay's histories dropped at a block's end.

The risk the plan named was the size of it: 80 tests read the engine's
output sample for sample and moved by 72 samples. They now read through
`tests/hearing.py`. A test plays first and reads after, on the timeline, and
a read plays on as far as the latency holds back. The graph's and the spatial
path's tests run with the limiter off, since they are about what reaches it.
The stand-in's ramp stays under half scale.

What phase 7 needs: the pane's fields only have to push their edits. A pan
edit is a gain command (D-125). A master gain or limiter edit is a `MASTER`
command (D-126). A position is a `POSITION` (D-121). A bypass, or a rolloff,
rebuilds the snapshot. The feed already tells each apart, and each is heard
at the next block, 72 frames late like everything else.
