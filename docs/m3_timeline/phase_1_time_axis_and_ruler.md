# M3 · Phase 1 — The time axis, the ruler and the grid

**Status:** ✅ complete · **Plan:**
[plans/phase_1_time_axis_and_ruler.md](plans/phase_1_time_axis_and_ruler.md)

## Goal

The timeline panel replaces its placeholder with a `QGraphicsView`. A ruler
runs across the top and a grid is drawn from the open project's BPM, time
signature and snap division over lanes that are still empty. One time axis
owns which span of the timeline is visible and at what zoom. The view
observes it rather than owning it, so that M6's curve editor can observe the
same one. Wheel, Shift+wheel and Ctrl+wheel scroll and zoom as `04` says.
The playhead is drawn in `accent` over everything, and clicking the ruler
puts it there.

Every later phase in the milestone draws into this view.

## Scope

**In:** the `TimeAxis` — samples to pixels and back, scroll, zoom, and
zooming about a point — observed by the view; the view, the ruler and the
grid; grid density that thins as the zoom widens, so lines never crowd
(level of detail from the start, per the risk register in
[06](../06-roadmap.md)); ruler labels in bars:beats or minutes:seconds
(F-19), with the View menu's two ruler actions enabled; the playhead, drawn
and placed by clicking the ruler — playback moves it at phase 9; the groups
`ruler`, `grid` and `playhead`, painted (D-92) and taking a theme change
without the timeline being rebuilt; the toolbar's BPM, signature and snap
chips showing the open project's values rather than constants, and
following it through New and Open.

**Out:** channels and their headers → phase 2. Editing the BPM and time
signature → phase 7, with the numeric field. Choosing the snap division →
phase 5. The loop region → phase 9. The curve editor observing the axis →
M6. Remembering the ruler's unit between sessions → M8, after beta.

## Acceptance

- [x] The axis converts samples to x and back exactly at any zoom, and
      zooming about a point keeps that point's sample under it — asserted
      headless, with no view. *Under it to within half a pixel: the scroll
      offset is whole pixels, for the reason D-94 gives.*
- [x] Grid lines fall on the samples `core.time` says bars, beats and the
      snap division fall on — at 120 BPM in 4/4, in 6/8, and at a tempo
      whose beat is not a whole number of samples.
- [x] As the zoom widens, finer lines drop out before any two are closer
      than a stated number of pixels, and bar lines are the last to go.
- [x] Ctrl+wheel zooms about the cursor, Shift+wheel scrolls horizontally,
      and the wheel scrolls vertically.
- [x] The ruler labels bars:beats or minutes:seconds, switched from the View
      menu, and both actions' tooltips no longer name M3.
- [x] Clicking the ruler moves the playhead there, and the playhead is drawn
      in `accent` above the grid.
- [x] A project opened at 90 BPM in 3/4 draws its grid and ruler at 90 in
      3/4, and New goes back to the defaults.
- [x] `ruler`, `grid` and `playhead` are in `04`'s painted table and the
      bundled theme, every key read by a `group_color()` call (D-92), and a
      theme switch repaints the timeline without rebuilding it. *As the
      `ruler` group, and the grid and playhead as keys of the `timeline`
      group that `04`'s worked example had already named — see Notes.*
- [x] The toolbar's tempo, signature and snap chips show the open project's
      values.
- [x] A screenshot of the timeline at three zoom levels is taken and looked
      at.

## Implements

F-16 (the grid), F-19, D-52, D-92 — *Timeline* in
[04-ui-spec.md](../04-ui-spec.md), *Time* in
[03-data-model.md](../03-data-model.md), and the `TimeAxis` row of the risk
register in [06-roadmap.md](../06-roadmap.md).

## Notes

Appended while building.

**The time axis is `ui/time_axis.py`, Qt-free, and its offset is whole
pixels (D-94).** Not `core`, which holds what a project is and the edits
that change it, and not `ui/timeline/`, because M6's curve editor is its
second observer. The window holds it and hands it in. Whole pixels because
`QGraphicsView` scrolls in whole pixels: the scene's x is `sample / scale`,
the scrollbar value *is* the offset, and the ruler and the lanes cannot come
apart. That is why a zoom holds its point to half a pixel.

**`04` had already named the colours.** The plan proposed three groups —
`ruler`, `grid`, `playhead`. The worked example of a theme file under *The
file* in `04` already had a `timeline` group whose `grid` is `border` and
whose `playhead` is `accent`, and a test holds the built-in theme to that
example value for value. So the lanes draw from `timeline` — `background`,
`grid` for bars, `grid.beat`, `grid.division`, `playhead` — and the ruler
from its own `ruler` group. The example's test now waits on two things only:
`timeline.loop.region`, which is phase 9's, and the `clip` group, phase 3's.

**Crowding is judged on what is drawn together, not series by series.**
Triplet halves among beats leave gaps of a third of a beat — closer than
either alone. In ticks the smallest gap of such a union is the two steps'
greatest common divisor, which makes the rule exact: bars always, thinned by
powers of two; beats when they fit; the snap division when it fits among
them. `04`'s *Timeline* section now says so.

**The two ways `core.time` rounds a position agree.** Bars and beats are
placed as `from_bar_beat` places them and divisions as `snap` does. The two
were compared at 327 000 beat positions before anything was written, and
never differed.

**What the grab found.** On the ruler, beats and divisions were ticked the
same length, so a beat was hard to find by eye. The lanes had always told
them apart. A ruler mark now carries its grid line's level, and there are
three tick lengths.

**What the suite found about itself.** A theme-switch test that read a
window-sized grab one `pixelColor` at a time took 0.7 s; reading the image
through numpy takes 0.09 s, and still kills the mutation it was written for.
The phase adds 297 tests that run in 0.88 s together. The suite is 1417
tests: 11 s serially, 4.3 s in parallel, and 3.3 s in the fast lane, measured
on WSL2.
