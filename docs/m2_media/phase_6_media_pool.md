# M2 · Phase 6 — The media pool

**Status:** not started · **Plan:** not written yet

## Goal

File › Import Audio… takes files or a folder and fills the explorer's media
pool: a tree of what was imported, each row with its name, duration and
waveform thumbnail, a filter box above it, and rows that can be dragged. The
decoding happens off the UI thread, every file that could not be read is
reported, and the whole import is one edit that one Undo takes back.

This is the phase the milestone's acceptance can first be seen in, short of
the sound.

## Scope

**In:** importing files and folders, a folder recursively; decode, hash and
peaks on workers so the window keeps responding (N-3); the command that adds
media to the pool, one per import; the tree, mirroring the folders beneath
what was imported; the filter; each row's name, duration and thumbnail; the
drag *source*, and the MIME type it carries, named in `04` so M3 can accept
it; missing files drawn in `warn`; importing the same audio twice; the theme
groups `04` gives M2 — tree view, header and filter field.

**Out:** the drop target → M3. The relink action on a missing row → M8,
before beta. Removing media from the pool — the plan decides whether it
belongs here; nothing in the acceptance needs it. The parameters pane's media
view, which arrives with the pane.

## Acceptance

- [ ] Importing a folder of *n* readable files adds *n* `MediaFile`s in one
      undoable step. One Undo removes all *n*; Redo restores them without
      decoding again.
- [ ] The tree mirrors the folder structure beneath the imported folder.
- [ ] Each row shows its name, duration and waveform thumbnail.
- [ ] The filter narrows rows by name, ignores case, and keeps the folders
      that lead to a match.
- [ ] During the import of a folder large enough to take seconds, the UI
      thread keeps turning — asserted by a timer that keeps firing, not by
      the import merely finishing.
- [ ] A file that cannot be decoded is not added, and the import posts **one**
      notice whose detail lines name each failure and its reason.
- [ ] Importing audio already in the pool does what the plan decides, and
      says so rather than silently adding a duplicate.
- [ ] Dragging a row produces the MIME type `04` names, carrying the media's
      id.
- [ ] The groups tree view, header and filter field are in `04` and the
      bundled theme, and no widget in the pool names a hex.
- [ ] A screenshot of a real imported folder is taken and looked at.

## Implements

F-3, F-4, F-5, F-7, F-9, F-56, N-3 — *Media pool* in
[04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.
