# M4 · Phase 4 — The bank, and its cache

**Status:** planned · **Plan:** [plans/phase_4_bank.md](plans/phase_4_bank.md)

## Goal

`audio/hrtf/bank.py` turns a decomposed set into what the audio thread
convolves with: each minimum-phase response zero-padded to `nfft` and
transformed once, `[M, 2, nfft/2 + 1]` complex64, with the ITDs and the
lookup beside it (05, *4. Prepare the bank*). `nfft` is sized from the
block and the data, never hardcoded. What is slow to make - the
decomposition and the direction index - is cached on disk, keyed by the
set's content hash, so a project opens without making it again. The bank
is transformed from it at the block's size on load (D-120).

## Scope

**In:** `nfft = next_pow2(block + N + max_itd_samples - 1)`; the transform
of the bank; the cache of the decomposition and index, in the one
user-level cache directory (D-59) beside the peaks, written atomically and
read with a check; preparing the bank on a worker when the application
starts or a project opens, with the info box saying so (D-116), and
stopping when the window closes.

**Out:** convolving with it → phase 5.

## Acceptance

- [ ] For SADIE II D1 at a 512-frame block, `nfft` is 1024, as the spike
      found, and at 2048 frames it is the next power of two the formula
      gives.
- [ ] Each bank entry, transformed back, is its minimum-phase response,
      zero-padded.
- [ ] A second preparation of the same set is read from the cache without
      decomposing, and a different block size is served by the same entry,
      transformed anew (D-120).
- [ ] A cache entry that is truncated or from another format version is
      prepared again, never used, and nothing raises.
- [ ] Preparing the bank on opening a project runs on a worker and shows
      in the info box; the time it takes cold and warm is recorded.

## Implements

*The HRTF pipeline, 4.* in [05-audio-engine.md](../05-audio-engine.md);
D-59, D-116.

## Notes

Appended while building.

**Amended before the phase started.** 05 said the bank is cached, keyed by
hash and block size. Measured while planning, the bank is the cheap part:
0.11 s to transform, against 6.5 s to decompose and index. Caching it per
block would store 72 MB to 289 MB per block size to save that fraction of
a second. The Goal, Scope and one acceptance line were corrected to D-120
before any code.
