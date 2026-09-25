# M3 · Phase 3 — Clips on the lanes

**Status:** ✅ complete · **Plan:**
[plans/phase_3_clips_on_the_lanes.md](plans/phase_3_clips_on_the_lanes.md)

## Goal

Dragging samples from the media pool onto a lane creates clips there, at
the snapped drop position. Dropping on the empty space below the last lane
creates a channel holding them. Clips are drawn in their channel's colour,
with their name and their waveform inside, and stay fast to draw when there
are hundreds of them. A project opened from disk draws its clips. A clip
whose sample is missing is drawn greyed, and says so.

This is the phase where an arrangement can first be seen.

## Scope

**In:** the timeline as the drop target for the MIME type `04` names under
*Media pool* — M2 built the source; the drop position snapped to the grid
and to other clips' edges (F-13, F-17), and exact while `Alt` is held;
several samples in one drop; a drop onto empty space creating a channel
(`04`, *Media pool*); a drop onto an occupied span trimming the clip
underneath, and a modifier refusing the drop instead (`03`, *Rules*); each
drop one command; the clip item — body in the channel's colour, name, and
the waveform drawn from the peak pyramid (F-21), reusing M2's drawing rather
than a second copy of it; waveform detail dropping out as the zoom widens,
and a cached pixmap per clip (`04`, *Timeline*); a missing sample drawn
greyed and labelled (F-3); the `clip body` group.

**Out:** moving, trimming, splitting and the rest → phase 5. Selecting
clips → phase 4. Fade handles → phase 7. Hearing them → phases 8 and 9.

## Acceptance

- [x] Dropping a pool row on a lane adds one clip at the snapped drop
      position, the whole length of its sample, in one undoable step (F-13).
- [x] Dropping several rows adds that many clips, placed as the plan
      decides, in one undoable step.
- [x] Dropping on the empty space below the last lane creates a channel
      holding the drop, in that same one step.
- [x] A drop over part of an existing clip trims that clip so nothing
      overlaps; with the modifier held, the drop is refused and nothing
      changes. `model.validate()` is clean after every drop.
- [x] With `Alt` held, the clip starts exactly where it was dropped.
- [x] A clip shows its name and waveform in its channel's colour, and a clip
      whose sample is missing is drawn greyed and says *missing* in text.
- [x] At a zoom where a clip is a few pixels wide, its waveform is not drawn
      and its name is elided; a clip's waveform pixmap is rebuilt when the
      zoom changes, not on every paint.
- [x] A project of five hundred clips is opened, scrolled and zoomed, and a
      full repaint is measured and recorded in the Notes against the 16 ms of
      a 60 Hz frame. *Cached repaints and scrolling take 2–4 ms; a cold
      repaint 13 ms with 33 clips on screen and 57 ms with 275 — see Notes.*
- [x] `clip body` is in `04` and the bundled theme.
- [x] A screenshot of a real arrangement is taken and looked at.

## Implements

F-3 (drawn), F-13, F-17 (on drop), F-21 — *Timeline* and *Media pool* in
[04-ui-spec.md](../04-ui-spec.md), *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**A drop inside a longer clip splits it (D-95).** `03` said a drop trims
what it lands on and not what happens to a clip longer than the drop on both
sides. `DropClips` subtracts the dropped spans from each clip already there,
and what is left decides: nothing — removed; one part — trimmed; two — split,
the tail a new clip with a fresh id. Every part plays the samples it played
before. `03`'s rule is amended.

**The waveform drawing learned ranges, and found a seam first.** A trimmed
clip shows its own frames, so `envelope` and `paint_envelope` take a frame
range and a run of columns, and the pool's thumbnail became one caller of
them. The test that a strip of columns equals those columns of the whole
failed before anything was on screen: a strip's last column ended a bucket
late, so strips painted while scrolling would not have met.

**Qt's device cache is the view's size, and lies about the first paint.**
Checked before relying on it: an item ten million pixels wide caches a
view's width of pixmap, not its own. But the first paint is told the whole
item is exposed, so a clip draws only what is exposed *and* on the
painter's device; a test counts the columns a 48 000-pixel clip draws.

**The clip group is `04`'s example's**, and `body` and `waveform` are the
first keys any widget paints per channel. `theme.channel_group_color`
resolves them, and painted groups no longer go into the stylesheet at all —
the first `channel` value would have broken it.

**Five hundred clips, measured.** Twenty channels of twenty-five, on WSL2.
Scrolling and a cached repaint take 2–4 ms. A cold repaint — after a zoom,
a theme change, peaks arriving — was 81 ms and is 57 ms with 275 clips on
screen at 40 px each, and 13 ms at an ordinary zoom with 33. Two causes were
fixed: the waveform was one line call per pixel column in Python and is now
one image per clip; and every colour lookup ran an `import` statement,
which the application pays on every paint as well. What is left at the
densest zoom is per-item Python, spread thinly.

**The drop tests call the view's handlers directly.** A synthesised drag
the view ignored, sent through `QApplication.sendEvent`, crashed the
interpreter: Qt carries an ignored drag up the parent chain expecting a
real drag in progress.

The phase adds 57 tests. The suite is 1574: 13 s serially, 5.5 s in
parallel, 3.4 s in the fast lane.
