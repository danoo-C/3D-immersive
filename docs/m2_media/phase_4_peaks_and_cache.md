# M2 · Phase 4 — Peaks and the cache

**Status:** ✅ complete · **Plan:**
[plans/phase_4_peaks_and_cache.md](plans/phase_4_peaks_and_cache.md)

## Goal

`core/io/peaks.py` builds a min/max peak pyramid from decoded audio and keeps
it in the one user-level cache directory, keyed by content hash (D-59). The
second time any project asks for a file's peaks they are read rather than
computed — whichever project, whichever path the file is at (F-9: "computed
once per file").

This is the half of a waveform that has nothing to do with drawing.

## Scope

**In:** the pyramid — the finest bucket size and the ratio between levels;
per-channel peaks; the on-disk format, with a version so a later change is a
cache miss rather than a misread; writing through a temporary file, as
`project_io` does; a cache entry that is missing, truncated, corrupt or from
another version treated as a miss and rewritten; resolving the cache
directory without Qt, because this module is in `core/`; keeping the test
suite out of the developer's real cache.

**Out:** drawing peaks → phase 5. Evicting old entries or bounding the
cache's size — nothing asks for it, and `03` calls the whole directory safe to
delete. The decoded-audio cache `03` mentions as a possibility, and the HRTF
bank cache, which is M4's.

## Acceptance

- [x] Every level of the pyramid agrees with the level below it, and the
      coarsest level's min and max are the file's min and max — asserted as a
      property over generated signals, not over one hand-picked file.
- [x] Stereo keeps a pyramid per channel; mono has one.
- [x] The first request computes and writes; the second reads, asserted by
      counting computations rather than by timing.
- [x] The same audio at two paths, or in two projects, produces one cache
      entry.
- [x] A cache entry that is truncated, corrupt, or written by another format
      version is recomputed and rewritten, and nothing raises.
- [x] An interrupted write cannot leave a truncated entry behind that is later
      read as valid.
- [x] Where the cache lives is decided — `03`'s literal per-platform paths or
      the location Qt reports — and `03` is corrected to whichever is true.
- [x] No test writes to a cache outside its temporary home, asserted by a
      test in the way M9 phase 4 asserted it for settings.
- [x] The time to load warm peaks for 100 files is measured and recorded
      against N-4's three-second budget for a whole project.

## Implements

F-9, D-59, N-4, N-5 — *Caches, not project data* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**A sample's peaks are built once and read ever after, whichever project
asks.** The pyramid is checked against a loop that shares no code with it,
the cache cannot raise, and the suite's cache is inside its temporary home on
every platform.

### D-91: `core` reads `03`'s table itself

`03` had the paths right. What it did not say was who works them out, and
the answer had to be `core`: `peaks.py` is headless and will run on phase 6's
workers. The consequence that mattered more than the tidiness is that the
suite's redirect now means the same thing everywhere — `conftest.py` sets
`XDG_CACHE_HOME` and `LOCALAPPDATA`, the code reads exactly those, and a test
asserts the result is inside the temporary home. M9 could not say that about
Qt's Windows lookup.

### ⚠️ The build was slower than decoding, and it was the memory layout

Measuring for N-4 found building the pyramid for five minutes of stereo took
0.79 s — longer than decoding and resampling the same file. Minimum and
maximum were being reduced across the strided middle axis of `(frames, 256,
channels)`. Transposed to channel-major first, the same reduction runs over
contiguous memory and the build takes **0.06 s**. The oracle tests did not
move, which is what they are for.

### N-4, measured

| | Cold: build and write | Warm: read |
|---|---|---|
| 100 × 30 s stereo | — | 0.13 s |
| 100 × 5 min stereo | 6.4 s | 0.19 s |

An entry is about 120 KiB for thirty seconds of stereo and 1.2 MiB for five
minutes. Warm, a hundred samples' peaks are well inside N-4's three seconds
for a whole project. Cold is an import cost and belongs on phase 6's workers.

### What the mutation sweep found

Eleven mutations, all killed on the first run. One of the plan's could not be
expressed inside `peaks()` at all: "keyed by path instead of hash" is a
mistake a *caller* makes, since `peaks()` only ever sees a key. The test that
puts the same bytes at two paths and finds one entry covers it from the
caller's side, and phase 6 is the caller. In its place the sweep ran a key
pattern that accepts anything, which the test that stops a key leaving the
cache directory caught.
