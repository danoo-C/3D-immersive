# Plan — M5 · Phase 1 — The ortho views, drawn

**Written:** 2026-09-30 · **Status:** in progress

## Approach

**One view, two planes.** `OrthoView` draws one plane of the scene: the
top view is X across and Y up-screen, and the front view is X across and Z
up-screen. In both, screen-right is +X, as 03's *Coordinate system* fixes,
so the front view is the listener's own front, seen from behind: a source
to the right is to the right in both views.

**A shared scale (D-143).** How metres become pixels is `Scale`, Qt-free,
as the timeline's `TimeAxis` is (D-94). It holds pixels per metre and the
metre of X at the views' centre. Both views share one `Scale`, so their X
lines up and a zoom in either zooms both. Each keeps its own vertical
centre, Y for the top view and Z for the front. At first the head is
centred and the shorter side of a view shows 8 m, ±4 m about the head.
Zoom goes from 2 m across to 200 m, about the pointer, so the metre under
it stays under it. Middle-drag pans: horizontally both views together,
vertically the one dragged. Scroll zooms.

**What is drawn**, back to front:

1. the background;
2. in the top view, rings every metre around the head, labelled at the
   right, and every fifth one stronger once there are many; in the front
   view, the ear-level line, Z = 0, with its label;
3. the head: in the top view a circle with a nose up-screen and ears, and
   in the front view a circle with ears, seen from behind;
4. every channel that is not bypassed. A point is a filled circle in the
   channel's colour. A pair is its two sides, each a smaller circle marked
   L or R, joined by a line in the channel's colour;
5. the selected channels last, each ringed in the accent colour, so they
   are drawn over the others.

Radius, opacity, mute and solo are phase 3's. Here an icon is a fixed
size: 7 px for a point, and 6 px for a pair's side.

**Selecting.** A click selects the channel whose icon is under the
pointer, nearest first and the selected ones before the rest, as they are
drawn on top. Ctrl-click toggles one in or out. A click on empty space
clears the selection. It goes through the document's selection, so the
timeline's headers and the pane follow, as they do for a click on a
header.

**The colours are a painted group, `spatial`** (D-92), read when it
paints: `background`, `ring`, `ring.label`, `level`, `head`, `head.fill`,
`icon`, `pair` and `selected`. `icon` and `pair` are the reserved
`channel` value, as the clips' are, so a theme may paint every source one
colour. 04 gets the group's table.

**Into the window.** The two placeholders become the views. The View
menu's Focus Top View (1), Focus Front View (2) and Focus 3D View (3) are
enabled. The first two select the first tab and focus their view, and the
third selects the 3D tab. The views repaint when the document changes,
when the selection changes, and on a theme switch.

## Decisions settled here

**D-143**: the views share one scale and X, each with its own vertical
centre; 8 m across the shorter side at first; zoom from 2 m to 200 m about
the pointer; middle-drag pans, scroll zooms.

## Steps

1. **The scale.** `ui/spatial/scale.py`, Qt-free. Tests: metres to pixels
   and back, for both views on one scale; zoom about a point keeps its
   metre under it; the limits hold; a pan moves both views' X and one
   view's vertical; observers are called once a change.
2. **The view, drawn.** `ui/spatial/ortho_view.py`, the `spatial` group,
   and 04's table. Tests: a channel at (1, 2, 0) is drawn where the
   acceptance says in both views, at a zoom and a pan; a pair is two
   points; a bypassed channel is not drawn; every `spatial` key is read.
   Then looked at: grabs of both views with a real arrangement.
3. **Selecting.** Click, Ctrl-click, empty click; the selected channel
   drawn over. Tests: each, with two icons overlapping.
4. **In the window.** The views in the workspace; keys 1 to 3; repaint on
   document, selection and theme. Tests: the keys; a position typed in the
   pane moves the icon; a theme switch changes a view's pixels.
5. **The sweep and the close.**

## Files

`src/immersive/ui/spatial/scale.py` — new
`src/immersive/ui/spatial/ortho_view.py` — new
`src/immersive/ui/main_window.py` — the views; keys 1 to 3
`src/immersive/ui/theme.py` — `spatial` among the painted groups
`src/immersive/assets/themes/vscode_dark.3dimtheme` — the `spatial` group
`docs/04-ui-spec.md` — the `spatial` table
`tests/test_spatial_scale.py`, `tests/test_ortho_view.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | +Y drawn down-screen | a channel at (1, 2, 0) in the top view |
| 2 | the front view showing Y for Z | the same channel, at ear level in the front view |
| 3 | X mirrored in the front view | X agrees in both views |
| 4 | zoom about the centre, not the point | zoom keeps the metre under the pointer |
| 5 | no zoom limits | the limits hold |
| 6 | a pan moving the other way | a pan moves the metre with the pointer |
| 7 | a pan moving both views' vertical | a pan moves one view's vertical |
| 8 | a bypassed channel drawn | not drawn |
| 9 | a pair drawn as one point | a pair is two points |
| 10 | a click on empty space keeping the selection | an empty click clears |
| 11 | the hit test taking the icon beneath | overlapping icons: the selected one is hit |
| 12 | the selected channel drawn first | the selected icon's pixels are on top |
| 13 | colours read once, not when painting | a theme switch changes the pixels |
| 14 | key 3 focusing the front view | key 3 selects the 3D tab |
| 15 | the views not repainted on an edit | a typed position moves the icon |

## Risks and unknowns

- **Pixel tests are brittle.** The geometry is tested through the view's
  own mapping, `point_of(position)`, and pixels only where the point is
  what is on top. Grabs are looked at, not compared.
- **The selection's observers already do a lot**: the pane rebuilds and
  the headers repaint. A click on a canvas costs what a click on a header
  does, which the timeline already pays.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Dragging | phase 2 |
| Radius, opacity, mute, solo, the bypass strip | phase 3 |
| The 3D view | phase 4 |
| Trails | M6 |

## Outcome

Filled in at the end.
