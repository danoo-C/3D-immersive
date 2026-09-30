# M5 · Phase 4 — The 3D view

**Status:** not started · **Plan:** not written yet

## Goal

The workspace's second tab shows the scene from a fixed isometric camera,
drawn with `QPainter` under an orthographic projection. It shows the head,
a ground grid, and every placed source with its icon's radius and opacity,
a pair as its two points. It has no controls, because it is for reading
the scene and for screen recordings, and nothing in it can be knocked out
of place mid-take.

## Scope

**In:** the isometric projection; the head, the grid and the sources; the
icons' rules from phase 3; redrawing on project, selection and theme
changes.

**Out:** trails → M6. A camera, or a GL scene → not in v1.

## Acceptance

- [ ] A source at a known position is drawn where the projection puts it,
      within a pixel, and above the grid by its height.
- [ ] Sources are drawn back to front, so a nearer one covers a farther
      one.
- [ ] The view takes no mouse input that changes anything, and an
      offscreen grab is recorded.

## Implements

*3D view — read-only* in [04-ui-spec.md](../04-ui-spec.md); D-49.

## Notes

Appended while building.
