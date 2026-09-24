# M2 · Phase 4 — Peaks and the cache

**Status:** not started · **Plan:** not written yet

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

- [ ] Every level of the pyramid agrees with the level below it, and the
      coarsest level's min and max are the file's min and max — asserted as a
      property over generated signals, not over one hand-picked file.
- [ ] Stereo keeps a pyramid per channel; mono has one.
- [ ] The first request computes and writes; the second reads, asserted by
      counting computations rather than by timing.
- [ ] The same audio at two paths, or in two projects, produces one cache
      entry.
- [ ] A cache entry that is truncated, corrupt, or written by another format
      version is recomputed and rewritten, and nothing raises.
- [ ] An interrupted write cannot leave a truncated entry behind that is later
      read as valid.
- [ ] Where the cache lives is decided — `03`'s literal per-platform paths or
      the location Qt reports — and `03` is corrected to whichever is true.
- [ ] No test writes to a cache outside its temporary home, asserted by a
      test in the way M9 phase 4 asserted it for settings.
- [ ] The time to load warm peaks for 100 files is measured and recorded
      against N-4's three-second budget for a whole project.

## Implements

F-9, D-59, N-4, N-5 — *Caches, not project data* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
