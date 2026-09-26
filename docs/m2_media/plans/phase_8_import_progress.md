# Plan — M2 · Phase 8 — Import progress, in the info box

**Written:** 2026-09-26 · **Reworked:** 2026-09-26, before building - the
pool strip became the toolbar's info box (D-116) · **Status:** planned

## Approach

Phase 6 already prepares samples on workers, so the window never froze. This
phase gives the application **one place to show that something is under
way**, and makes the workers **say how far they have got**. Five layers, each
testable without the one above it.

**`ui/activity.py`: activities, without Qt.** Anything slow begins an
activity, updates it and finishes it. That is the whole contract, and it is
what the box shows:

```python
work = window.activities().begin(
    "Importing 0 of 22 files", maximum=total_bytes, cancel=importer.cancel
)
work.update(done_bytes, label=f"Importing {done} of 22 files")
work.finish()
```

- `begin(label, maximum=0, *, cancel=None) -> Activity`. A `maximum` of 0
  means busy with no measure.
- `Activity.update(value=None, *, maximum=None, label=None)` changes what it
  is given. A value is held between 0 and the maximum.
- `Activity.finish()` removes it, and a second call does nothing.
- `Activities.running()` lists activities in the order they began.
  `shown()` lists those that have run for at least `SHOW_AFTER`, 0.25 s, by
  a clock passed in. `observe(callback)` reports every begin, update and
  finish.

It is Qt-free, like `landing.py`, so it is tested without a widget. It is
used from the UI thread only (D-116). Work on a worker reports through
values the UI thread reads, as the importer below does.

**`ui/widgets/info_box.py`: the box.** An `InfoBox` at the right end of the
transport toolbar, after a spacer that takes the free width, so it appears
and disappears without moving anything else. It holds:
- the first shown activity's label, elided to the box's width;
- *+n more* when others are shown, and a tooltip naming every one;
- a ✕ when that activity was begun with a cancel;
- under them, a thin `QProgressBar` with `QProgressBar`'s own model, where a
  maximum of 0 is busy.

It re-reads the model when told of a change, and once more at the moment
the next activity reaches `SHOW_AFTER`, by a single-shot timer, so nothing
polls while nothing is happening. Its `info` group is read from the theme,
and the ✕ is a new `cancel` icon, drawn as the toolbar's glyphs are.

**`core`: progress without Qt.** `prepare(path, cache, progress)` takes an
optional `Progress`: one small object per file, with a `done` fraction that
only rises and a `cancelled` flag. The worker writes `done`; the UI thread
reads it, and sets `cancelled`. A float and a bool assigned whole are safe
to share under the GIL, so no lock and no signal per chunk.

`decode` reads in chunks of 2¹⁸ frames into an array sized from the file's
frame count, rather than in one `soundfile.read`. `content_hash` already
reads 1 MiB at a time. Each chunk of either moves `done` and checks
`cancelled`. A cancelled file returns a new `Cancelled` value, next to
`Refused`, never an exception. Measured while planning: a 5-minute stereo
file read in chunks gives exactly the samples a single read does, and takes
the same time (0.15–0.18 s).

**`ui/importer.py`: a batch's progress, and its cancel.** The importer gets
a `QThreadPool` of its own, so `clear()` drops only its own queued jobs and
not the global pool's.
- It takes each file's size when it starts, so progress is
  Σ sizeᵢ·doneᵢ / Σ sizeᵢ: bytes rather than files (D-113).
- While busy it emits `progressed(files_done, files, bytes_done,
  bytes_total)` from a 15 Hz timer of its own, stopped when idle.
- `cancel()` clears the queue and sets every running file's `cancelled`.
- Every delivery carries its batch's number, so a straggler from a
  cancelled batch is dropped rather than counted into the next one.

**The window: the activities, the actions, the loader.**
- An import begins an activity with the importer's cancel, a load one
  without, and each is updated from `progressed` and finished when its
  batch lands or is dropped.
- While an import runs, the two Import actions are disabled, with the
  reason in their tooltips (D-114).
- `_load_samples` no longer returns early when a load is running. It
  cancels that load, which belonged to the project being replaced, and
  starts the new one's.

**Rejected alternatives:**
- **A strip in the media pool**, which this plan first proposed. It could
  show only imports, and would vanish with the pool collapsed (D-116).
- **Counting files and keeping `prepare` as one call.** It changes nothing
  in `core`, but the workers finish files in bursts. The first eight of
  twenty-two would all end at once after several seconds of a bar standing
  still, which is the report this phase exists to replace.
- **Having the box poll each piece of work.** Most work already knows when
  it has moved, and polling keeps a timer running for everything. The
  importer polls its own workers, because the thing that moves there is a
  float on another thread, and hands the box the result.

## Decisions settled here

**Where, and for what (D-116).** An info box at the right end of the
transport toolbar, for any activity: a label, a value and a maximum, a
cancel if the work has one, the first-begun shown with *+n more*.

**In what unit, and when (D-113, as superseded).** Bytes, after a quarter of
a second. Rows still land together.

**What cancel means (D-114).** The whole import is dropped quietly. The
Import actions are disabled while one runs. A load has no ✕, and a newer
open stops it.

**One read or two: decided by measurement, in step 1, by this criterion.**
Today each file is read twice, once by the decoder and once by the hash.
Measured while planning, the Windows drive under WSL reads at about
220 MB/s, where the Linux filesystem reads a cached file at over 6 GB/s.
From the Windows drive, 22 stems of 86 MB each is roughly 17 s of reading,
and half of that is the second read.

Reading once means the decoder reads through a wrapper. The wrapper hashes
the bytes it hands over, in order, and afterwards reads only what the
decoder skipped, so the digest is `content_hash`'s exactly. The catch:
libsndfile then calls back into Python for every read, holding the GIL,
which could cost the parallelism the workers give on fast disks.

**Step 5 is kept if, over the 22 stems, it makes the import at least a
quarter faster from the Windows drive and no more than a tenth slower from
the Linux filesystem.** Otherwise it is reverted, and the Notes say so with
the numbers. If it is kept, the change of read path goes into 01 as a
decision.

## Steps

1. **Measure first.** No code in `src`. A throwaway script builds 22
   five-minute stereo 24-bit stems, half at 44.1 kHz and half at 48 kHz. It
   times each stage (read, resample, hash, peaks) and the whole import at 1,
   2, 4 and 8 workers and at the machine's count. It runs from the Linux
   filesystem and from the Windows drive, using the person's real stems if
   they say where those are. It settles:
   - the stage weights that make one file's `done` move evenly;
   - whether the importer's pool should run fewer workers than cores, which
     it should if the Windows drive is faster with fewer;
   - the numbers step 5's criterion is judged against.

   Recorded in the phase's Notes.
2. **Progress and cancel through `prepare`** (`core`). Add `Progress` and
   `Cancelled`, a chunked `decode`, a hash that counts its bytes, and stages
   weighted by step 1. Tests, all headless:
   - reading in chunks decodes to exactly what a single read gives, for WAV,
     AIFF, FLAC, OGG and MP3;
   - `done` rises monotonically, reaches values strictly between 0 and 1,
     and ends at 1;
   - `cancelled` set between chunks returns `Cancelled` before the next
     chunk is read;
   - a refused file still returns `Refused`;
   - `prepare` without a `Progress` behaves as it did.
3. **The activities and the info box.** Add `ui/activity.py`, the `InfoBox`,
   and the box's place in the toolbar after the spacer. Add the `info` group
   to `04`, the bundled theme and `app.qss`, and move *progress bar* in
   `04`'s owner table from M8 to this phase. Add the `cancel` icon.

   Model tests, headless:
   - begin, update and finish;
   - a value held within its maximum;
   - `running()` in the order begun;
   - `shown()` only after `SHOW_AFTER`, by a stepped clock;
   - a second `finish()` does nothing;
   - observers are told of each change.

   Box tests:
   - the label, value and maximum drawn;
   - a maximum of 0 is busy;
   - nothing shown before 0.25 s, and shown at 0.25 s without any update;
   - *+1 more* and a tooltip naming both;
   - a ✕ only with a cancel, and clicking it calls the cancel;
   - empty and hidden once all have finished;
   - the other toolbar widgets' geometry unchanged by showing and hiding;
   - no hex.

   A screenshot of the box with a measured activity, a busy one and *+1
   more*, looked at.
4. **The importer and the window.** Add the importer's own pool, sizes as
   weights, `progressed`, `cancel()` and the batch number. In the window,
   add the activities for import and load, disable the Import actions while
   an import runs, and cancel a running load on a newer open. The tests use
   phase 6's gates, never sleeps:
   - a gated import shows *Importing n of N files* and a byte fraction in
     the box;
   - the ✕ adds nothing, posts nothing and leaves the stack as it was;
   - a queued job never runs;
   - a straggler from a cancelled batch is not counted in the next;
   - the actions are disabled and say why, then are enabled again after
     both finishing and cancelling;
   - a load shows no ✕;
   - opening project B during A's load loads B's samples. This one is
     written first, to watch it fail against today's early return.
5. **One read, if step 1 says so.** The wrapper that hashes what the decoder
   reads, in order, and then reads only what was skipped. Tests: the digest
   equals `content_hash` for every format, including against a decoder made
   to seek backwards and to skip ahead. Measure again, and keep or revert by
   the criterion above.
6. **Looked at, written down, closed.** A real import of the 22 stems, and a
   screenshot of the box part-way through, looked at. Update `02`'s
   threading table: activities are touched on the UI thread only, workers
   report through shared values, and the importer has a pool of its own.
   Update `04`'s *Transport and the ARM toggle* for the box. Then the Notes,
   the Outcome, and M2's README.

## Files

`src/immersive/ui/activity.py` — new: `Activities`, `Activity`,
`SHOW_AFTER`
`src/immersive/ui/widgets/info_box.py` — new: `InfoBox`
`src/immersive/core/progress.py` — new: `Progress`, `Cancelled`
`src/immersive/core/io/media.py` — chunked `decode`, counted hash; step 5's
reading wrapper
`src/immersive/core/media_store.py` — `prepare(..., progress)`
`src/immersive/ui/importer.py` — its own pool, `progressed`, `cancel()`,
batch numbers
`src/immersive/ui/main_window.py` — the box in the toolbar, `activities()`,
the import and load activities, the actions disabled, the load superseded
`src/immersive/assets/icons/cancel.svg` — new
`src/immersive/assets/app.qss`, `src/immersive/assets/themes/vscode_dark.3dimtheme`
— the `info` group
`docs/02-architecture.md`, `docs/04-ui-spec.md` — as step 6 says
`tests/test_media.py`, `tests/test_media_store.py`, `tests/test_import.py`,
`tests/test_loading.py`, `tests/test_icons.py`, `tests/test_theme.py` —
extended
`tests/test_activity.py`, `tests/test_info_box.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | an activity shown at once, with no delay | nothing before 0.25 s |
| 2 | the box re-reads only on updates, so a silent activity never appears | shown at 0.25 s without an update |
| 3 | the newest activity shown, not the first begun | the two-activity test |
| 4 | *+n more* counts the one shown | *+1 more* with two |
| 5 | a ✕ for an activity begun without a cancel | ✕ only with a cancel |
| 6 | `finish()` leaves the activity running | empty once all have finished |
| 7 | a maximum of 0 drawn as a full bar | a maximum of 0 is busy |
| 8 | `update` ignores a new label | the label drawn after an update |
| 9 | the box added without the spacer | toolbar geometry unchanged |
| 10 | `done` written only when the file is finished | progress strictly between 0 and 1 |
| 11 | the batch fraction counts files, not bytes | the small-and-large-file test |
| 12 | `cancel()` does not clear the queue | a queued job never runs |
| 13 | a running file ignores `cancelled` | `Cancelled` before the next chunk |
| 14 | a cancelled batch's results still land | nothing added after a cancel |
| 15 | a cancel posts a notice | no notice after a cancel |
| 16 | a straggler's batch number is not checked | the next batch's count |
| 17 | a load's activity given the importer's cancel | a load shows no ✕ |
| 18 | the early return kept in `_load_samples` | B's samples load |
| 19 | the actions not enabled again after a cancel | enabled after finishing *and* after cancelling |
| 20 | the last, partial chunk dropped | chunked equals single read |
| 21 | reading stops at the announced frame count when a file holds more | chunked equals single read, MP3 |
| 22 | step 5's hash takes bytes out of order after a backward seek | equals `content_hash` under a seeking decoder |
| 23 | a literal colour in the box | the theme's no-hex test |

## Risks and unknowns

- **A toolbar that is too narrow.** At the window's smallest width the
  spacer is gone, and Qt folds what does not fit into an overflow menu.
  The box then goes there first, since it is last. Acceptable while
  something else is on screen, and looked at in step 3. If it hides the
  one thing a long import has to show, the box gets a minimum width that
  the tempo and snap chips give way to.
- **An MP3's frame count can be an estimate.** Sizing the array from it
  could truncate or leave a tail of zeros. So the chunked read grows the
  array or trims it to what was actually read, and mutation 21 covers it.
- **The GIL under step 5.** Python read callbacks could serialise the
  workers. That is why step 5 is measured and can be reverted rather than
  assumed.
- **Resampling is one call**, 0.34 s for a 5-minute 44.1 kHz stem, so one
  file's `done` pauses for that long while the others keep the bar moving.
  A streaming resampler would move it, but is not promised to give exactly
  the samples a single call does, and phase 2's tests hold those exact.
  Accepted.
- **The Linux numbers are warm.** A file just written is in the page cache,
  and clearing that cache needs root. The Windows drive is limited by the
  bridge either way, and that is the case this phase is for.
- **Memory is unchanged.** 22 five-minute stems decode to about 2.5 GB of
  float32, as they do today, because the session holds samples in RAM by
  design (M2). If the person's machine was paging, no progress bar fixes
  that. Step 1 records the peak.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Render's progress and cancel (F-37) | M7, as an activity in this box |
| The HRTF bank's first build into its cache | M4, as an activity in this box |
| Progress for relinking | M8, with the relink dialog |
| Anything else in the info box — a clock, the device, autosave | not asked for; it holds activities |
| Rows appearing as each file finishes | not planned: an import is one edit (D-113) |
| A decoded-audio cache, so an open does not decode again | not planned; its own question, sized by the samples themselves |
| Dropping files from the desktop onto the pool | not asked for; the pool is a drag source only (phase 6) |

## Outcome

Filled in at the end.
