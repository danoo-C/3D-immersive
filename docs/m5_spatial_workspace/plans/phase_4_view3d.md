# Plan — M5 · Phase 4 — The 3D view

**Written:** 2026-09-30 · **Status:** ✅ built

## Approach

**The camera (D-148).** A true isometric projection: a metre along X, Y
or Z is the same length on screen, so a height reads like a distance on
the ground. The camera is behind the listener, as the front view's is,
and to their left, looking down at 35.26°. So their right, +X, goes up and
to the right of the screen, as it goes right in the ortho views; their
front, +Y, goes up and to the left; and up is up. The listener faces into
the scene, not out of it. On screen, with `s` pixels a metre and the head
at `(cx, cy)`:

    x = cx + s·cos 30°·(X − Y)
    y = cy − s·(sin 30°·(X + Y) + Z)

**What fits.** The head stays at the view's centre, and the scene is a
square of ground about it, from −R to +R metres in X and Y. R is the
smallest of 2, 4, 8, 16 ... metres that holds every placed source in X, Y
and Z, so the view rescales only when a source crosses a step, not as it
moves. `s` fits the ground's diamond, and heights of ±R above and below
it, inside the view with a margin. *(Built otherwise: up and down it fits
the sources, in quarters of R. See the Outcome.)* There is no zoom and no
pan, since the view has no controls (04).

**What is drawn**, back to front:

- the background, then the ground grid at ear level, Z = 0, a line every
  metre, or wider when R is large, in a new `spatial` key, `grid`. A
  *front* label at its front edge, since the head's nose is small;
- each placed source's **drop line**, from its icon straight down or up to
  its point on the grid, marked there with a small dot. That is what
  shows its height, and it tells a source ahead and high from one behind
  and low, which the projection puts in the same place;
- the head and every icon in **depth order**, the farthest from the camera
  first. Depth along the camera's direction is `Z − X − Y`. So a source
  nearer the camera covers a farther one, and the head covers the sources
  behind it and is covered by those in front of it;
- the selected channels' rings last, over everything, since a ring is the
  selection's and should not be lost behind another icon.

Icons follow phase 3's rules from `look.py`: radius from distance, opacity
from gain, a quarter when not heard, a glow when soloed. A pair is its two
sides joined. A bypassed channel is not drawn (D-36). Its chip is in the
top view's strip.

**No input.** The view takes no mouse or wheel input and no focus, so a
click, a drag or a scroll passes through and changes nothing. It repaints
on the document, the selection, a drag in progress and a theme switch.

## Decisions settled here

**D-148**: the 3D view is a true isometric from behind the listener and to
their left, the head at its centre and the ground fitted in steps.

## Steps

1. **The projection and its fit.** `ui/spatial/view3d.py`: `point_of`,
   `half_size` and `per_metre`. Tests: a source at a known position is
   drawn where the formula puts it, within a pixel, and above its point
   on the grid by its height; the ground fits the view; R steps and holds
   between steps.
2. **Drawn.** The grid, the drop lines, the head and the icons in depth
   order, the rings last; the `grid` key. Tests: a source in line with
   another nearer the camera is covered by it, whatever the channel
   order; the head covers a source behind it and is covered by one in
   front; a pair is two icons; a bypassed channel is not drawn; icons
   take phase 3's radius and opacity.
3. **In the window.** The 3D tab's placeholder replaced. Tests: key 3
   shows it; an edit repaints it; a press, a drag and a scroll on it
   change nothing.
4. **Looked at, the sweep and the close.**

## Files

`src/immersive/ui/spatial/view3d.py` — new
`src/immersive/ui/main_window.py` — the 3D tab
`src/immersive/assets/themes/vscode_dark.3dimtheme` — `grid`
`docs/04-ui-spec.md` — the camera, and the `grid` key
`tests/test_view3d.py` — new; `tests/test_main_window.py` — the tab

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | X and Y swapped in the projection | drawn where the formula puts it |
| 2 | height not drawn | above its point on the grid by its height |
| 3 | icons in channel order, not depth | a source in line is covered by the nearer |
| 4 | the head always under the icons | the head covers a source behind it |
| 5 | R following the farthest source continuously | R steps and holds |
| 6 | R not holding a source's height | the ground fits, and heights with it |
| 7 | the radius not from `look` | icons take phase 3's radius |
| 8 | a bypassed channel drawn | a bypassed channel is not drawn |
| 9 | a press selecting | a press changes nothing |
| 10 | not repainted on an edit | an edit repaints it |
| 11 | a pair drawn as one point | a pair is two icons |

## Risks and unknowns

- **The drop line is the only cue to height**, since shading would need a
  light and a GL scene. The grab will say whether it is enough.
- **Two views of the same icons.** The ortho views and this one must not
  disagree about an icon's look, so this one reads `look.py` and draws
  with the ortho view's own `Icon`.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Trails, and the "now" dot | M6 |
| A camera to move, or a GL scene | not in v1 (04) |
| Selecting in the 3D view | not in v1: it is for reading the scene |

## Outcome

Built as planned, with one change the first grab asked for: the fit kept
room for heights of ±R, which only a source R high at the ground's far
corner needs, and the ground filled a third of the view. Up and down it
now fits the source farthest up or down the screen, in steps of a quarter
of R, so the view still holds still while a source moves within a step.
`depth` became a module function, `nearness`, since a widget's `depth()`
is Qt's own.

Twelve mutations were run, the eleven named and one more, *no drop
lines*, caught by the drop line's foot. All were caught the first time.

What phase 5 needs: three views that repaint on every edit and every
movement of a drag, and the 3D view that repaints only while its tab is
shown.
