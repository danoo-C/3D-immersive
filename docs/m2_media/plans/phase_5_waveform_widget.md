# Plan — M2 · Phase 5 — The waveform widget

**Written:** 2026-09-24 · **Status:** ✅ complete

## Approach

`ui/widgets/waveform.py`: a `QWidget` that is handed a `Pyramid` and draws
it, one lane per channel, one vertical stroke per pixel column from that
column's lowest to its highest sample. It is the first widget built after M9
told every later widget how to behave, and it follows both instructions from
the start.

**Colours are read when it paints, and `retheme()` is a repaint.** Nothing is
baked in, so there is nothing for a theme change to invalidate; the method
exists so D-82's walk reaches it and schedules the repaint rather than
relying on the application stylesheet to happen to cause one. It is the
cheapest way to satisfy both halves of M9's guidance at once.

**Which level it reads is chosen from its width.** The coarsest level whose
bucket covers no more frames than one pixel column does: at least one bucket
per column, and — because the next level up is four times coarser — fewer
than four. So the work of a paint is bounded by the widget's width, never by
the sample's length. Each column's envelope is one `minimum.reduceat` and one
`maximum.reduceat` over that level, not a Python loop over buckets.

## One theme group, and what it holds

`04`'s ownership table gives M2 the waveform thumbnail. The group is
`waveform`, and it is added to the bundled theme and to `04`:

| Key | Default | For |
|---|---|---|
| `background` | `surface.panel` | behind the lanes |
| `centre` | `border` | the zero line — what silence looks like |
| `fill` | `text.secondary` | the envelope |
| `missing` | `warn` | a sample whose file has gone |

A missing sample also says so in text, because *Accessibility and feel* says
missing media is never shown by colour alone. A widget with no peaks yet
draws only its background — which is distinguishable from silence, which
draws a centre line.

Clips at M3 will want the envelope in their channel's colour; that is the
reserved `channel` value, and M3's to wire.

## Steps

1. **The widget, and its group.** `Waveform` with `set_peaks(pyramid, *,
   missing=False)`, the level choice, the envelope, the missing and empty
   states, `retheme()`. The `waveform` group in the bundled theme and in
   `04`.
   *Test:* on real offscreen grabs, a full-scale sine inks the lane from top
   to bottom and silence inks only its centre row; stereo draws two lanes;
   missing draws in `warn` and differs from silence; no peaks differs from
   both; over widths from 1 to 4000 and lengths from one bucket to hours, the
   level read has at least one bucket per column and fewer than four, counted;
   under a theme where every token differs, the grab's colours change.

2. **Looked at.** A thumbnail and a full-width render grabbed offscreen and
   looked at, as M9 phase 4 did, before the phase is called done.

## Files

```
docs/04-ui-spec.md                              amended — the waveform group
docs/m2_media/phase_5_*.md                      amended — Notes
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — the group
src/immersive/ui/widgets/waveform.py            new
tests/test_waveform.py                          new — gui
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A new group in the bundled file breaking the spec-example tests | a red suite for a reason that looks unrelated | the example merges *over* the built-in, and a group it does not mention survives the merge; run the theme tests first |
| The level choice right on average and wrong at the edges | a thumbnail that reads a million buckets for a very short or very long file | a sweep over widths and lengths, asserting the bound at every point rather than at one |
| Pixel tests that depend on antialiasing | tests that pass here and fail on another platform's rasteriser | draw with antialiasing off — one-pixel strokes on pixel columns — and assert colours that are present, not exact coordinates |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the finest level always read | correct, and slow in proportion to the sample's length |
| the coarsest level always read | one bucket smeared across every column |
| lanes drawn for one channel only | a stereo sample drawn as its left channel |
| missing drawn like silence | a sample whose file has gone looks merely quiet |
| missing shown by colour alone | *Accessibility and feel*, broken |
| a colour read once and kept | the widget keeps the old theme |
| the centre line not drawn | silence draws nothing, like a sample not loaded |
| overs drawn past the lane | a float over paints into the next channel |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Drawing inside clips, scrolling and zooming | M3 |
| The envelope in a channel's colour | M3, through the reserved `channel` value |
| The pool that shows it | phase 6 |

## Outcome

Two steps in the planned order, all six acceptance boxes ticked, nine
mutations with one survivor, which was a missing test. 994 tests.

### What the plan got right

**Bounding the work by width.** The level choice was asserted at thirty
points from one pixel to four thousand and from one bucket to two hours, and
held at all of them.

**Grabs, not painter calls.** The over test's first version had the sign of
the over backwards; a test of calls would have agreed with the wrong
expectation, and the grab showed the widget was right.

### What the plan did not see

**That the risk row about the spec example was the wrong risk.** The plan
worried that a new group would break the tests of `04`'s worked example. It
did not; it broke M9's rule that every group key is a stylesheet
placeholder, which is a better thing to have broken, because the rule was
right and its scope was too narrow. D-92 is the result.

**The centre line's real job.** The plan named "the centre line not drawn"
as a mutation and assumed silence would catch it. Silence cannot, and a
sample offset from zero can.

### Deviations

| Planned | Actual |
|---|---|
| No change to M9's vocabulary tests | the placeholder test narrowed to stylesheet groups, and two tests added for painted ones (D-92) |
| Eight mutations | nine — a misspelled painted key |

### What phase 6 needs to know

`Waveform.set_peaks(pyramid, missing=...)` is the whole interface; with
`None` and not missing it draws only its background, which is the state
while a worker is still building the pyramid. It is `Expanding` horizontally
and has a minimum height of 12, and a pool row of about 20 px gives each
channel of a stereo sample 10.
