# M2 · Phase 8 — Import progress, in the info box

**Status:** planned · **Plan:**
[plans/phase_8_import_progress.md](plans/phase_8_import_progress.md)

## Goal

Anything slow can say so in one place: an **info box** at the right end of
the transport toolbar, which any piece of work can use by beginning an
*activity* with a label, a value and a maximum (D-116). Importing and loading
samples are the first two users. While samples are being prepared the box
reads *Importing 7 of 22 files* or *Loading 7 of 22 samples*, with a bar
that moves as the files' bytes are read, not only when whole files finish
(D-113). An import has a ✕ that drops it (D-114). Opening another project
stops a load that is still running and loads the new project's samples. And
if the measurement this phase starts with says so, each file is read once
rather than twice.

## Scope

**In:**
- the activity model, Qt-free, and the info box that shows it: its place,
  its delay, a ✕ for work that can be cancelled, *+n more*, and its theme
  group;
- progress reported from the workers through `prepare`, without Qt;
- reading in chunks, so progress moves within a file and a cancel takes
  effect at the next chunk;
- the importer's progress and cancel;
- the Import actions disabled while an import runs;
- a load stopped by a newer open;
- a measured 22-stem import, and reading each file once if the measurement
  shows the second read costs enough to be worth it.

**Out:**
- **Other users of the box.** Render is M7's (F-37), the HRTF cache M4's,
  and relinking M8's. The box is built for them, and they begin their own
  activities when they arrive.
- **Rows appearing one by one** as files finish. An import stays one edit,
  and D-113 says why.
- **A cache of decoded audio**, so that opening a project does not decode
  everything again. It would cost disk space on the order of the samples
  themselves, and it is a question of its own.
- **Fewer workers than cores** is in only if the measurement shows it is
  faster, as it may be on the Windows drive.

## Acceptance

- [ ] An activity begun with a label and a maximum, and updated, shows that
      label and that value of that maximum in the info box. A maximum of 0
      shows busy, with no measure. Finishing it empties the box.
- [ ] Nothing shows for an activity finished within 0.25 s; one still
      running at 0.25 s shows then.
- [ ] With two activities running, the box shows the one begun first and
      *+1 more*, and its tooltip names both. A ✕ shows only for an activity
      begun with a cancel, and clicking it calls that cancel.
- [ ] The box sits at the right end of the transport toolbar, and showing
      or hiding it moves nothing else in the toolbar.
- [ ] An import that runs longer than 0.25 s shows *Importing n of N files*
      and a ✕ in the box, until it has landed.
- [ ] The bar moves within a file: one large file's import reports progress
      strictly between 0 and 1 before it finishes.
- [ ] The bar counts bytes. When a small and a large file are imported and
      only the small one is done, the bar stands at the small file's share
      of the bytes.
- [ ] The ✕ cancels the import: nothing is added, no notice is posted, and
      the undo stack is unchanged. Files not yet started never run, and a
      file being prepared stops at its next chunk.
- [ ] While an import runs, *Import Audio…* and *Import Folder…* are
      disabled, and their tooltips say an import is running.
- [ ] Opening a project shows *Loading n of N samples* with no ✕. Opening
      another project while that load runs stops it, and the second
      project's samples load.
- [ ] Reading in chunks decodes to exactly the samples a single read gives,
      for every format F-5 names.
- [ ] `info` is in `04` and the bundled theme, and the box names no hex.
- [ ] A 22-stem import is timed stage by stage, on the Linux filesystem and
      on the Windows drive under WSL. The numbers are recorded in the Notes,
      along with whether reading once was kept, judged by the plan's
      criterion.
- [ ] A screenshot of the box part-way through a real import is taken and
      looked at.

## Implements

F-59, N-3, D-113, D-114, D-116 — *Transport and the ARM toggle* and *Media
pool* in [04-ui-spec.md](../04-ui-spec.md), the threading table in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.

**Reworked before building (2026-09-26).** Planned first as a strip at the
top of the media pool, for imports only. The person asked instead for a box
that anything can use, at the top right of the transport toolbar, taking a
label, a value and a maximum. D-116 records it, and D-113's placement is
superseded.
