# M2 · Phase 5 — The waveform widget

**Status:** in progress · **Plan:**
[plans/phase_5_waveform_widget.md](plans/phase_5_waveform_widget.md)

## Goal

`ui/widgets/waveform.py` draws a peak pyramid at whatever width it is given,
choosing the pyramid level that fits, in colours it reads from the theme when
it paints. It is one widget: the media pool's thumbnail in this milestone,
the inside of a clip at M3 and the parameters pane's full waveform after
that.

M9 left two instructions for every widget from here on: read colours at paint
time or implement `retheme()`, and add your groups to `04`. This is the first
widget to follow them from the start rather than being retrofitted.

## Scope

**In:** drawing one or two channels from the pyramid; choosing the level from
the widget's width; silence, a zero-length file and a missing file each drawn
as something distinguishable; the theme group or groups the widget paints
with, added to `04`'s ownership table and to the bundled theme; repainting on
a theme switch.

**Out:** drawing inside clips, and scrolling and zooming a waveform → M3.
Selection and playhead overlays → M3. Anything interactive — this phase
draws.

## Acceptance

- [ ] A full-scale sine fills the widget's height and silence draws only a
      centre line, asserted on a real offscreen grab rather than on the calls
      made to a painter.
- [ ] At any width the widget reads no more than a fixed multiple of its
      width in buckets, asserted by counting — a waveform that reads the
      finest level at thumbnail size is correct and slow, and slow is the bug
      N-4 would find much later.
- [ ] A missing file draws in `warn`, distinguishably from silence.
- [ ] A theme switch changes the widget's pixels, asserted under a theme where
      every token differs. Whether it gets there by reading at paint time or
      by `retheme()` is the plan's choice, and the Notes say which.
- [ ] The widget's groups are in `04`'s ownership table and the bundled theme,
      and no line of it names a hex (F-44's test already walks `ui/`).
- [ ] A screenshot of it at thumbnail and at full width is taken and looked
      at — the check that found both of M9 phase 4's bugs.

## Implements

F-9 (drawing half), F-21 (the widget M3 reuses), F-44 — *The vocabulary
grows* in [04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.
