# M5 · Phase 1 — The ortho views, drawn

**Status:** in progress · **Plan:** [plans/phase_1_ortho_views.md](plans/phase_1_ortho_views.md)

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

- [ ] A channel at (1, 2, 0) is drawn 1 m right of and 2 m ahead of the
      head in the top view, and 1 m right at ear level in the front view,
      at whatever zoom and pan, within a pixel.
- [ ] A linked or free pair is two points, each where its side is, joined
      by a line in the channel's colour. A bypassed channel is not drawn.
- [ ] A click on an icon selects its channel, and a click on empty space
      clears the selection. The selected channel's icon is ringed and
      drawn over the others.
- [ ] Scroll zooms about the pointer, which keeps the metre under it in
      place, and middle-drag pans. Both stay within limits the plan sets.
- [ ] Keys 1 and 2 focus the top and front views, and 3 selects the 3D
      tab.
- [ ] The views read their colours from the theme, and a theme switch
      repaints them. Offscreen grabs of both views are recorded.

## Implements

The top and front views in *Workspace (centre)* and *The workspace is
tabbed* in [04-ui-spec.md](../04-ui-spec.md); D-49.

## Notes

Appended while building.
