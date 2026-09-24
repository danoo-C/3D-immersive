# Plan — M2 · Phase 6 — The media pool

**Written:** 2026-09-24 · **Status:** in progress

## Approach

Everything the first five phases built, joined up and put on screen. Four
layers, each testable without the one above it:

1. **Preparing one file, headless.** `prepare(path)` = decode, hash, peaks —
   phases 2, 3 and 4 in one call, returning everything the session needs to
   keep or a `Refused`. It runs on a worker, so it touches no Qt.
2. **Keeping what was prepared.** A `MediaStore` holds each sample's decoded
   audio and pyramid by media id, for the session. It is not the model:
   nothing in it is saved, and phase 7's audition and M3's playback read
   audio from it. It is also what makes Redo of an import free — undoing an
   import removes the entries from the pool, not their audio from the store,
   so Redo puts back what is already decoded.
3. **Importing on workers.** A `QThreadPool` prepares files in parallel and
   hands results back to the UI thread by signal, where — and only where —
   the model is edited (02's threading table). One import is one `AddMedia`
   command: one Undo takes back a folder of forty. Failures are one notice
   with a line per file, as `04` already says a report should be.
4. **The pool on screen.** A tree whose folders mirror the folders beneath
   what was imported, a row per sample with its name, duration and
   thumbnail, a filter above it, and rows that drag.

## Three things the phase doc leaves open

A decision row for the first two, written in step 1; the third goes in `04`.

### What in a folder is tried

Only files whose suffix is one of F-5's formats — `.wav`, `.wave`, `.aif`,
`.aiff`, `.aifc`, `.flac`, `.ogg`, `.oga`, `.mp3`, in any case. Everything
else in the folder is passed over without a word. A sample folder holds
readmes, cover art and `.DS_Store`, and a notice listing each of those as a
failure would bury the one WAV that really did not open.

### Importing what is already there

Audio whose hash is already in the pool is not added again, and the import's
notice says how many were already there. Two entries for one sample would be
two rows that are the same thing, and a relink of one that silently leaves
the other stale.

### The drag's MIME type

`application/x-3dimmersive-media`, carrying a JSON list of media ids. Named
in `04` so M3's timeline has a contract to accept rather than a guess.

## Steps

1. **Preparing, and keeping.** `core/media_store.py`: `prepare(path)`,
   `Prepared`, `MediaStore`, `find_audio(folder)`. `edits.AddMedia` for
   several entries at once. The decision row; `02` gains the module.
   *Test:* `find_audio` recurses, sorts, keeps F-5's suffixes in any case and
   ignores everything else; `prepare` fills every `MediaFile` field and the
   store; `AddMedia` of *n* entries is one undo and redoes the same objects.

2. **Importing on workers.** `ui/importer.py`; File › Import Audio… for files
   and Import Folder… for a folder; the window's `import_paths`.
   *Test:* a folder of *n* readable files is *n* entries in one undoable
   step, and Redo decodes nothing; a timer keeps firing on the UI thread
   while a large import runs (N-3); undecodable files are one notice with a
   line each; audio already in the pool is not added again and is counted in
   the notice; a folder with nothing importable in it says so.

3. **The pool on screen.** `ui/explorer/media_pool.py` in place of the
   placeholder: the tree, the columns, a thumbnail delegate painting with the
   waveform widget's own drawing, the filter, missing rows in `warn` with a
   glyph, and the drag. The MIME type in `04`.
   *Test:* the tree mirrors the folders; each row shows name, duration and a
   thumbnail; the filter ignores case and keeps the folders that lead to a
   match; a missing row is `warn` and says so in text; a drag carries the
   named type and the ids; the pool follows Undo and Redo.

4. **An opened project's samples load too.** *Added while building step 3.*
   The store is filled only by imports, so a project opened from disk showed
   blank thumbnails and — at phase 7 — would play nothing. Opening now
   prepares the samples that are present on the same workers, into the store
   and not the model: no edit, no dirty mark, no hash written (D-89).
   *Test:* a saved project reopened shows thumbnails; opening marks nothing
   unsaved; a sample that fails to load is reported once; missing samples
   are not tried.

5. **Its theme groups, and a fixture retired.** `tree`, `header` and
   `filter` in `app.qss`, the bundled theme and `04`'s ownership table. M9's
   golden stylesheet fixture retires here, as its docstring says it would the
   first time a milestone legitimately changed the sheet. A screenshot of a
   real imported folder, looked at.
   *Test:* the vocabulary tests already cover new stylesheet groups; no
   widget in the pool names a hex.

## Files

```
docs/01-requirements.md                    amended — the decision row
docs/doc-system.md                         amended — the D high-water mark
docs/02-architecture.md                    amended — media_store, importer
docs/04-ui-spec.md                         amended — the MIME type, the groups
docs/m2_media/phase_6_*.md                 amended — Notes
src/immersive/core/media_store.py          new
src/immersive/core/edits.py                amended — AddMedia
src/immersive/ui/importer.py               new
src/immersive/ui/explorer/media_pool.py    new
src/immersive/ui/widgets/waveform.py       amended — drawing shared with the delegate
src/immersive/ui/main_window.py            amended — actions, the pool
src/immersive/assets/app.qss               amended — tree, header, filter
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — the groups
tests/test_media_store.py                  new — headless
tests/test_import.py                       new — gui
tests/test_media_pool.py                   new — gui
tests/test_theme.py                        amended — the golden fixture retired
tests/fixtures/stylesheet_before_m9.qss    removed
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A worker touching the model or a widget | a crash that happens one import in fifty | workers receive a path and return a value; the only code that edits is the slot on the UI thread, and a test asserts the result arrives on the main thread |
| Tests racing the workers | a flaky suite | a helper turns the event loop until the importer reports finished, with a timeout that fails loudly |
| Memory: the store holds every sample decoded | 115 MB per five minutes of stereo | the roadmap says hold it in RAM; recorded, and M3's question to revisit |
| The GIL making "on a worker" a formality | a frozen window during import after all | the N-3 test is a timer firing, not a claim; numpy, soxr and libsndfile release the GIL for the heavy parts |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `find_audio` not recursive | a folder of folders imports nothing |
| `find_audio` trying every file | a readme reported as a failure |
| an import as one command per file | forty undos for one import |
| Redo decoding again | the store is not doing its job |
| preparing on the UI thread | the window freezes for the length of the import |
| a failed file added anyway | a pool entry that cannot play |
| a notice per failure | one import raises the count by every bad file |
| a duplicate added twice | two rows that are one sample |
| the tree flat | the folders the person organised their samples in, lost |
| the filter case-sensitive | "Kick" does not find `kick.wav` |
| the filter dropping the folders of a match | a match with no way to see where it lives |
| the drag without the MIME type | M3 has nothing to accept |
| a missing row not in `warn` | a sample that cannot play looks like one that can |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Double-click to hear | phase 7 |
| The drop target | M3 |
| Removing media from the pool | nothing needs it yet; M3's clips make removal a real question |
| Relinking from a pool row | M8, before beta |
| Import progress beyond "importing…" | nothing asks for a progress bar; the notice at the end is the report |

## Outcome

Filled in at the end.
