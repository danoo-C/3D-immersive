# M2 · Phase 3 — Content hash and relink

**Status:** not started · **Plan:** not written yet

## Goal

Every `MediaFile` carries a hash of its content, and a file that has gone
missing can be pointed at a new path by an undoable command that checks it is
the same audio. The hash is also what phase 4's cache is keyed by, so it is
defined once, here, before anything depends on it.

M8 hangs a dialog off the missing-media notice. This phase builds what that
dialog will call.

## Scope

**In:** what is hashed — the bytes on disk or the decoded audio — and with
which algorithm; hashing a large file without holding it all in memory
twice; `MediaFile.hash` filled on import and written to the `.3dim` (the field
exists since M1); a relink command that replaces a `MediaFile`'s path, clears
`missing`, and is undone and redone like any other edit; what relinking to a
file with a *different* hash does.

**Out:** the relink dialog, and any search for the moved file → M8, before
beta (D-84). The cache the hash keys → phase 4. Importing → phase 6.

## Acceptance

- [ ] Identical content hashes identically wherever it lives and whatever it
      is called; changing one byte of audio changes the hash.
- [ ] The rule for what is hashed is written down with its reason, and a test
      pins the case that distinguishes the two candidates — a file whose tags
      change but whose audio does not.
- [ ] Hashing a file larger than the read chunk streams it, asserted by a test
      that would fail if the whole file were read at once.
- [ ] The hash is in the `.3dim`, asserted by reading the saved file's text
      rather than by a round trip — M1 phase 5's lesson that a round trip
      proves only that the reader and writer agree.
- [ ] A project written before this phase — no hash, or an empty one — still
      opens. Whether and when its hash is filled in is decided, and it does
      not silently mark a freshly opened project as unsaved.
- [ ] Relinking a missing file to one with the same hash clears `missing`, is
      undoable, and redoes.
- [ ] Relinking to a file with a different hash behaves as the plan decides,
      and says so through a notice rather than silently.

## Implements

F-3 (relinking, model side), D-59 (the key), D-72 — `MediaFile.hash` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
