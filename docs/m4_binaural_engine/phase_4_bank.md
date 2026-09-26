# M4 · Phase 4 — The bank, and its cache

**Status:** not started · **Plan:** not written yet

## Goal

`audio/hrtf/bank.py` turns a decomposed set into what the audio thread
convolves with: each minimum-phase response zero-padded to `nfft` and
transformed once, `[M, 2, nfft/2 + 1]` complex64, with the ITDs and the
lookup beside it (05, *4. Prepare the bank*). `nfft` is sized from the
block and the data, never hardcoded. The prepared bank is cached on disk,
keyed by the set's content hash and the block size, so a project opens
without preparing it again.

## Scope

**In:** `nfft = next_pow2(block + N + max_itd_samples - 1)`; the transform
of the bank; its cache in the one user-level cache directory (D-59),
beside the peaks, written atomically and read with a check; preparing the
bank on a worker when a project opens or the block size changes, with the
info box saying so (D-116).

**Out:** convolving with it → phase 5.

## Acceptance

- [ ] For SADIE II D1 at a 512-frame block, `nfft` is 1024, as the spike
      found, and at 2048 frames it is the next power of two the formula
      gives.
- [ ] Each bank entry, transformed back, is its minimum-phase response,
      zero-padded.
- [ ] A second preparation of the same set at the same block is read from
      the cache without transforming, and a different block size prepares
      anew.
- [ ] A cache entry that is truncated or from another format version is
      prepared again, never used, and nothing raises.
- [ ] Preparing the bank on opening a project runs on a worker and shows
      in the info box; the time it takes cold and warm is recorded.

## Implements

*The HRTF pipeline, 4.* in [05-audio-engine.md](../05-audio-engine.md);
D-59, D-116.

## Notes

Appended while building.
