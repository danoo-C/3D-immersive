# M3 · Phase 5 — Editing clips, and snapping

**Status:** ✅ complete · **Plan:**
[plans/phase_5_editing_and_snapping.md](plans/phase_5_editing_and_snapping.md)

## Goal

Selected clips can be moved by their body, trimmed from either edge, split
at the playhead, duplicated and deleted. Each gesture is one undoable edit
that never touches a source file. Every gesture that moves an edge snaps it
to the grid and to other clips' edges, under the channel's snap override if
it has one, and not at all while `Alt` is held. The toolbar's snap chip
chooses the division, and a channel header's indicator sets that channel's
override.

## Scope

**In:** moving, as the plan decides for a neighbour in the way and for a
drag across lanes; trimming either edge, never past the sample's own start
or end (`offset + length` within `MediaFile.frames`); splitting at the
playhead (`S`) into two clips that play the same samples as the one they
replace; duplicating (`Ctrl+D`); deleting; every verb taking the whole
selection (F-51); one command per gesture, coalesced on release (*Undo* in
[02](../02-architecture.md)); snapping to the grid and to clip edges, nearest
wins (F-16, F-17, and `core.time.snap`); the channel override (F-18); `Alt`;
the snap chip as a live control, choosing 1/1 to 1/32, straight or triplet,
or off, as one undoable project edit; Edit › Split, Duplicate and Delete
enabled.

**Out:** cut, copy and paste → phase 6. Clip gain and fades → phase 7.
Shift+drag bringing automation along (D-7) → M6.

## Acceptance

- [x] Dragging a selected clip moves every selected clip by the same amount,
      in one command on release.
- [x] Dragging either edge trims the clip; it never reaches past its
      sample's start or end, nor shrinks below the plan's minimum length; one
      command on release.
- [x] `S` splits every selected clip under the playhead into two clips whose
      samples, played end to end, are the original's — asserted on offsets
      and lengths, and by reading the samples themselves.
- [x] `Ctrl+D` duplicates the selection and `Delete` removes it, each one
      command.
- [x] No gesture leaves two clips overlapping: a move onto a neighbour does
      what the plan decides, and `model.validate()` is clean after every
      edit.
- [x] Every edge a gesture moves lands on the nearest grid line or clip edge
      (F-17), under the channel's override where there is one (F-18); with
      `Alt` held it lands exactly under the cursor.
- [x] The snap chip chooses every division F-16 names, and off, as one
      undoable edit; a header's indicator sets and clears that channel's
      override, and shows which is in force.
- [x] Edit › Split, Duplicate and Delete are enabled exactly when the
      selection holds clips, and their tooltips no longer name M3.
- [x] No source file is written: after a session of edits every sample's
      bytes hash as they did before it (F-14).

## Implements

F-14, F-16, F-17, F-18, F-51 — *Timeline* and *Keyboard* in
[04-ui-spec.md](../04-ui-spec.md), *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**A move overwrites, and a trim stops (D-97, D-98).** The two questions
this phase was left were settled before any code. A move lifts the moved
clips first, then lands them by the drop's rule. It crosses lanes, and the
whole selection keeps its shape. A trim stops at the neighbour, at its
sample's ends and at 64 samples, two implicit fades end to end. Ableton
overwrites on a trim; that is the decision to reverse if it is missed.

**One settling, three callers.** `DropClips`'s way of making room moved
into a function the move and the duplicate share. The before-and-after
bookkeeping moved into a base class, so every new command only works out
its lists and placings. Eight seeds of two hundred random edits go through
the stack, which refuses anything invalid; none is refused, and undoing
them all gives back an equal project.

**A drag is a preview, not a gesture.** At every movement the view builds
the command the release would push and draws the clips where it would
leave them. So what is shown is what is pushed, and `Esc` has nothing to
undo. A live edit inside a gesture would have trimmed and restored the
neighbours at every mouse event. With 500 clips, 20 of them dragged, a
movement takes 1.9 ms (median, worst 10.7 ms).

**The split is checked on samples, read from an array** standing for the
decoded sample: head and tail, end to end, are exactly the original's. F-14
is checked on real files. Two WAVs are hashed, imported, and put through a
drag, a trim, a split, a duplicate, a delete, every undo and redo, and a
save. They hash the same after.

**A Ctrl+press that toggles a clip out drags nothing.** Not even the rest
of the selection, which a first test could not tell, having nothing else
selected.

**Looked at.** A move across lanes, drawn in the new lanes' colours before
the release, then trimming and splitting what it lands on; a trim held at
its sample's end; the Pad's override brighter than the other headers'
`snap`. The snap chip, now the window's first focusable widget, opened
with the accent focus ring and took the initial focus from the pool's
filter. It is out of the focus chain now, like the toolbar's own buttons.

The phase adds 100 tests. The suite is 1717: 17.2 s serially, 6.5 s in
parallel, 3.4 s in the fast lane.
