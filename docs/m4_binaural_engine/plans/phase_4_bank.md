# Plan — M4 · Phase 4 — The bank, and its cache

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

**`audio/hrtf/bank.py`: `prepare(hrirs, block, cache, progress) -> Bank |
Refused | Cancelled`.** A `Bank` is what the engine convolves with:
- the minimum-phase responses zero-padded to `nfft` and transformed,
  `[M, 2, nfft/2 + 1]` complex64;
- the signed ITDs, the directions and their `Lookup`;
- `nfft = next_pow2(block + taps + ceil(max_itd) − 1)`, from the data.

**The cache is the slow part, not the bank (D-120).** Keyed by the set's
content hash alone, one entry per set in the cache directory (D-59), under
`hrtf/`. It holds the minimum-phase responses, the ITDs, `max_itd`, the
directions, and the lookup's arrays: faces, inverses, neighbours, and the
cells as one flat array with offsets. It is written through a temporary file
and a rename, as the peaks are. A read that finds another format version, a
different set, a truncated file or shapes that disagree is a miss, and the
set is decomposed again. The transform is done on every load: 0.11 s at 512
frames.

**Progress and cancel**, as an import has (F-59). `decompose()` and
`Lookup.build()` take an optional `Part`. The minimum-phase pass moves it a
chunk at a time and checks for a cancel between chunks, and the index
checks between its six cube faces. So a window closed while a set is being
prepared stops within a chunk, rather than holding the close for the whole
6.5 s.

**The window: `ui/hrtf.py`'s `Preparer`.** Its own `QThreadPool`, one job at
a time. It prepares the project's set (`HrtfRef.id`, the built-in) at the
player's block size, with an activity, *Preparing the HRTF set*, that moves
with the progress (D-116), and hands the result to the window. A set that is
not fetched becomes one `warn` notice naming the command that fetches it.
`app.run` asks for it once the window is up, and opening a project whose set
differs asks again. A window built by a test asks for nothing, so no test
pays for SADIE by constructing a window. Closing cancels it.

## Decisions settled here

**D-120**: the decomposition and the index are cached once per set; the bank
is made from them at the block's size on load.

**Nothing prepares a set until the application asks.** `app.run`, and an
open, do; constructing a window does not.

## Steps

1. **`Lookup` from arrays, and the bank.** Split `Lookup.build` into
   computing its arrays and assembling them, so a cached index is
   assembled without the hull. Add `bank.py`: `fft_size`, `prepare`, the
   cache read and write, progress and cancel through `decompose` and
   `build`. Tests:
   - `nfft` is 1024 for SADIE at 512 frames and 4096 at 2048;
   - each bank entry, transformed back, is its minimum-phase response,
     zero-padded;
   - a second preparation is read from the cache without decomposing, and
     the same entry serves another block size;
   - an entry truncated, of another format, or for another set is prepared
     again, and nothing raises;
   - a cancel stops the decomposition between chunks.
2. **The `Preparer` and the window.** The worker, the activity, the notice,
   `app.run` and an open asking, and a close cancelling. Tests, with a
   small synthetic set in place of SADIE:
   - the activity shows while it prepares and goes when it lands;
   - a set not fetched is one `warn`, naming `launch.py --install`;
   - a close stops it;
   - a window built directly prepares nothing.
3. **Measured and written down.** SADIE cold and warm through `prepare()`,
   recorded. 05's *4. Prepare the bank* and 02's layout, updated.

## Files

`src/immersive/audio/hrtf/bank.py` — new: `Bank`, `fft_size`, `prepare`
`src/immersive/audio/hrtf/lookup.py` — `Lookup` assembled from arrays;
progress
`src/immersive/audio/hrtf/decompose.py` — progress and cancel
`src/immersive/ui/hrtf.py` — new: `Preparer`
`src/immersive/ui/main_window.py` — `prepare_hrtf()`, `bank()`, close
`src/immersive/app.py` — asking once the window is up
`docs/05-audio-engine.md`, `docs/02-architecture.md`
`tests/test_bank.py`, `tests/test_hrtf_in_the_window.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | `nfft` without the ITD term | 4096 at 2048 frames, 1024 at 512 |
| 2 | `nfft` from a constant 39 | a synthetic set's own ITD |
| 3 | the cache's format not checked | an entry of another format prepared again |
| 4 | the cache's set not checked | an entry for another set prepared again |
| 5 | a truncated entry read | an entry truncated prepared again |
| 6 | written straight to its name | nothing half-written is read (a killed write) |
| 7 | the cache keyed by block too | the same entry serves another block |
| 8 | a cancel not checked between chunks | a cancel stops between chunks |
| 9 | the lookup's cells reassembled out of order | a cached bank weighs as a fresh one |
| 10 | a window prepares on construction | a window built directly prepares nothing |
| 11 | a close does not cancel | a close stops it |

## Risks and unknowns

- **The bank is 72 MB at 512 frames and 289 MB at 2048.** It is held for
  the session. At the largest block that is a real share of a small
  machine's memory, and it is recorded rather than solved here. If it
  bites, the bank can hold float16 spectra, or fewer directions where the
  set is densest.
- **A test that constructs a window with a player**, which dozens do, must
  not start SADIE's decomposition. The design makes that the default: only
  `app.run` and an open ask. Mutation 10 is there to keep it so.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Convolving with the bank | phase 5 |
| A second built-in set, or the person's own | phase 9's candidates; M8 |

## Outcome

Built as planned. D-120, settled while planning, held: the bank is made in
0.11 s from a 21 MB entry that serves every block size. Mutation 6, written
straight to its name, is equivalent. A half-written `.npz` has no zip
directory and reads as a miss, so the temporary file only spares a failed
read; it is kept, as the peaks do, for the reason its docstring gives.

What phase 5 needs: `window.bank()`, a `Bank` with `filters` `[M, 2,
nfft/2 + 1]`, `itd` signed, `lookup` to weigh and blend, and `nfft` for
its buffers. It is `None` until prepared, and stays `None` without an
output or a fetched set. The engine has to play without it, flat, as it
does today.
