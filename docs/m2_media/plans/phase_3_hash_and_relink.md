# Plan — M2 · Phase 3 — Content hash and relink

**Written:** 2026-09-24 · **Status:** in progress

## Approach

Two things that share one definition. The hash says whether two files hold
the same sample; relinking asks that question of a file somebody points at in
place of one that has gone. Phase 4's cache keys peaks by the same hash, so it
is defined once, here, before anything stores one.

**What is hashed is the file's bytes, not its decoded audio.** The two fail
differently, and the test the phase doc asks for — a file whose tags change
and whose audio does not — is exactly where. Hashing the audio survives a
retag. It also depends on the decoder: MP3 and Vorbis decode to slightly
different samples across library versions, and D-40 already declines to
promise the same floats on two machines, so the same sample could hash
differently on a colleague's laptop — which is the one thing a relink key and
a cache key must never do. It also costs a full decode to answer "is this the
same file". Bytes are stable everywhere, cost a streamed read, and get the
retag case wrong in the safe direction: a retagged file relinks with a notice
saying it differs, and its peaks are computed again.

SHA-256, written `sha256:<hex>` as `03`'s own example already writes it, and
read in fixed chunks so a two-gigabyte WAV costs memory for one chunk.

**Relinking replaces what the pool knows about the file, not just its path.**
Pointing a missing sample at a different file — a re-export with a fade
fixed, a WAV where there was an MP3 — is legitimate and is allowed. But the
pool's `frames`, `source_rate`, `channels` and `hash` describe the old file,
and keeping them would be the pool lying about what plays. So a relink takes
the new file's facts, and M1's `validate()` then does what it already does: a
clip that runs past the new file's end makes the edit invalid, and the relink
is refused with that reason rather than half-applied.

## Three things the phase doc leaves open

Decision rows, written in step 1 and step 2.

### A project saved before this phase is not hashed on open

Its `MediaFile.hash` is empty. Filling it on open would be an edit nobody
made — D-14 says the model changes only through the stack, and a command on
open would put an entry on the stack and a dirty mark on a project that was
just opened. It would also read every sample in full on every open, which is
N-4's budget spent on bookkeeping. So an empty hash stays empty until the
sample is next relinked or imported, and relinking against an empty hash says
it could not compare rather than claiming either answer.

### A different hash is allowed, and said

Refusing would make the re-export case impossible. Allowing it silently would
let a wrong file slip in unnoticed. So it is allowed, the report says the
audio is not the same, and the window posts a `warn` notice. The same hash is
quiet — success is.

### Where relinking lives

`core/relink.py`, one function taking the document: decode, hash, compare,
push. It needs `media.py` to read and `document.py` to edit, and belongs to
neither. `02` gains it. The window's `relink_media` is the thin front door
M8's dialog will call, and the only part with a notice in it.

## Steps

1. **The hash.** `content_hash(path) -> str | Refused` in `core/io/media.py`;
   `Decoded.media_file` takes the hash. The decision row for what is hashed,
   and for leaving old projects alone.
   *Test:* identical bytes hash identically at two paths under two names; one
   changed byte — the *last* one, past the first chunk — changes it; the same
   audio written twice with different tags hashes differently, which is the
   case that distinguishes bytes from audio; a file larger than the chunk is
   read chunk by chunk, asserted by recording the reads; the hash is in the
   saved `.3dim`, asserted by reading its text; a project saved with no hash
   opens clean and keeps none.

2. **Relinking.** `edits.Relink` — every field decoding determines, plus
   `missing`, done and undone together; `relink(document, media, path)`
   returning `Relinked` (with whether the audio is the same, different, or
   could not be compared) or `Refused`; `MainWindow.relink_media` posting the
   notices. The decision row for different hashes; `02` gains the module.
   *Test:* same hash clears `missing`, undoes back to missing and redoes;
   different hash takes the new file's facts and says so; a new file too short
   for the clips is refused and changes nothing; an undecodable file is
   refused; an empty old hash relinks, is reported as not compared, and gains
   the new hash; in the window, a different hash is one `warn`, the same hash
   is silent, a refusal is one `error`.

## Files

```
docs/01-requirements.md            amended — two decision rows
docs/doc-system.md                 amended — the D high-water mark
docs/02-architecture.md            amended — core/relink.py
docs/m2_media/phase_3_*.md         amended — Notes
src/immersive/core/io/media.py     amended — content_hash
src/immersive/core/edits.py        amended — Relink
src/immersive/core/relink.py       new
src/immersive/ui/main_window.py    amended — relink_media
tests/test_media.py                amended
tests/test_relink.py               new — headless, plus the window's notices
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| Hashing bytes, and a retag changing the hash | a retagged sample relinks with a "not the same audio" notice, and its peaks are recomputed | accepted in the decision row, and pinned by the test that distinguishes the two candidates |
| A relink that changes `frames` under existing clips | a clip reading past the end of its sample | M1's `validate()` refuses the edit, and the relink reports the reason |
| Hashing large files on the UI thread | a frozen window while a sample is read | the function is synchronous and headless; phase 6 and M8 call it from workers |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the path hashed instead of the content | the same sample under two names looks like two |
| only the first chunk hashed | an edit past the first chunk goes unseen |
| the whole file read at once | a two-gigabyte WAV costs two gigabytes to hash |
| the `sha256:` prefix dropped | a hash that cannot say what made it, and a format that cannot change algorithm |
| undoing a relink leaves `missing` cleared | Undo claims the file is back when it is not |
| a relink keeps the old `frames` | the pool lies about what plays |
| a different hash reported as the same | a wrong file slips in unnoticed |
| an empty old hash reported as different | every relink of an old project warns about nothing |
| an invalid relink raising out of `relink` | one short file breaks the dialog that asked |
| an undecodable file relinked anyway | the pool points at something that cannot play |
| the window silent on a different hash | the report exists and nobody sees it |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The relink dialog, and searching for a moved file | M8, before beta (D-84) |
| Filling hashes for old projects | nowhere, deliberately — they fill on the next relink or import |
| The peak cache the hash keys | phase 4 |

## Outcome

Filled in at the end.
