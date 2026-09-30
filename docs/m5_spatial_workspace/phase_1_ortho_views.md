# M5 · Phase 1 — The ortho views, drawn

**Status:** ✅ · **Plan:** [plans/phase_1_ortho_views.md](plans/phase_1_ortho_views.md)

## Goal

The workspace's first tab shows the top view (X/Y) and the front view
(X/Z) in place of their placeholders. Each has the head at its centre,
facing up-screen in the top view and out of the screen in the front view.
The top view has distance rings every metre, labelled, and the front view
a line at ear level. Every channel that is not bypassed is an icon in its
own colour where its position puts it, and a stereo pair is its two
points, joined. A click on an icon selects its channel, and the selected
channel is ringed and drawn in front. Scroll zooms and middle-drag pans.
Keys 1 and 2 focus the views, and 3 shows the 3D tab.

## Scope

**In:** one ortho view class for both axes; the head glyph, rings, labels
and ear-level line; icons and pairs from the model; selection by click
and shown from the selection; zoom and pan; keys 1 to 3; the views' theme
tokens; redrawing when the project, the selection or the theme changes.

**Out:** dragging → phase 2. Radius by distance, opacity by gain, mute and
solo, the bypass strip → phase 3. The 3D view → phase 4.

## Acceptance

- [x] A channel at (1, 2, 0) is drawn 1 m right of and 2 m ahead of the
      head in the top view, and 1 m right at ear level in the front view,
      at whatever zoom and pan, within a pixel. *`test_ortho_view.py`.*
- [x] A linked or free pair is two points, each where its side is, joined
      by a line in the channel's colour. A bypassed channel is not drawn.
- [x] A click on an icon selects its channel, and a click on empty space
      clears the selection. The selected channel's icon is ringed and
      drawn over the others.
- [x] Scroll zooms about the pointer, which keeps the metre under it in
      place, and middle-drag pans. Both stay within limits the plan sets.
      *2 m to 200 m across (D-143).*
- [x] Keys 1 and 2 focus the top and front views, and 3 selects the 3D
      tab.
- [x] The views read their colours from the theme, and a theme switch
      repaints them. Offscreen grabs of both views are recorded. *Looked
      at; see the Notes.*

## Implements

The top and front views in *Workspace (centre)* and *The workspace is
tabbed* in [04-ui-spec.md](../04-ui-spec.md); D-49.

## Notes

Appended while building.

**Built (2026-09-30)** in four steps: the shared scale, the view drawn,
selecting, and the views in the window.

**The front view has lines of height.** The first grab of it showed
nothing to judge height by but the ear-level line, and height is what the
front view is for dragging. So it draws a faint line every metre of height,
labelled, as the top view draws rings, and ear level is stronger. 04's
front view says so. The same grab showed a source at the listener's own
position covering the head glyph, which is where it is, and is left so.

**Looked at.** Grabs of both views with a linked pair, a free pair, two
points, a source in the centre, a selected channel and a bypassed one; and
of the whole window, where the selected channel is ringed in both views and
marked in its header and the pane at once.

**What D-143 shares.** Metres across a view's shorter side, not pixels per
metre, so "8 m across" holds in each view whatever its size. Two views of
the same size, as the splitter starts them, are then the same scale in
pixels too.
