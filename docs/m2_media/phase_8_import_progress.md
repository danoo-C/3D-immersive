# M2 · Phase 8 — Import progress

**Status:** planned · **Plan:**
[plans/phase_8_import_progress.md](plans/phase_8_import_progress.md)

## Goal

While samples are being prepared, the media pool says so. A strip at its top
reads *Importing 7 of 22 files* or *Loading 7 of 22 samples*, with a bar that
moves as the files' bytes are read, not only when whole files finish. An
import has a ✕ that drops it. Opening another project stops a load that is
still running and loads the new project's samples. And if the measurement
this phase starts with says so, each file is read once rather than twice.

## Scope

**In:** progress reported from the workers, through `prepare`, without Qt;
reading in chunks, so progress moves within a file and a cancel takes effect
at the next chunk; the importer's progress and cancel; the strip in the
pool, its delay and its theme group; the Import actions disabled while one
runs; a load stopped by a newer open; a measured 22-stem import; and reading
each file once, if the measurement shows the second read costs enough to be
worth it.

**Out:** rows appearing one by one as files finish. An import stays one edit
(D-113), and D-113 says why. A cache of decoded audio, so that opening a
project does not decode everything again: it would cost disk space on the
order of the samples themselves, and it is a question of its own. Limiting how
many files are prepared at once is in only if the measurement shows that
fewer workers are faster, as they may be on the Windows drive. Progress for
relinking, which is still synchronous: its dialog is M8's.

## Acceptance

- [ ] An import that runs longer than 0.25 s shows *Importing n of N files*,
      a bar and ✕ at the top of the pool, and the strip is gone once the
      import has landed. An import shorter than that shows nothing.
- [ ] The bar moves within a file: one large file's import reports progress
      strictly between 0 and 1 before it finishes.
- [ ] The bar counts bytes. When a small and a large file are imported and
      only the small one is done, the bar stands at the small file's share
      of the bytes.
- [ ] ✕ cancels the import: nothing is added, no notice is posted, and the
      undo stack is unchanged. Files not yet started never run, and a file
      being prepared stops at its next chunk.
- [ ] While an import runs, *Import Audio…* and *Import Folder…* are
      disabled, and their tooltips say an import is running.
- [ ] Opening a project shows *Loading n of N samples*, with no ✕. Opening
      another project while that load runs stops it, and the second
      project's samples load.
- [ ] Reading in chunks decodes to exactly the samples a single read gives,
      for every format F-5 names.
- [ ] `progress` is in `04` and the bundled theme, and the strip names no hex.
- [ ] A 22-stem import is timed stage by stage, on the Linux filesystem and
      on the Windows drive under WSL, and the numbers are recorded in the
      Notes, along with whether reading once was kept, judged by the plan's
      criterion.
- [ ] A screenshot of the strip part-way through a real import is taken and
      looked at.

## Implements

F-59, N-3, D-113, D-114 — *Media pool* in
[04-ui-spec.md](../04-ui-spec.md), the threading table in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.
