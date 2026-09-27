# M2 · Phase 5 — The waveform widget

**Status:** ✅ complete · **Plan:**
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

- [x] A full-scale sine fills the widget's height and silence draws only a
      centre line, asserted on a real offscreen grab rather than on the calls
      made to a painter.
- [x] At any width the widget reads no more than a fixed multiple of its
      width in buckets, asserted by counting — a waveform that reads the
      finest level at thumbnail size is correct and slow, and slow is the bug
      N-4 would find much later.
- [x] A missing file draws in `warn`, distinguishably from silence.
- [x] A theme switch changes the widget's pixels, asserted under a theme where
      every token differs. Whether it gets there by reading at paint time or
      by `retheme()` is the plan's choice, and the Notes say which.
- [x] The widget's groups are in `04`'s ownership table and the bundled theme,
      and no line of it names a hex (F-44's test already walks `ui/`).
- [x] A screenshot of it at thumbnail and at full width is taken and looked
      at — the check that found both of M9 phase 4's bugs.

## Implements

F-9 (drawing half), F-21 (the widget M3 reuses), F-44 — *The vocabulary
grows* in [04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.

**The first widget built after M9, and the first whose colours no
stylesheet can express.** It reads them when it paints; `retheme()` is a
repaint, so D-82's walk still reaches it. That answers the acceptance line
that asked which: both, deliberately.

### ⚠️ D-92: M9's vocabulary rule assumed every group was a stylesheet's

M9 phase 1 made every group key a placeholder in `app.qss`, with a test that
the sheet and the vocabulary cover each other exactly. Adding the `waveform`
group broke that test on its first run, and rightly: it had no placeholder,
because the waveform draws with a painter. The rule itself — no key that
nothing reads — was worth keeping, so it was widened rather than relaxed.
Painted groups are declared in `theme.PAINTED`, and a second test reads `ui/`
for literal `group_color()` calls, requiring every painted key to appear in
one and every call to name a key that exists. A misspelled key in the widget
fails nine tests at once. Clips at M3, the spatial views at M5 and the curves
at M6 will all be painted groups, and this is how they join.

### Found by looking

At thumbnail size (120 × 20) and full width (900 × 120), from a real decoded
drum loop and pad, the envelope was right: accented hits taller, the pad's
two-second fade visible. The missing state was not quite: its dashed line
ran through the words *⚠ missing*, and the words are the half of that state
that does not depend on colour. The line now stops either side of them. No
image is committed, for the reason M9 phase 4 gave.

### What the mutation sweep found

Nine mutations — the plan's eight and a misspelled painted key. The survivor
was the centre line: silence inks its centre row with or without it, because
a stroke of no length is still a point. The line is the zero reference for
sound that never crosses zero, and no test drew any, so one now holds a
sample at +0.5 and asserts the line is there.
