# Plan — M3 · Phase 1 — The time axis, the ruler and the grid

**Written:** 2026-09-25 · **Status:** ✅ complete

## Approach

Three layers, each testable without the one above it.

**The axis is numbers.** `ui/time_axis.py` holds a `TimeAxis`: a scale in
samples per pixel, a scroll offset, the width of the viewport and the extent
that can be scrolled over. It converts a sample to an x and back, scrolls,
and zooms about a point. It imports no Qt. It notifies observers with plain
callbacks, the way `Document` does, so the arithmetic is tested headless and
runs in the fast lane.

**The grid is numbers too.** `ui/timeline/grid.py` answers two questions for
a visible span at a given scale: which grid lines to draw, each marked as a
bar, a beat or a division; and which ruler marks to draw, with their labels,
in either unit. It is also Qt-free. This is where level of detail lives:
finer lines drop out before two of them come closer than a minimum number of
pixels, and bars are thinned by powers of two only when bars themselves would
crowd.

**Then the widgets draw what those two say.** `ui/timeline/view.py` is a
`QGraphicsView` whose background is the grid and whose foreground is the
playhead. `ui/timeline/ruler.py` is a plain widget above it, and
`ui/timeline/panel.py` puts both into a `Panel` in place of the placeholder.
Every colour is read at paint time from three painted groups (D-92), so
`retheme()` on each is only a request to repaint. That is also the answer to
M9's warning about scene items: they will read their colours when they
paint, and the view's `retheme()` invalidates the scene.

## The first decision: where the axis lives

The README left this open between `core/` and `ui/timeline/`. It goes in
neither, and it is recorded as D-94: `ui/time_axis.py`, Qt-free.

- **Not `core/`.** `core` holds what a project *is* and the edits that
  change it. The selection goes there at phase 4 because edits read it. The
  axis is only how a project is being looked at. Nothing saves it, and the
  engine never asks for it.
- **Not `ui/timeline/`.** The curve editor at M6 is its second observer, so
  it is not the timeline's to own. The risk register's whole point is that
  neither widget owns it.
- **Qt-free anyway.** The arithmetic is where the bugs would be. A zoom that
  drifts or a click landing a sample off is found in milliseconds without a
  window, and a layering test keeps it that way, as it does for the theme
  modules.

**The scroll offset is a whole number of pixels, not a number of samples.**
`QGraphicsView` scrolls in integer pixels. An axis whose offset was a
fractional sample count would put the ruler, which is drawn from the axis,
and the lanes, which the view scrolls, a fraction of a pixel apart, with no
way to say which of them was right. With the offset in whole pixels, a scene
x is `sample / scale` and the view's scrollbar value *is* the offset, so the
two cannot disagree. The cost is that zooming about a point keeps that point
within half a pixel rather than exactly, and the acceptance line is read
that way.

## The grid's arithmetic

Bars and beats are placed with the expression `from_bar_beat` uses:
`round(beat_index * samples_per_beat)`. Divisions are placed with the one
`snap` uses: `round(k * grid_step)`. So a clip snapped to a line at phase 5
sits on the line as drawn. Before writing this, the two roundings were
compared at 327 000 beat positions over random tempos from 40 to 240 BPM and
six time signatures. They never differed, so no shared function is added to
`core.time`, and the test that compares the grid against both would say so
if they ever did.

A line belongs to the coarsest series it is on. A bar line is drawn as a
bar, never also as a beat. Division lines are drawn only while snapping is
on, because the grid shows "the current snap division" (`04`, *Timeline*).

## Three painted groups

`04`'s vocabulary table gives M3 these. Every value names a token, so a
theme that changes only its tokens re-colours the timeline too.

| Group | Key | Default | For |
|---|---|---|---|
| `ruler` | `background` | `surface.raised` | behind the ticks and labels |
| `ruler` | `tick` | `text.disabled` | tick marks |
| `ruler` | `text` | `text.secondary` | labels |
| `grid` | `background` | `surface.panel` | behind the lanes |
| `grid` | `division` | `surface.raised` | the snap division — faintest |
| `grid` | `beat` | `surface.hover` | beats |
| `grid` | `bar` | `border` | bars — strongest |
| `playhead` | `line` | `accent` | the playhead, over everything, across ruler and lanes |

The three grid values rely on `04`'s rule that the surfaces are monotonic,
deepest first, and not on their literal values.

## Steps

1. **The axis, and D-94.** `TimeAxis` with `x_of`, `sample_at`,
   `visible()`, `scroll_by`, `scroll_to`, `zoom_about`, `set_width` and
   `set_extent`; scale clamped between one sample per pixel and one minute
   per pixel, and offset clamped to what can be scrolled. D-94 in `01`,
   `doc-system.md`'s high-water mark, and `02`'s layout.
   *Test (headless):* round trips at every zoom from the closest to the
   widest; `zoom_about` keeps its anchor within half a pixel, at anchors
   across the width; clamps at both ends; observers told once per change
   and not at all for a change that changes nothing; `time_axis.py` imports
   no Qt.

2. **The grid and the ruler marks, as numbers.** `grid_lines()` and
   `ruler_marks()` over a span and a scale, with the level-of-detail rule.
   *Test (headless):* at 120 BPM in 4/4, in 6/8, and at 97.3 BPM, where a
   beat is not a whole number of samples, bar and beat lines equal
   `from_bar_beat`'s samples and division lines equal what `snap()` returns
   for them. At every zoom no two lines drawn are closer than the minimum,
   and a coarser level is never dropped while a finer one is drawn. Bars
   thin by powers of two. There are no division lines with snapping off.
   Minutes:seconds labels step through round values: 1, 2, 5, 10, 15 and 30
   seconds, then minutes.

3. **The view, drawing the grid, and the wheel.** `TimelineView` on the
   axis: scene x as pixels at the current zoom, the scrollbar written from
   the axis and back, the grid in `drawBackground`, Ctrl+wheel zooming about
   the cursor, and Shift+wheel or a horizontal wheel scrolling sideways.
   The `grid` group, and `PAINTED`.
   *Test (gui, the widget alone):* in a grab, the pixel columns where the
   axis puts bar lines are `grid.bar` and those between beats are the
   background. A synthesised Ctrl+wheel leaves the sample under the cursor
   within half a pixel. Shift+wheel moves only the horizontal offset.
   Dragging the scrollbar moves the axis.

4. **The ruler, the playhead and the unit.** `Ruler` drawn from
   `ruler_marks()`; a click moving the playhead; the playhead in the view's
   foreground and across the ruler; the View menu's two ruler actions as
   one exclusive, checked pair; the `ruler` and `playhead` groups; the panel
   replacing the placeholder in the window.
   *Test (gui):* clicking the ruler at x puts the playhead at
   `sample_at(x)`, drawn in `accent` in both widgets. Switching the unit
   changes the labels and not the grid. The window still has seven panels,
   and the two ruler actions no longer name M3.

5. **The project in the timeline.** The view and ruler read BPM, signature
   and snap from the document when they paint, and repaint on every change
   the document reports. The toolbar's three chips show the same values.
   The groups documented in `04`.
   *Test (gui):* a project opened at 90 BPM in 3/4 draws bars three beats
   of 90 BPM apart, and New goes back to 120 in 4/4. The chips read `90.0
   BPM`, `3/4` and the snap setting, and follow Undo. Under a theme where
   every token differs, grabs of the ruler and the view change colour
   without the panel being rebuilt.

6. **Looked at.** Grabs of the timeline at three zoom levels, and in both
   units, looked at before the phase is called done.

## Files

```
docs/01-requirements.md                        amended — D-94
docs/02-architecture.md                        amended — time_axis.py
docs/04-ui-spec.md                             amended — two painted groups
docs/doc-system.md                             amended — high-water mark
docs/m3_timeline/phase_1_*.md                  amended — Notes, boxes
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — three groups
src/immersive/ui/theme.py                      amended — PAINTED
src/immersive/ui/time_axis.py                  new — Qt-free
src/immersive/ui/timeline/grid.py              new — Qt-free
src/immersive/ui/timeline/view.py              new
src/immersive/ui/timeline/ruler.py             new
src/immersive/ui/timeline/panel.py             new
src/immersive/ui/main_window.py                amended — panel, menu, chips
tests/test_time_axis.py                        new — headless
tests/test_grid.py                             new — headless
tests/test_timeline.py                         new — gui
tests/test_layering.py                         amended — Qt-free modules
tests/test_main_window.py                      amended if the panel count moves
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The ruler and the lanes a pixel apart after scrolling or zooming | a grid that visibly slides against its own ruler, the one thing a timeline must not do | the offset in whole pixels (D-94), and a test that drags the scrollbar and compares the axis |
| Wheel events differing by platform | Shift+wheel arrives as a horizontal delta on some platforms and a vertical one with a modifier on others | treat either as horizontal, and test both shapes of event |
| Pixel tests on one-pixel lines | tests that pass here and fail on another rasteriser | antialiasing off for lines, and assertions on colours present in a column, not exact coordinates — as the waveform's tests did |
| GUI tests that each build a `MainWindow` | the suite slows by 50 ms a test | build the panel alone wherever the window is not the point, per the speed plan's *Keeping it fast* |
| A grid computed per paint at wide zoom | thousands of lines a paint at a long project zoomed out | the level-of-detail rule bounds lines by pixels, not by length, and a test counts them at the widest zoom |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `zoom_about` anchoring on the left edge | every zoom jumps away from the cursor |
| the offset not clamped at zero | scrolling left of the timeline's start |
| the scale not clamped | a wheel spin zooms to nothing or to infinity |
| observers told of a change that changed nothing | repaints for nothing on every mouse-move |
| grid lines accumulated by addition | drift at a tempo whose beat is fractional |
| the beat taken as a quarter note in 6/8 | the grid wrong in every compound time |
| the level-of-detail rule removed | lines crowd into a solid block when zoomed out |
| bars thinned before beats are dropped | a zoomed-out ruler with beats and no bars |
| division lines drawn with snapping off | a grid promising a snap that will not happen |
| the scrollbar not written back to the axis | the ruler and the lanes disagree after a scrollbar drag |
| Ctrl+wheel zooming about the view's centre | zoom not about the cursor |
| a colour read once at construction | the timeline keeps the old theme |
| the playhead drawn under the grid | a playhead hidden by a bar line |
| minutes:seconds labels read from bars | a ruler in the wrong unit |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Channel headers, lanes and their heights | phase 2 |
| Anything placed in the scene | phase 3 |
| Choosing the snap division | phase 5 |
| Editing the BPM and signature | phase 7 |
| The playhead moving during playback, the readout, the loop region | phase 9 |
| Remembering the ruler's unit between sessions | M8, after beta |

## Outcome

Six steps in the planned order, all ten acceptance boxes ticked. Twenty-six
mutations were run and two survived their first run, both now killed:
fourteen named in advance, the rest found on the way. 1417 tests.

### What the plan got right

**Three layers, each testable without the one above.** Every question about
where a line goes or where a click lands was settled by 297 tests that run
in under a second, most of them with no window at all. The widgets draw
what the numbers say and decide nothing, and their tests only check that
they did.

**Offset in whole pixels.** The ruler and the lanes never came apart. A test
drags the scrollbar and reads the axis, and another does the reverse; they
could not disagree by a fraction because there is no fraction to disagree
by.

**Deciding the rounding question before writing the grid.** Five minutes
comparing `from_bar_beat` with `snap` meant `core.time` did not change.

### What the plan did not see

**That `04` had already named the colours.** The plan invented `ruler`,
`grid` and `playhead` groups. The worked example of a theme file in `04`
already held a `timeline` group with `grid` and `playhead` keys, and a test
holds the built-in to it. The spec won: see the phase's Notes.

**That lines can crowd across series.** The plan's level-of-detail rule
checked each series against the minimum spacing. Triplet halves among beats
passed that and still drew lines four pixels apart. The rule is now judged
on the union, in ticks, by the greatest common divisor, and the mutation that
undoes it is killed.

**That a grab cannot see a missing repaint.** `grab()` renders afresh
whatever was scheduled, so "the lanes repaint when the project changes" was
untestable the way the plan said. The test counts paint events instead.

**That the ruler's ticks needed three lengths.** Only the grab showed it.

### Deviations

| Planned | Actual |
|---|---|
| Groups `ruler`, `grid`, `playhead` | `ruler`, and `timeline` with `grid`, `grid.beat`, `grid.division` and `playhead`, as `04`'s example named them |
| Level of detail judged per series | judged on the union of what is drawn, by greatest common divisor |
| A ruler mark major or minor | a ruler mark carries its line's level, and three tick lengths |
| The theme-switch test at step 5 | written at step 4, to kill the survivor there |
| Two redundant scale clamps | one; the second was an equivalent mutation, removed rather than pinned |

### What phase 2 needs to know

`TimelinePanel(document, axis)` is a `Panel` holding `ruler` and `view`, and
the window's `timeline()` returns it. The view's scene is one pixel high and
exactly `axis.span()` wide; phase 2 makes it as tall as its lanes, and puts
the channel headers in a column to the left. The ruler has to stay aligned
with the lanes, so it will need a spacer as wide as the headers. The view's
`drawBackground` draws the grid over whatever rectangle is exposed, so lanes
can be drawn over it, as items or as background, without the grid being
asked. `panel.playhead()` is where the playhead is until phase 9.
