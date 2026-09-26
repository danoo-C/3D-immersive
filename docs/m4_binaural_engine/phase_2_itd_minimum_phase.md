# M4 · Phase 2 — ITD and minimum phase

**Status:** planned · **Plan:** [plans/phase_2_itd_minimum_phase.md](plans/phase_2_itd_minimum_phase.md)

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

- [ ] A synthetic response delayed by a known fractional amount on one ear
      comes back with that ITD, within a tenth of a sample, and with its
      sign saying which ear is far.
- [ ] Across SADIE II D1, the correlation and onset estimates agree on the
      far ear for at least 99% of directions where `|ITD| > 3`, with a
      median difference under a sample and a p95 under 8 (S0's measured
      tolerances, D-69). A set where they do not is refused, not used.
- [ ] Each minimum-phase response has the magnitude spectrum of its source
      within 0.1 dB, and is minimum phase: its energy is front-loaded as a
      minimum-phase response's must be, checked against the source's.
- [ ] ITDs are largest at the sides and near zero at the front, back and
      poles, and `max_itd_samples` for SADIE II D1 is the spike's 39.
- [ ] The cepstral `nfft` is the spike's, with its measured table of
      aliasing against size kept beside it.

## Implements

*The HRTF pipeline, 2.* in [05-audio-engine.md](../05-audio-engine.md);
S0 [phase 2](../s0_listening_spike/phase_2_itd_minimum_phase.md)'s findings.

## Notes

Appended while building.
