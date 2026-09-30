# M5 · Phase 2 — Dragging, heard

**Status:** ✅ · **Plan:** [plans/phase_2_dragging.md](plans/phase_2_dragging.md)

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

- [x] Dragging an icon moves the channel's position on the view's two axes
      and leaves the third alone, by the metres the pointer moved.
      *`test_dragging_sources.py`, pressed off the icon's centre.*
- [x] While the transport plays, each movement is heard at the next block,
      before the release, and no edit is made until it. *The engine's
      ring read in `test_fields_heard.py`.*
- [x] The release is one edit and one undo step, however far the drag
      went. Esc puts the source back where it was, and is heard there.
      *In the window too, where Esc is also Stop; see the Notes.*
- [x] The pane's position fields show the dragged position while the drag
      goes on, and a value typed in them moves the icon.
- [x] A linked pair dragged by its right side moves the right side under
      the pointer and the left in its mirror. A free pair's side moves
      alone. *Looked at; see the Notes.*

## Implements

*Drag an icon* in [04-ui-spec.md](../04-ui-spec.md)'s top and front
views; *Undo* in [02-architecture.md](../02-architecture.md); D-105,
D-121, D-132.

## Notes

Appended while building.

**Built (2026-09-30)** in four steps: `Placing`, the feed's preview,
dragging in the views, and one `Placing` in the window for the views, the
pane and the feed. The pivot is not drawn. It is typed in the pane, and
dragging it waits until it is asked for.

**Esc is also the window's Stop.** The views' own tests pressed Esc on a
view and passed, but in the window the Stop shortcut took the key first,
so a drag was never dropped. The sweep found it: a cancel not sent back to
the engine survived, because no window test ever cancelled. A view now
claims Esc from Stop while the mouse is held, as the timeline's drags do,
and only then. After a click or a drag, Esc is Stop's again.

**An edit made during a drag drops it.** The window's keys still work
while the mouse is held, so Ctrl+Z or Delete can change the model under a
drag. The release would then have pushed an edit placed against a model
that had since changed, onto a channel that might be gone. Any edit the
document reports while a view's press is held now drops the drag, as Esc
does. The release ends its press before it pushes its own edit.

**The heard test counts from before the release.** Every edit sends the
engine the loop and repeat commands, so the release is never silent. The
test reads the engine's ring from the drag's start and asks that no
`POSITION` command follows the release. The engine already had the
position.

**The release pushes, then clears.** Clearing first would tell the feed
the drag had ended while the model still had the old position, and the
engine would be sent back there for a block before the edit arrived.

**Looked at.** A linked pair dragged by its right side, in both views at
once: the right under the pointer, the left in its mirror, and the front
view following before the release. A point beside it did not move.
