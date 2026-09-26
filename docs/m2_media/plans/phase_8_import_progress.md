# Plan — M2 · Phase 8 — Import progress

**Written:** 2026-09-26 · **Status:** planned

## Approach

Phase 6 already prepares samples on workers, so the window never froze. This
phase makes the workers **say how far they have got**, and gives the pool a
place to show it. Four layers, each testable without the one above it.

**`core`: progress without Qt.** `prepare(path, cache, progress)` takes an
optional `Progress`: one small object per file, with a `done` fraction that
only rises and a `cancelled` flag. The worker writes `done`; the UI thread
reads it, and sets `cancelled`. A float and a bool assigned whole are safe to
share under the GIL, so no lock and no signal per chunk. `decode` reads in
chunks of 2¹⁸ frames into an array sized from the file's frame count, rather
than in one `soundfile.read`. Each chunk moves `done` and checks `cancelled`.
`content_hash` already reads 1 MiB at a time and does the same. A cancelled
file returns a new `Cancelled` value, next to `Refused`, never an exception.
Measured while planning: a 5-minute stereo file read in chunks gives exactly
the samples a single read does, and takes the same time (0.15–0.18 s).

**`ui/importer.py`: a batch's progress, and its cancel.** The importer gets a
`QThreadPool` of its own, so `clear()` drops only its own queued jobs and not
the global pool's. It takes each file's size when it starts, so progress is
Σ sizeᵢ·doneᵢ / Σ sizeᵢ, bytes rather than files (D-113). `progress()`
returns files done, files in all, and that fraction. `cancel()` clears the
queue and sets every running file's `cancelled`. Every delivery carries its
batch's number, so a straggler from a cancelled batch is dropped rather than
counted into the next one.

**`ui/explorer/progress_strip.py`: the strip.** A label, a `QProgressBar`
and a ✕, between the pool's filter and its tree. It is told which importer
to watch and whether that work may be cancelled. It reads `progress()` on a
15 Hz timer of its own while the importer is busy. It shows itself once the
work has run for 0.25 s, and hides when the importer is idle. The clock is
passed in and `tick()` is public, as the transport's is, so a test steps
time rather than waiting.

**The window: the actions, and the loader.** While an import runs, the two
Import actions are disabled, with the reason in their tooltips (D-114).
`_load_samples` no longer returns early when a load is running: it cancels
that load, which belonged to the project being replaced, and starts the new
one's.

The alternative was a progress bar in the status bar, rejected for D-113's
reasons. A second alternative was **counting files and keeping `prepare`
as one call**, which changes nothing in `core`. It was rejected because the
workers finish files in bursts. The first eight of twenty-two would all end
at once after several seconds of a bar standing still, and that is the
report this phase exists to replace.

## Decisions settled here

**Where, and in what unit (D-113).** A strip in the pool, counted in bytes,
after a quarter of a second; rows still land together.

**What cancel means (D-114).** The whole import is dropped quietly. The
Import actions are disabled while one runs. A load has no ✕, and a newer open
stops it.

**One read or two: decided by measurement, in step 1, by this criterion.**
Today each file is read twice: once by the decoder and once by the hash.
Measured while planning, the Windows drive under WSL reads at about 220 MB/s,
where the Linux filesystem reads a cached file at over 6 GB/s. From the
Windows drive, 22 stems of 86 MB each is roughly 17 s of reading, half of
which is the second read. Reading once means the decoder reads through a
wrapper. The wrapper hashes the bytes it hands over, in order, and afterwards
reads only what the decoder skipped, so the digest is `content_hash`'s
exactly. The catch: libsndfile then calls back into Python for every read,
holding the GIL, which could cost the parallelism the workers give on fast
disks. **Step 5 is kept if, over the 22 stems, it makes the import at least a
quarter faster from the Windows drive and no more than a tenth slower from
the Linux filesystem**; otherwise it is reverted, and the Notes say so with
the numbers. If step 5 is kept, the change of read path is recorded in 01 as
a decision.

## Steps

1. **Measure first.** No code in `src`. A throwaway script builds 22
   five-minute stereo 24-bit stems, half at 44.1 kHz and half at 48 kHz. It
   times each stage (read, resample, hash, peaks) and the whole import at 1,
   2, 4, 8 workers and the machine's count. It does this from the Linux
   filesystem and from the Windows drive, using the person's real stems if
   they say where those are. It settles three things. First, the stage
   weights that make one file's `done` move evenly. Second, whether the
   importer's pool should run fewer workers than cores, which it should if
   the Windows drive is faster with fewer. Third, the numbers step 5's
   criterion is judged against. Recorded in the phase's Notes.
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
3. **The importer and the window.** Add the importer's own pool, sizes as
   weights, `progress()`, `cancel()` and the batch number. In the window,
   disable the Import actions while an import runs, and cancel a running load
   on a newer open. The tests use phase 6's gates, never sleeps:
   - a gated import reports files done and a byte fraction;
   - a cancel adds nothing, posts nothing and leaves the stack as it was;
   - a queued job never runs;
   - a straggler from a cancelled batch is not counted in the next;
   - the actions are disabled and say why, then are enabled again after
     both finishing and cancelling;
   - opening project B during A's load loads B's samples. This one is
     written first, to watch it fail against today's early return.
4. **The strip.** Add the widget, its delay, the 15 Hz refresh, and a ✕ for
   imports only, placed under the filter. Add the `progress` group to `04`,
   the bundled theme and `app.qss`, and move *progress bar* in `04`'s owner
   table from M8 to this phase. Draw the ✕ from a new `cancel` icon, as the
   toolbar's glyphs are drawn. Tests, with the clock stepped:
   - nothing is shown before 0.25 s;
   - the text and the bar at a known progress;
   - the strip is gone once the import lands;
   - ✕ cancels;
   - a load shows no ✕;
   - no hex in the widget.
5. **One read, if step 1 says so.** The wrapper that hashes what the decoder
   reads, in order, and then reads only what was skipped. Tests: the digest
   equals `content_hash` for every format, including against a decoder made
   to seek backwards and to skip ahead. Measure again, and keep or revert by
   the criterion above.
6. **Looked at, written down, closed.** A real import of the 22 stems, and a
   screenshot of the strip part-way through, looked at. Update `02`'s
   threading table (workers report progress through a shared value, and the
   importer has a pool of its own) and `04`'s *Media pool*. Then the Notes,
   the Outcome, and M2's README.

## Files

`src/immersive/core/progress.py` — new: `Progress`, `Cancelled`
`src/immersive/core/io/media.py` — chunked `decode`, counted hash; step 5's
reading wrapper
`src/immersive/core/media_store.py` — `prepare(..., progress)`
`src/immersive/ui/importer.py` — its own pool, `progress()`, `cancel()`,
batch numbers
`src/immersive/ui/explorer/progress_strip.py` — new
`src/immersive/ui/explorer/media_pool.py` — the strip, under the filter
`src/immersive/ui/main_window.py` — watching both importers, the actions
disabled, the load superseded
`src/immersive/assets/icons/cancel.svg` — new
`src/immersive/assets/app.qss`, `src/immersive/assets/themes/vscode_dark.3dimtheme`
— the `progress` group
`docs/02-architecture.md`, `docs/04-ui-spec.md` — as step 6 says
`tests/test_media.py`, `tests/test_media_store.py`, `tests/test_import.py`,
`tests/test_loading.py`, `tests/test_icons.py`, `tests/test_theme.py` —
extended
`tests/test_progress_strip.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | `done` written only when the file is finished | progress strictly between 0 and 1 |
| 2 | the batch fraction counts files, not bytes | the small-and-large-file test |
| 3 | `cancel()` does not clear the queue | a queued job never runs |
| 4 | a running file ignores `cancelled` | `Cancelled` before the next chunk |
| 5 | a cancelled batch's results still land | nothing added after a cancel |
| 6 | a cancel posts a notice | no notice after a cancel |
| 7 | a straggler's batch number is not checked | the next batch's count |
| 8 | the strip is shown at once, with no delay | nothing before 0.25 s |
| 9 | the strip is not hidden when the import lands | gone once landed |
| 10 | a load is given a ✕ | a load shows no ✕ |
| 11 | the early return kept in `_load_samples` | B's samples load |
| 12 | the actions not enabled again after a cancel | enabled after finishing *and* after cancelling |
| 13 | the last, partial chunk dropped | chunked equals single read |
| 14 | reading stops at the announced frame count when a file holds more | chunked equals single read, MP3 |
| 15 | step 5's hash takes bytes out of order after a backward seek | equals `content_hash` under a seeking decoder |
| 16 | a literal colour in the strip | the theme's no-hex test |

## Risks and unknowns

- **An MP3's frame count can be an estimate.** Sizing the array from it
  could truncate or leave a tail of zeros. So the chunked read grows the
  array or trims it to what was actually read, and mutation 14 covers it.
- **The GIL under step 5.** Python read callbacks could serialise the
  workers. That is why step 5 is measured and can be reverted rather than
  assumed.
- **Resampling is one call**, 0.34 s for a 5-minute 44.1 kHz stem, so one
  file's `done` pauses for that long. Other files keep the bar moving. A
  streaming resampler would move it, but is not promised to give exactly the
  samples a single call does, and phase 2's tests hold those exact. Accepted.
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
| Rows appearing as each file finishes | not planned: an import is one edit (D-113) |
| A decoded-audio cache, so an open does not decode again | not planned; its own question, sized by the samples themselves |
| Progress for relinking | M8, with the relink dialog |
| Dropping files from the desktop onto the pool | not asked for; the pool is a drag source only (phase 6) |

## Outcome

Filled in at the end.
