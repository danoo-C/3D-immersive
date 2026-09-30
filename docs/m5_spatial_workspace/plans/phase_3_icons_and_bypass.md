# Plan — M5 · Phase 3 — What an icon says, and the bypass strip

**Written:** 2026-09-30 · **Status:** in progress

## Approach

**What an icon says (D-146).** Two rules, in a small Qt-free module the 3D
view will read too (`ui/spatial/look.py`):

- **Radius from distance.** The distance is the side's own, from the
  listener, in three dimensions, so a source above the head is as small as
  one as far ahead: that is how the top view "tells you about height
  indirectly" (04). 10 px at 1 m, 2 px less each time the distance doubles
  (8 px at 2 m, 6 px at 4 m), between 5 and 13 px. The rule is in octaves
  of distance rather than 1/d, which would make a source at 8 m a tenth of
  one at 0.8 m, too small to click or to see its colour.
- **Opacity from gain, like loudness.** 100% at 0 dB and above. Below it,
  the opacity falls towards a floor of 40%, halving its height above the
  floor every 10 dB, which is roughly half as loud: 70% at −10 dB, 55% at
  −20 dB. The floor is above mute's 25%, so no gain looks muted.
- **A channel not heard is at 25%**, whatever its gain: muted, or silenced
  because another channel is soloed. Both are "not heard", which is what a
  faint icon says. The headers already say *silenced* for the second
  (M3), and `audible()` decides both. A soloed channel glows, a soft halo
  in its own colour, so the silenced ones say why.

A pair's two sides each take the radius of their own distance, and share
the channel's opacity. The line joining them takes it too. The selected
ring is drawn at full strength, since it is the selection's, not the
channel's. An icon being dragged takes its radius from where the drag has
it, so it grows as it comes nearer.

**The bypass strip (D-147).** A painted widget of its own, under the top
view in the tab, not over it. An overlay would cover the sources behind
the listener, and take their clicks. It is hidden, and takes no room, when
no channel is bypassed. Its chips follow the project's channel order, each
a dot in the channel's colour, its name elided past 140 px, and a ⊘. They
wrap into as many rows as they need, so every bypassed channel is always
shown. A click on a chip selects its channel as a click on its icon would,
and Ctrl toggles. A click on ⊘ un-bypasses it, as one edit, the header's
own. The ⊘ under the pointer is highlighted, and a selected chip is
outlined in `selected`, as its icon would be ringed.

The strip's colours are four more keys in the `spatial` group (D-92):
`strip`, `chip`, `chip.text` and `chip.glyph`. The ⊘ under the pointer is
drawn in `selected`.

## Decisions settled here

**D-146**: an icon's radius follows its distance in octaves, its opacity
its gain like loudness, and a channel not heard is at 25%. **D-147**: the
bypass strip is a widget of its own under the top view, its chips wrapping.

## Steps

1. **The rules.** `ui/spatial/look.py`, Qt-free: `radius(position)` and
   `opacity(gain_db, heard)`. Tests: the values the rules name; the 3D
   distance; the limits; the floor above mute.
2. **The icons drawn by them.** `Icon` gains its opacity and whether it
   glows; the views draw both. Tests: a nearer icon is larger, in both
   views; a quieter one is fainter, read as a pixel blended over the
   background; muted and silenced are at 25%; a soloed icon's glow is
   there beyond its edge; a dragged icon's radius follows the drag.
3. **The strip.** `ui/spatial/bypass_strip.py`, and its keys. Tests: a
   chip for each bypassed channel and none other; hidden when none; every
   chip inside the strip when they wrap; a click selects and Ctrl toggles;
   ⊘ un-bypasses in one edit and the icon is back where it was kept.
4. **In the window.** The strip under the top view in the tab; a bypass
   toggled in a header shows it. Tests: the strip shown and hidden by an
   edit made elsewhere; the top view keeps the rest of the tab.
5. **Looked at, the sweep and the close.**

## Files

`src/immersive/ui/spatial/look.py` — new
`src/immersive/ui/spatial/ortho_view.py` — radius, opacity, glow
`src/immersive/ui/spatial/bypass_strip.py` — new
`src/immersive/ui/main_window.py` — the strip under the top view
`src/immersive/assets/themes/vscode_dark.3dimtheme` — the strip's keys
`docs/04-ui-spec.md` — the rules, the strip, the keys
`tests/test_spatial_look.py`, `tests/test_bypass_strip.py` — new;
`tests/test_ortho_view.py`, `tests/test_main_window.py` — extended

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | one radius for every distance | the values the rule names; a nearer icon is larger |
| 2 | the distance across the view's plane only | the 3D distance |
| 3 | no limits on the radius | the limits |
| 4 | opacity not from gain | a quieter icon is fainter |
| 5 | a floor below mute | the floor above mute |
| 6 | a muted icon at its gain's opacity | muted at 25% |
| 7 | a channel silenced by solo drawn as heard | silenced at 25% |
| 8 | no glow | a soloed icon's glow |
| 9 | a dragged icon's radius from the model | its radius follows the drag |
| 10 | a bypassed channel with no chip, or a chip for one not bypassed | a chip for each bypassed channel |
| 11 | the strip shown when none is bypassed | hidden when none |
| 12 | chips in one row past the strip's edge | every chip inside when they wrap |
| 13 | a chip's click not selecting, or Ctrl not toggling | a click selects, Ctrl toggles |
| 14 | ⊘ selecting and not un-bypassing | ⊘ un-bypasses in one edit |
| 15 | the strip not told of an edit | shown and hidden by an edit made elsewhere |

## Risks and unknowns

- **A pixel's colour read back** is the blend of the icon over the
  background, rounded, so a test compares within a step of two, and only
  at an icon's centre, clear of its letter.
- **The head moves up when the strip appears.** The view is shorter, and
  the head is at its centre. A drag under way when a channel is bypassed
  from elsewhere is dropped anyway (phase 2), so nothing moves under the
  pointer.

## Out of scope for this plan

| Not here | Where |
|---|---|
| The same icons in the 3D view | phase 4, from `look.py` |
| Depth order, nearer icons drawn over farther | later, if asked for |
| Gain moved by automation, and so the opacity | M6 |
| A chip reached by keyboard | the header's B button does the same today |

## Outcome

Filled in at the end.
