# M3 · Phase 1 — The time axis, the ruler and the grid

**Status:** not started · **Plan:** not written yet

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

- [ ] The axis converts samples to x and back exactly at any zoom, and
      zooming about a point keeps that point's sample under it — asserted
      headless, with no view.
- [ ] Grid lines fall on the samples `core.time` says bars, beats and the
      snap division fall on — at 120 BPM in 4/4, in 6/8, and at a tempo
      whose beat is not a whole number of samples.
- [ ] As the zoom widens, finer lines drop out before any two are closer
      than a stated number of pixels, and bar lines are the last to go.
- [ ] Ctrl+wheel zooms about the cursor, Shift+wheel scrolls horizontally,
      and the wheel scrolls vertically.
- [ ] The ruler labels bars:beats or minutes:seconds, switched from the View
      menu, and both actions' tooltips no longer name M3.
- [ ] Clicking the ruler moves the playhead there, and the playhead is drawn
      in `accent` above the grid.
- [ ] A project opened at 90 BPM in 3/4 draws its grid and ruler at 90 in
      3/4, and New goes back to the defaults.
- [ ] `ruler`, `grid` and `playhead` are in `04`'s painted table and the
      bundled theme, every key read by a `group_color()` call (D-92), and a
      theme switch repaints the timeline without rebuilding it.
- [ ] The toolbar's tempo, signature and snap chips show the open project's
      values.
- [ ] A screenshot of the timeline at three zoom levels is taken and looked
      at.

## Implements

F-16 (the grid), F-19, D-52, D-92 — *Timeline* in
[04-ui-spec.md](../04-ui-spec.md), *Time* in
[03-data-model.md](../03-data-model.md), and the `TimeAxis` row of the risk
register in [06-roadmap.md](../06-roadmap.md).

## Notes

Appended while building.
