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

**Step 1 — measured, on the person's 23 stems.** Each stem is a 50 MB
24-bit stereo WAV of 187 s at 44.1 kHz, so every one is resampled; 1.1 GB
in all. Each file's peaks are cold.

One stem, one worker:

| Stage | Linux filesystem | Windows drive under WSL |
|---|---|---|
| read | 0.08–0.12 s | 0.85 s (67%) |
| resample | 0.17–0.18 s (about half) | 0.16 s |
| hash (the second read) | 0.04 s | 0.19 s |
| peaks | 0.05–0.07 s | 0.06 s |
| **total** | **0.34–0.41 s** | **1.25 s** |

The whole import:

| Workers | Linux filesystem | Windows drive |
|---|---|---|
| 1 | 7.9 s | 28.2 s |
| 4 | 2.7 s | 11.5 s |
| 8 | 2.0 s | 9.2 s |
| 12, the machine's count | 2.0 s | 9.0 s |
| **through the window**, offscreen | **2.4 s** | **9.4 s** |

The window's own part, landing the results and painting 23 rows, took under
0.01 s. It also measured the peak memory: 1.65 GB of samples held, and
2.3 GB at the peak with 12 workers.

What it settles:

- **The wait was the Windows drive.** It reads roughly 2.3 GB over the
  bridge, 1.15 GB twice, in 9 s: about 255 MB/s, which is the bridge's
  limit, and no worker count beyond eight gets past it. libsndfile's own
  reads are slow there too: 59 MB/s where the hash's 1 MiB reads reach
  260 MB/s, because it reads in small pieces and each crosses the bridge.
- **No worker cap.** Eight and twelve workers are equally fast on both
  filesystems, so the pool keeps the machine's count.
- **The stage weights.** Reading is two-thirds of a file from the Windows
  drive, and resampling half of it from a local disk. A file's `done`
  therefore moves 0.45 for reading, 0.30 for resampling, 0.15 for hashing
  and 0.10 for peaks. A file already at 48 kHz skips resampling, and
  reading takes that share.
- **Step 5's baseline** is 9.0–9.4 s from the Windows drive and 2.0–2.4 s
  from the Linux filesystem.

**Step 2 — progress through `prepare`.** Every stage moves a file's
progress, and a cancel stops it at the next chunk or between stages. The
finding is libsndfile's: an MP3 read in pieces decodes wrongly after each
boundary, so MP3s still read in one call (the plan's amendments say how,
and a canary test watches for the fix). Fourteen mutations, all caught; two
only after their tests were tightened. Rising-only progress hid a hash
stage counted from 0, and a stage's own cancel check hid the one between
stages.
