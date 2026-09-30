# Plan — M5 · Phase 5 — Measured with the views playing

**Written:** 2026-09-30 · **Status:** in progress

## Approach

**A `dragging` load for `contention`.** It drags as a hand does, through
the window's own path, not around it. Mouse events go to the top view: a
press on the second source's icon (the first is inside the centre), then
a move every 16 ms along a circle 2 m about the head, once round in 4 s,
and the release when the lap ends. So each movement goes through
`Placing` to the feed and the engine's ring, repaints the top and front
views, and refreshes the pane's fields for the channel the press
selected. The other 31 sources keep moving as in every lap, through the
engine alone (M4 phase 10's `_moving`). The load joins `LOADS`, so the
switch interval's table has a row for it, and `live --load dragging` is
there for phase 6 on the listening machine.

**The views' repaint cost.** A new `views` subcommand shows the window
with 32 sources, as points and then as linked pairs, and times a
synchronous `repaint()` of each view: the top, the front, the bypass
strip, the 3D view on its own tab, and the whole window, for comparison
with M4 phase 10's 55 ms. It counts the paint events each gets, so a view
timed while hidden, which paints nothing, cannot pass for a fast one.

**What the counts could ask.** If the 1 ms stream misses more than one
block in a thousand while dragging, or a view takes more than a frame at
60 Hz, 16.7 ms, the plan makes it cheaper before closing. The likely
place is the per-movement work in `Feed.preview` and the pane's refresh,
not the painting, which the views do at the event loop's pace.

## Decisions settled here

None expected. If the counts force a change, it is recorded here as the
next free D-number.

## Steps

1. **The load.** `_drag` in `benchmark.py`, and `dragging` in `LOADS`.
   Tests: the load presses on the second source, moves it while it runs,
   and makes one edit when it stops; nothing else is selected or moved.
2. **The repaint times.** `views()` and `run_views`. Tests: each view is
   timed as many times as asked, and painted each time.
3. **The runs.** `contention` with the new row, and `views`, recorded in
   the phase's Notes with the machine they ran on.
4. **The sweep and the close.**

## Files

`src/immersive/benchmark.py` — the load, `views`, `run_views`
`tests/test_benchmark.py` — extended

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the load moving the pointer without a press | it moves the source while it runs |
| 2 | the press on the first source, inside the centre | it presses on the second |
| 3 | no release at the end | one edit when it stops |
| 4 | the 3D view timed on its hidden tab | each view painted each time |
| 5 | a view timed fewer times than asked | timed as many times as asked |

## Risks and unknowns

- **Offscreen is not a screen.** Painting offscreen goes to an image, as
  M4 phase 10's `repainting` did. The listening machine's live run in
  phase 6 is the one with a real display.
- **This machine is not quiet.** Runs are taken with nothing else running,
  and three rounds each, in turn, as M4 phase 10's were.

## Out of scope for this plan

| Not here | Where |
|---|---|
| The live count, with a display and a device | phase 6 |
| Dragging several sources at once | later, if asked for |

## Outcome

Filled in at the end.
