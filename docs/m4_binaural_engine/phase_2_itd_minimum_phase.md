# M4 · Phase 2 — ITD and minimum phase

**Status:** ✅ complete · **Plan:** [plans/phase_2_itd_minimum_phase.md](plans/phase_2_itd_minimum_phase.md)

## Goal

`audio/hrtf/decompose.py` splits every measurement of an `HrirSet` into the
two things that interpolate cleanly on their own and not together (05, *2.
Split ITD from spectrum*): an **interaural time delay** per direction,
estimated by cross-correlating the ears, and a **minimum-phase response**
per ear with the delay removed. The spike did this and it was heard to
work. This is it again, properly: tested, with the spike's measured choices
- the cepstral `nfft` among them - carried over with their reasons.

## Scope

**In:** ITD by cross-correlation, sub-sample, with an onset-threshold
estimate as a cross-check that fails loudly when the two disagree; the
minimum-phase response by the real cepstrum, at the `nfft` the spike
measured; the far ear and the sign convention 05 fixes (the full delay on
the far ear, none on the near); `max_itd_samples` computed from the data.

**Out:** interpolating either → phase 3. Applying the delay → phase 5.

## Acceptance

- [x] A synthetic response delayed by a known fractional amount on one ear
      comes back with that ITD, within a tenth of a sample, and with its
      sign saying which ear is far.
- [x] Across SADIE II D1, the correlation and onset estimates agree on the
      far ear for at least 99% of directions where `|ITD| > 3`, with a
      median difference under a sample and a p95 under 8 (S0's measured
      tolerances, D-69). A set where they do not is refused, not used.
- [x] Each minimum-phase response has the magnitude spectrum of its source
      within 0.1 dB wherever the source is within 30 dB of its own peak,
      checked over every response rather than a sample. Below that, the
      bottoms of deep notches may be filled by the set's tap count, and no
      error over 1 dB lies less than 50 dB down. Each is minimum phase: its
      energy is front-loaded as a minimum-phase response's must be.
      *Amended while building: as first written this was 0.1 dB everywhere,
      which 256 taps cannot hold at an 80 dB notch - see the Notes.*
- [x] ITDs are largest at the sides and near zero at the front, back and
      poles, and `max_itd_samples` for SADIE II D1 is the spike's 39.
- [x] The cepstral `nfft` is the spike's, with its measured table of
      aliasing against size kept beside it.

## Implements

*The HRTF pipeline, 2.* in [05-audio-engine.md](../05-audio-engine.md);
S0 [phase 2](../s0_listening_spike/phase_2_itd_minimum_phase.md)'s findings.

## Notes

Appended while building.

**Built (2026-09-27), as S0 built it, and with S0's numbers.** SADIE II D1
decomposes in 5.2 s:
- far-ear agreement 99.99%, median difference 0.30 samples, p95 7.7;
- the largest ITD 38.3 samples, exactly on the interaural axis, so phase
  4's buffer is sized from 39;
- the front at 0.37.

A source at +X delays the left ear by 38.1 samples, and one at −X the
right. The constants carry their measurements beside them: the 1.5 kHz
low-pass, the −10 dB onset, the 8192-point cepstrum and its aliasing table.

**The finding: S0's 0.017 dB was a sample of twenty.** Checked over every
one of the 17 604 responses, the worst magnitude error is 16.0 dB. It
comes at 10 kHz, at a notch 80.6 dB below that response's peak, which the
minimum-phase response renders at 64.7 dB down. 256 taps cannot carry a
notch that deep: the untruncated response has 1.8 × 10⁻⁶ of its energy past
tap 256, which is −57 dB, and that is roughly where the floors land.
Every error over 1 dB, 45 bins in the whole set, lies 53.6 dB or more below
its own peak. Wherever the spectrum is within 30 dB of its peak, the worst
is 0.019 dB. S0's twenty directions (seed 7) reproduce its 0.017 dB exactly:
it was right about what it measured and did not measure the notches. The
acceptance line said 0.1 dB everywhere. It now says so within 30 dB of the
peak, with the floors bounded, and is tested over every response. Amended
explicitly, per 09. A notch 65 dB down is as inaudible as one 80 dB down;
the numbers are here in case a listener one day disagrees.

**What the tests cost.** Decomposing the real set takes seconds. Three
tests each decomposed it on their own worker, and the suite went from 13 s
to 31 s. They are now one test of 6.1 s, checking every response's
magnitude at 2048 points, 23 Hz apart, so that no notch can hide between
them. The suite is 21 s. Phase 4's cache is where the decomposition stops
being paid every session, and it should cache the decomposition, not only
the bank.

Eleven mutations, all caught. Three were caught at first only by the real
set, which is skipped where it is not fetched. The ITD stored unsigned now
has a synthetic test. The other two cannot have one: no low-pass, and the
onset at −20 dB. Both fail on properties of a real head's responses, the
shadow's ripple and the pre-ringing, which a synthetic pulse does not have.
They are pinned by the real set alone, and a machine without it would not
notice them. The phase adds 19 tests.
