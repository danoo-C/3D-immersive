# M2 · Phase 8 — Import progress, in the info box

**Status:** ✅ complete · **Plan:**
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

- [x] An activity begun with a label and a maximum, and updated, shows that
      label and that value of that maximum in the info box. A maximum of 0
      shows busy, with no measure. Finishing it empties the box.
- [x] Nothing shows for an activity finished within 0.25 s; one still
      running at 0.25 s shows then.
- [x] With two activities running, the box shows the one begun first and
      *+1 more*, and its tooltip names both. A ✕ shows only for an activity
      begun with a cancel, and clicking it calls that cancel.
- [x] The box sits at the right end of the transport toolbar, and showing
      or hiding it moves nothing else in the toolbar.
- [x] An import that runs longer than 0.25 s shows *Importing n of N files*
      and a ✕ in the box, until it has landed.
- [x] The bar moves within a file: one large file's import reports progress
      strictly between 0 and 1 before it finishes.
- [x] The bar counts bytes. When a small and a large file are imported and
      only the small one is done, the bar stands at the small file's share
      of the bytes.
- [x] The ✕ cancels the import: nothing is added, no notice is posted, and
      the undo stack is unchanged. Files not yet started never run, and a
      file being prepared stops at its next chunk.
- [x] While an import runs, *Import Audio…* and *Import Folder…* are
      disabled, and their tooltips say an import is running.
- [x] Opening a project shows *Loading n of N samples* with no ✕. Opening
      another project while that load runs stops it, and the second
      project's samples load.
- [x] Reading in chunks decodes to exactly the samples a single read gives,
      for every format F-5 names. *MP3 is read in one call: libsndfile
      misdecodes one read in pieces (step 2's Notes).*
- [x] `info` is in `04` and the bundled theme, and the box names no hex.
- [x] A 22-stem import is timed stage by stage, on the Linux filesystem and
      on the Windows drive under WSL. The numbers are recorded in the Notes,
      along with whether reading once was kept, judged by the plan's
      criterion.
- [x] A screenshot of the box part-way through a real import is taken and
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

**Step 3 — the activities and the info box.** Any piece of work begins,
updates and finishes an activity, and the box at the right end of the
transport toolbar shows the first begun. Two things were found by looking,
not by the tests as first written:

- **At the window's narrowest, 1024 px, a 260 px box did not fit.** Qt folded
  it into the toolbar's overflow menu, the risk the plan named. It now gives
  way down to 150 px, eliding its label, and a test holds it in sight at
  that width.
- **The ✕ at 20 px showed nothing.** The buttons' 10 px padding left it no
  room for its icon, and the button had been trimmed to 20 px so the box
  would be no taller than the toolbar's buttons. It is unpadded now.

The bar counts in thousandths, not in the activity's numbers, because
`QProgressBar` holds a 32-bit int and an import counted in bytes passes
2 GB. Eighteen mutations, all caught; three only once their tests were
tightened (which label was drawn, where the box sits, the ✕'s size). A
note for later sweeps: with `-x` under xdist, tests cut short by the stop
are listed as failures, so the first FAILED line can name the wrong
catcher. Attribution is read from runs without `-x`.

**Step 4 — the importer and the window.** An import is an activity with a
✕, and a load one without. Both are updated from the importer's own
fifteen-a-second report, which counts each file by its bytes. The ✕ drops
the batch: its queue is cleared, and each running file stops at its next
chunk. A file that finishes anyway carries its batch's number and is
ignored. While an import runs, the Import actions are disabled and say why.
Opening a project cancels the load under way, and loads its own samples.
The test for that fails against the old early return, as the sweep showed.

One addition the plan did not name: **closing the window asks running
work to stop**. The importer's pool is its own now, and a pool being
destroyed waits for its threads, so a close would otherwise have waited
for a folder to finish decoding. Fourteen mutations, all caught.

**Step 5 — reading once: measured, and reverted by the plan's criterion.**
The wrapper was exact. For WAV, AIFF, FLAC, OGG and MP3 it hashed every
byte in order as libsndfile read it, with nothing to read again, and the
digest was `content_hash`'s. But over the 23 stems at twelve workers:

| | Read twice (as built) | Read once |
|---|---|---|
| Linux filesystem | 1.8–2.5 s | 12.9–13.2 s |
| Windows drive | 8.7–8.9 s | 13.1 s |

With one worker the two were level (8.1 s and 8.4 s), so no single call is
expensive. libsndfile makes about 6 000 small reads of a stem, and through
a file object each is a Python call holding the GIL. Twelve workers then
queue behind one another: the parallelism the workers exist for, lost. The
criterion asked for a quarter faster from the Windows drive and no more
than a tenth slower locally; it was half again slower on both. Reverted. A
one-read that kept libsndfile's reads in C would take a memory file
(`memfd`) on Linux and something else on Windows, for a saving that
matters only on WSL's bridge. Not pursued. **On WSL, keeping samples on
the Linux filesystem is the fix: 2 s instead of 9 for the same stems.**

**Step 6 — looked at, and closed.** The person's 23 stems, imported through
the window from the Linux filesystem, landed in 2.65 s. The box read
*Importing 0 of 23 files* at a quarter second with its bar at 19%, and the
bar kept moving: 67% at 1.7 s, 99% at 2.6 s. Its one pause, about half a
second at 23%, was twelve workers resampling at once, the one stage with no
progress inside it, as the plan accepted. The file count jumped from 0 to 12
in one step, which is exactly why the bar counts bytes. The grab shows the
box at the top right with a third of its bar and a ✕, over a pool still
empty.

The phase adds 50 tests. The suite is 2192: 12.3 s in parallel and 7.0 s
in the fast lane. The fast lane was 4.2 s at M3 phase 9; this phase's
chunked-read tests account for some of that, but the machine has been
slower all session (both states measured 23–27 s once, see M3), so the
figure is not a comparison.
