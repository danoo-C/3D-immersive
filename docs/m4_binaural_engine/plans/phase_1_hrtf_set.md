# Plan — M4 · Phase 1 — The HRTF set

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

Three pieces, the first two stdlib-light and the third the pipeline's
entrance.

**`assets/hrtf/__init__.py`: the registry and the fetch, stdlib only.** One
entry per built-in set: its id (`sadie-d1`), file name, URL, SHA-256 and
size, taken from the spike, which fetched this exact file. `fetch(entry,
into)` downloads with `urllib` in chunks, hashes as it writes, and moves
the file into place only if the digest matches. A mismatch deletes the
partial file and says so. It is stdlib only because `launch.py` runs before
the environment exists: `launch.py --install` loads this one file by path
(`importlib.util.spec_from_file_location`) without importing the package,
so the registry has one home and the launcher cannot drift from it.
`--check` reports whether each set is there.

**`audio/hrtf/sofa.py`: the loader.** `load(path) -> HrirSet | Refused`,
never raising:
- `sofar.read_sofa` reads the file, and anything that is not
  `SimpleFreeFieldHRIR` is refused with the convention it is;
- `SourcePosition`, spherical degrees, becomes unit vectors in the
  project's axes, X right, Y front and Z up:
  `(−cos el · sin az, cos el · cos az, sin el)`;
- `Data_IR` becomes float32 `[M, 2, N]`, resampled to 48 kHz by `soxr` along
  the taps when it is not there already;
- `Data_Delay` is kept, per measurement and ear, in samples at 48 kHz, for
  phase 2;
- the licence, title and database name are read from the file's globals.

Normalisation scales the set so its mean per-ear energy is 0.25, S0's
target, and keeps the factor. `builtin(id)` finds the registry's file
through `importlib.resources` (D-30), loads it, and refuses with the fetch
command if it is not there. The `HrirSet` also carries the content hash of
the file it came from, for phase 4's cache.

**The credits.** `THIRD-PARTY-NOTICES.md`'s bundled-data table gets SADIE
II D1's row: fetched at install, verified by SHA-256, Apache 2.0. The
Apache text travels in the file's own `GLOBAL_License`. It gets its full
text in the bundle at M8, as the notices file already says of the LGPL.

The alternative was committing a derived file: the float32 responses and
directions, 14 MB compressed, and exact, since the set's 24-bit samples
survive float32. It was measured and rejected. 02 and 08 decided *fetched,
not committed*, and nothing measured here outweighs 14 MB of repository
history for good, nor a derived file whose provenance is a script rather
than its publisher.

## Decisions settled here

**Fetched, not committed** - 02 and 08's decision, followed rather than
reopened. Recorded in the Notes with the measurement that tested it.

**The axes.** Once, here: SOFA's front, +x, is the project's +Y. Its left,
+y at azimuth 90°, is the project's −X. Up is +Z in both. Every later phase
takes directions from `HrirSet.directions` and never converts again.

**Level.** A mean per-ear energy of 0.25, as S0 settled, and SADIE II D1's
peak asserted under full scale rather than assumed.

## Steps

1. **The registry and the fetch.** `assets/hrtf/__init__.py`, and
   `launch.py --install` and `--check` using it. Tests against a `file://`
   URL on a temporary file:
   - a matching file lands and a second fetch does nothing;
   - a mismatch leaves nothing behind and says so;
   - an interrupted download leaves no partial file where the loader looks;
   - `launch.py` imports none of the package to do it.

   On this machine the real set is fetched from `spikes/data`'s copy by its
   `file://` URL, checked by the same digest.
2. **The loader.** `HrirSet`, `load()`, the axes, resampling, `Data_Delay`,
   refusals. Tests on synthetic SOFA files that `sofar` writes: a set whose
   responses encode their own direction, one at 44.1 kHz, one with the
   wrong convention, one with delays, and a file that is not SOFA.
3. **Normalisation, the built-in and the credits.** The factor, `builtin()`,
   the notices row. Tests: two sets at different levels come out equal;
   SADIE II D1, where fetched, is Apache 2.0 by its own words, has 8802
   directions, and peaks under 1.0; not fetched, `builtin` refuses with
   the command.

## Files

`src/immersive/assets/hrtf/__init__.py` — the registry and `fetch`,
stdlib only
`src/immersive/audio/hrtf/__init__.py` — new package
`src/immersive/audio/hrtf/sofa.py` — new: `HrirSet`, `load`, `builtin`
`launch.py` — `--install` fetches, `--check` reports
`THIRD-PARTY-NOTICES.md` — SADIE II D1's row
`docs/08-environment.md` — the fetch, as it now is
`tests/test_hrtf_fetch.py`, `tests/test_sofa.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the digest not checked | a mismatch leaves nothing behind |
| 2 | a mismatched file left in place | a mismatch leaves nothing behind |
| 3 | the download written straight to its final name | an interruption leaves no partial file |
| 4 | left and right swapped (`+cos el · sin az`) | directions in the project's axes |
| 5 | front and back swapped | directions in the project's axes |
| 6 | elevation's sign flipped | directions in the project's axes |
| 7 | no resampling | a 44.1 kHz set comes back at 48 kHz |
| 8 | the convention not checked | the wrong convention is refused |
| 9 | normalised to 0.5 | mean per-ear energy is 0.25 |
| 10 | the factor not kept | the factor on the `HrirSet` |
| 11 | the licence a constant | the licence read from the file |
| 12 | `Data_Delay` dropped | the set with delays keeps them |

## Risks and unknowns

- **The download is 36.6 MB from sofacoustics.org.** A slow or absent
  network makes `--install` fail at the fetch. The rest of the install
  stands, and the application starts and says what is missing. A retry is
  running `--install` again, since a fetched file is kept.
- **`sofar` writes synthetic files with its own defaults**, which may not
  round-trip every field. If one does not, that test builds the arrays
  directly rather than through a file, and says why.
- **`Data_Delay` may be stored per measurement or once for the whole set**,
  since SOFA allows both. Both are expanded to `[M, 2]`.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Loading a set of the person's own from the pane | M8 (F-27); `load()` takes any path already |
| Anything done to the responses beyond resampling and scaling | phase 2 |
| Candidate sets other than SADIE II D1 | phase 13, for listening |

## Outcome

Built as planned. The plan's approach held, and none of its risks
arrived: `sofar` wrote every synthetic set the tests needed, delays
included, and `Data_Delay` broadcast from one row or from one per
measurement. What it got wrong was one test missing, a download killed
part-way, and one test too trusting of its own constant (the 0.25).

What phase 2 needs: `HrirSet.responses`, `[M, 2, N]` float32 at 48 kHz,
normalised; `directions` in the project's axes, never to be converted
again; `delays`, zero for SADIE II D1 but read for the next set; and
`hash` for phase 4's cache key.
