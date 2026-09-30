# M5 · Phase 4 — The 3D view

**Status:** ✅ · **Plan:** [plans/phase_4_view3d.md](plans/phase_4_view3d.md)

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

- [x] A source at a known position is drawn where the projection puts it,
      within a pixel, and above the grid by its height. *D-148's formula;
      the drop line meets the ground straight below it.*
- [x] Sources are drawn back to front, so a nearer one covers a farther
      one. *And the head covers what is behind it.*
- [x] The view takes no mouse input that changes anything, and an
      offscreen grab is recorded. *Looked at; see the Notes.*

## Implements

*3D view — read-only* in [04-ui-spec.md](../04-ui-spec.md); D-49.

## Notes

Appended while building.

**Built (2026-09-30)** in three steps: the projection and its fit, the
drawing, and the view in its tab. The icons are drawn by one `draw_icon`
that the ortho views now share, so the two cannot disagree about a
glow, an opacity or a letter.

**The first grab showed the scene small.** The fit kept room for heights
of R above and below the ground, which only a source R high at the
ground's far corner needs, so the ground took a third of the view. Up and
down it now fits the sources farthest up and down the screen, in steps of
a quarter of R, so it still holds still while a source moves. 04 says so.

**A source at ear level has no drop line.** Its icon covers its own foot,
which showed through a faint icon as a stray dot.

**Looked at.** Standalone: a linked pair ahead, a source high on the
right, one behind and low hanging under the ground, one high and ahead,
a quiet one behind, and one in line with the head and nearer the camera,
which covers it. In the window's tab with R at 8: a solo glowing, the
silenced at a quarter, the selected ringed, and a bypassed channel
absent.
