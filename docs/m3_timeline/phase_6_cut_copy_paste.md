# M3 · Phase 6 — Cut, copy and paste

**Status:** not started · **Plan:** not written yet

## Goal

`Ctrl+X`, `Ctrl+C` and `Ctrl+V` move and copy clips within a channel and
between channels (F-50). A paste lands at the playhead on the selected
channel and keeps the clips' spacing. Clips copied from several channels
paste onto that many channels, starting at the selected one. This is the
arranging gesture D-58 kept in v1: taking a phrase from one channel to
another.

## Scope

**In:** the clipboard and what it holds, as the plan decides for a paste
into a project that lacks a clip's sample; cut, copy and paste as commands,
each one undoable step; fresh ids for pasted clips; the spacing between
clips, in time and across channels, kept; a paste over existing clips
following the drop rule — the clip underneath is trimmed; Edit › Cut, Copy
and Paste enabled exactly when they can act.

**Out:** the system clipboard and other applications — nothing outside this
one reads clips. Duplicating in place → phase 5, which has `Ctrl+D`.
Copying automation along with clips → M6, if at all.

## Acceptance

- [ ] Copy and then paste creates new clips with fresh ids at the playhead
      on the selected channel, keeping their spacing, and leaves the originals
      untouched.
- [ ] Cut removes the selection in one command, and a paste afterwards
      brings the clips back at the playhead.
- [ ] Clips copied from several channels paste onto consecutive channels
      from the selected one down, and what happens past the last channel is
      what the plan decides.
- [ ] A paste over existing clips trims them so nothing overlaps, and
      `model.validate()` is clean afterwards.
- [ ] One Undo removes everything one paste added.
- [ ] No paste creates a clip whose `media_id` names nothing in the
      project.
- [ ] Cut, Copy and Paste are enabled exactly when they can act, and their
      tooltips no longer name M3.

## Implements

F-50, D-58 — *Keyboard* and *Selection* in
[04-ui-spec.md](../04-ui-spec.md), *Ids* and *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
