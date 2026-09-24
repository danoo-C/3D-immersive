# M2 · Phase 3 — Content hash and relink

**Status:** ✅ complete · **Plan:**
[plans/phase_3_hash_and_relink.md](plans/phase_3_hash_and_relink.md)

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

- [x] Identical content hashes identically wherever it lives and whatever it
      is called; changing one byte of audio changes the hash.
- [x] The rule for what is hashed is written down with its reason, and a test
      pins the case that distinguishes the two candidates — a file whose tags
      change but whose audio does not.
- [x] Hashing a file larger than the read chunk streams it, asserted by a test
      that would fail if the whole file were read at once.
- [x] The hash is in the `.3dim`, asserted by reading the saved file's text
      rather than by a round trip — M1 phase 5's lesson that a round trip
      proves only that the reader and writer agree.
- [x] A project written before this phase — no hash, or an empty one — still
      opens. Whether and when its hash is filled in is decided, and it does
      not silently mark a freshly opened project as unsaved.
- [x] Relinking a missing file to one with the same hash clears `missing`, is
      undoable, and redoes.
- [x] Relinking to a file with a different hash behaves as the plan decides,
      and says so through a notice rather than silently.

## Implements

F-3 (relinking, model side), D-59 (the key), D-72 — `MediaFile.hash` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Every sample can now say what it is, and a missing one can be pointed at a
file that is here.** Two steps, three decisions, and the rules all asserted
without a window.

### D-88: the bytes, and the test that shows the trade

The hash is SHA-256 of the file's bytes, written `sha256:<hex>`. The phase doc
asked for the test that tells the two candidates apart, and it is the most
useful test in the phase: the same samples written twice under two titles
decode to identical audio and hash differently. That is the price of a key
that means the same file on every machine — decoded MP3 differs across
decoder versions, and D-40 already declines to promise the same floats twice
— and it errs the safe way: a retagged file relinks with a notice, and its
peaks are computed again.

### D-89: old projects are left alone

A project saved before this phase keeps its empty hashes, and opening it
neither fills them nor marks it unsaved. Filling them would be an edit nobody
made, and a full read of every sample on every open. Relinking against an
empty hash answers *could not compare* rather than guessing.

### D-90: a relink replaces everything the file determines

Different audio is allowed and is a `warn`; the same audio is quiet. The pool
entry takes the new file's path, name, hash, rate, channels and length
together, and a file too short for the clips that use it needs no rule of its
own — M1's `validate()` refuses the edit and the relink reports
`validate()`'s own words. Nothing about relinking needed a new invariant; it
needed the existing one to be reached.

### What the mutation sweep found

Thirteen mutations, twelve killed on the first run. The survivor was the
relink command's promise to clear `missing`: `relink()` only ever hands it an
entry fresh from decoding, which is never missing, so no test through
`relink()` could tell clearing from copying. A replacement built any other
way would have carried `missing` in, so the command's contract is now tested
on its own.
