# M3 · Phase 3 — Clips on the lanes

**Status:** not started · **Plan:** not written yet

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

- [ ] Dropping a pool row on a lane adds one clip at the snapped drop
      position, the whole length of its sample, in one undoable step (F-13).
- [ ] Dropping several rows adds that many clips, placed as the plan
      decides, in one undoable step.
- [ ] Dropping on the empty space below the last lane creates a channel
      holding the drop, in that same one step.
- [ ] A drop over part of an existing clip trims that clip so nothing
      overlaps; with the modifier held, the drop is refused and nothing
      changes. `model.validate()` is clean after every drop.
- [ ] With `Alt` held, the clip starts exactly where it was dropped.
- [ ] A clip shows its name and waveform in its channel's colour, and a clip
      whose sample is missing is drawn greyed and says *missing* in text.
- [ ] At a zoom where a clip is a few pixels wide, its waveform is not drawn
      and its name is elided; a clip's waveform pixmap is rebuilt when the
      zoom changes, not on every paint.
- [ ] A project of five hundred clips is opened, scrolled and zoomed, and a
      full repaint is measured and recorded in the Notes against the 16 ms of
      a 60 Hz frame.
- [ ] `clip body` is in `04` and the bundled theme.
- [ ] A screenshot of a real arrangement is taken and looked at.

## Implements

F-3 (drawn), F-13, F-17 (on drop), F-21 — *Timeline* and *Media pool* in
[04-ui-spec.md](../04-ui-spec.md), *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
