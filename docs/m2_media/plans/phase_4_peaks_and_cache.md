# Plan — M2 · Phase 4 — Peaks and the cache

**Written:** 2026-09-24 · **Status:** ✅ complete

## Approach

A min/max pyramid, finest level first: level 0 summarises every 256 frames,
and each level above summarises four buckets of the one below, up to a level
of one bucket that is the whole file's minimum and maximum. Per channel, in
float32 — float sources keep their overs (phase 2), and a pyramid in int16
would clip them.

The numbers are for drawing, not for listening. A five-minute stereo file is
56 000 buckets at level 0 and about 1.2 MB across all levels; a 120-pixel
thumbnail of it reads level 5, 55 buckets. Finer than 256 frames a bucket is
M3's problem at deep zoom, where it can read the audio itself.

**Built in memory, cached on disk, keyed by content hash** (D-59), under one
function that asks the cache first. The on-disk entry is a `.npz` carrying a
format version, the frame and channel counts, and the levels. Anything wrong
with an entry — missing, truncated, corrupt, another version, a length that
does not match the audio — is a miss: the pyramid is built again and the
entry rewritten. A cache is disposable by definition (`03` says the whole
directory is safe to delete), so it never gets to raise.

Writes go through a temporary file and a rename, as `project_io` does, so an
interrupted write leaves either the old entry or none — never a truncated one
that a later read could take for real.

## Two things the phase doc leaves open

### Where the cache is, and who works it out

`03`'s table gives literal paths — `$XDG_CACHE_HOME/3dimmersive`,
`~/Library/Caches/3dimmersive`, `%LOCALAPPDATA%\3dImmersive\Cache` — and Qt's
cache location for this application is a different path again. `peaks.py` is
in `core/`, which N-5 keeps free of Qt, and it runs on the workers phase 6
will start, where nothing should be asking a `QApplication` anything.

So `core` resolves `03`'s table itself, from the environment. That has a
consequence worth more than the tidiness: **the test suite can redirect it
on every platform.** M9 found that redirecting `APPDATA` may not reach Qt's
Windows lookup at all; this code reads `LOCALAPPDATA` itself, so the
redirect in `conftest.py` is the whole story, and a test can assert it. `03`
needs no correction — it was right — and gains a sentence saying who reads
it.

### Keying a sample whose hash is empty

D-89 leaves an old project's hashes empty, and filling one would be an edit.
So the cache is keyed by a hash the *caller* supplies: `MediaFile.hash` when
there is one, and `content_hash(path)` computed for the moment when there is
not — the same value either way, because it is the same file, and nothing
written into the model.

## Steps

1. **The pyramid.** `core/io/peaks.py`: `Level`, `Pyramid`, `build(audio)`.
   *Test:* against a brute-force oracle over generated signals and awkward
   lengths — a single frame, one short of a bucket, one over, several levels'
   worth plus a remainder — every level's every bucket equals the min and max
   of the frames it covers; the last level is one bucket and is the file's
   min and max; stereo keeps a pyramid per channel; overs survive.

2. **The cache.** `cache_directory()` from the environment per `03`;
   `peaks(key, audio, directory)` reading first, building and writing on a
   miss; the format version; atomic writes; `conftest.py` redirecting
   `XDG_CACHE_HOME` and `LOCALAPPDATA` beside what it already redirects. The
   decision row. `03` gains who resolves the path.
   *Test:* the second request reads, counted rather than timed; one entry for
   the same audio under two paths; truncated, corrupt, other-version and
   wrong-length entries are rebuilt and nothing raises; a write interrupted
   part-way leaves no entry; the cache directory under test is inside the
   temporary home, on every platform; warm-cache loading for 100 files is
   measured and recorded against N-4.

## Files

```
docs/01-requirements.md            amended — the decision row
docs/doc-system.md                 amended — the D high-water mark
docs/03-data-model.md              amended — who resolves the cache path
docs/m2_media/phase_4_*.md         amended — Notes
src/immersive/core/io/peaks.py     new
tests/test_peaks.py                new — headless
tests/conftest.py                  amended — the cache redirect
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The pyramid and its oracle wrong the same way | a test that agrees with a bug | the oracle is a Python loop over explicit slices, sharing no code with the vectorised build |
| `np.load` on a hostile file | a crash, or worse, a pickle | `allow_pickle=False`, and every exception it can raise is a miss |
| The cache growing without bound | disk use nobody sees | out of scope: `03` calls the directory safe to delete, and nothing asks for eviction |
| The suite writing a real cache | the developer's disk changes because a test ran | the redirect is written before the feature, and a test asserts where the cache is |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the last partial bucket dropped | the end of every sample drawn as silence |
| the pyramid stopping short of one bucket | no level that is the whole file |
| min and max swapped | a waveform drawn inside out |
| channels folded together | a stereo sample drawn as mono |
| the cache never read | every open rebuilds every pyramid |
| keyed by path instead of hash | one sample, two entries — F-9's "once per file" broken |
| a corrupt entry allowed to raise | one bad file in the cache stops a project opening |
| the version not checked | an old format misread as the current one |
| an entry for a different length accepted | peaks from a different file drawn under this one |
| written straight to the final name | an interrupted write leaves a truncated entry that reads as real |
| the directory taken from somewhere other than the environment | the suite writes the developer's real cache |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Drawing | phase 5 |
| Building peaks on a worker | phase 6, which calls this |
| Evicting old entries | nowhere yet — nothing asks for it |
| Buckets finer than 256 frames | M3, reading the audio itself at deep zoom |
| The HRTF bank cache | M4, in the same directory |

## Outcome

Two steps in the planned order, all nine acceptance boxes ticked, eleven
mutations and no survivor. 951 tests.

### What the plan got right

**An oracle that shares nothing with the build.** It is why rewriting the
reduction for speed was safe to do in the same step that measured it.

**Every damaged entry as a miss.** Five kinds of damage, one rule, and the
rule never needed an exception.

**Resolving the path in `core`.** The isolation test it made possible is the
one M9 could not write.

### What the plan did not see

**That the build would cost more than the decode.** The plan's numbers were
sizes, not times. Measuring for N-4 was what found a reduction running across
strided memory, and fixing it took the build from 0.79 s to 0.06 s for five
minutes of stereo.

**That one named mutation belonged to a caller.** "Keyed by path" cannot
happen inside a function that is only ever handed a key.

### What phase 5 needs to know

A `Pyramid` is finest-first; `Level.bucket` is the frames each bucket covers
and `low`/`high` are `(buckets, channels)`. To draw *w* pixels over *n*
frames, the coarsest level whose bucket is still at most *n / w* gives at
least one bucket per pixel. Every level's arrays are float32 and may exceed
±1 for float sources.
