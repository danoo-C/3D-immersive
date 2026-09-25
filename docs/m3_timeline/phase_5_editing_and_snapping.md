# M3 · Phase 5 — Editing clips, and snapping

**Status:** in progress · **Plan:**
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

- [ ] Dragging a selected clip moves every selected clip by the same amount,
      in one command on release.
- [ ] Dragging either edge trims the clip; it never reaches past its
      sample's start or end, nor shrinks below the plan's minimum length; one
      command on release.
- [ ] `S` splits every selected clip under the playhead into two clips whose
      samples, played end to end, are the original's — asserted on offsets
      and lengths, and by reading the samples themselves.
- [ ] `Ctrl+D` duplicates the selection and `Delete` removes it, each one
      command.
- [ ] No gesture leaves two clips overlapping: a move onto a neighbour does
      what the plan decides, and `model.validate()` is clean after every
      edit.
- [ ] Every edge a gesture moves lands on the nearest grid line or clip edge
      (F-17), under the channel's override where there is one (F-18); with
      `Alt` held it lands exactly under the cursor.
- [ ] The snap chip chooses every division F-16 names, and off, as one
      undoable edit; a header's indicator sets and clears that channel's
      override, and shows which is in force.
- [ ] Edit › Split, Duplicate and Delete are enabled exactly when the
      selection holds clips, and their tooltips no longer name M3.
- [ ] No source file is written: after a session of edits every sample's
      bytes hash as they did before it (F-14).

## Implements

F-14, F-16, F-17, F-18, F-51 — *Timeline* and *Keyboard* in
[04-ui-spec.md](../04-ui-spec.md), *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
