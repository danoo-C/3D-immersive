# M5 · Phase 2 — Dragging, heard

**Status:** in progress · **Plan:** [plans/phase_2_dragging.md](plans/phase_2_dragging.md)

## Goal

A source is dragged around the head and heard moving while it is dragged.
Dragging an icon in the top view sets its X and Y, and in the front view
its X and Z. The engine hears each movement at the next block, through
its command ring, and the release makes one edit and one undo step. Esc
puts the source back. The parameters pane's position fields follow the
drag as it goes, and a value typed there moves the icon. A pair is dragged
by either side. A linked pair's other side follows in its mirror, and the
side grabbed leads.

## Scope

**In:** dragging icons in both views; a position heard before it is an
edit; one edit per drag; Esc; the pane following; pairs dragged by either
side; the pivot, if the plan draws it.

**Out:** dragging during a take recorded as automation → M6. Snapping to
a grid → later, if asked for.

## Acceptance

- [ ] Dragging an icon moves the channel's position on the view's two axes
      and leaves the third alone, by the metres the pointer moved.
- [ ] While the transport plays, each movement is heard at the next block,
      before the release, and no edit is made until it.
- [ ] The release is one edit and one undo step, however far the drag
      went. Esc puts the source back where it was, and is heard there.
- [ ] The pane's position fields show the dragged position while the drag
      goes on, and a value typed in them moves the icon.
- [ ] A linked pair dragged by its right side moves the right side under
      the pointer and the left in its mirror. A free pair's side moves
      alone.

## Implements

*Drag an icon* in [04-ui-spec.md](../04-ui-spec.md)'s top and front
views; *Undo* in [02-architecture.md](../02-architecture.md); D-105,
D-121, D-132.

## Notes

Appended while building.
