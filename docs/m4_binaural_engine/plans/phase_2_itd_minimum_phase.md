# Plan — M4 · Phase 2 — ITD and minimum phase

**Written:** 2026-09-27 · **Status:** planned

## Approach

`audio/hrtf/decompose.py`, one function, `decompose(hrirs) -> Decomposed |
Refused`, porting S0 phase 2's heard-and-measured construction rather than
redesigning it. Four parts.

**The ITD, by cross-correlation (D-69).** Both ears go through a zero-phase
4th-order Butterworth low-pass at 1.5 kHz. S0 measured that without it the
largest ITD on the sphere, 44 samples, lands somewhere other than the
poles, which can only be a spurious peak. The ears are then
cross-correlated over ±128 lags, and the peak refined by a parabola through
its three samples. The ITD is kept **signed**: positive when the left ear
is the later, far one. Phase 3 interpolates it, and averaging magnitudes
across the median plane turns +30 and −30 into 30, a delay pointing the
wrong way at full strength. Delays the file stores (`Data_Delay`) are added
as the difference between the ears.

**The cross-check, by onset (D-69).** Fullband, the first crossing of −10 dB
of each ear's own peak, linearly interpolated. It shares nothing with the
correlation, which is its whole value. It is not a second opinion on the
size of the delay, since the two measure the dominant arrival and the first
one. It checks the side. Where `|ITD| > 3` samples, at least 99% of
directions must agree on which ear is far. A set that fails is refused as
mirrored or malformed, with the share that agreed. The median signed
difference and the p95 are reported beside it.

**The minimum-phase responses, by the real cepstrum.** At a cepstral `nfft`
of 8192, which S0 measured: 5.5 dB of error at the pinna notches with the
textbook 4×, and 0.017 dB at 32×. The magnitude is floored at −100 dB of
each response's peak, so a notch's `log(0)` cannot make every tap NaN. The
cepstrum is folded causal, and the result truncated back to the set's taps.
It is chunked 512 measurements at a time, as S0 found necessary, so memory
stays around 70 MB rather than several GB. The table of error against
`nfft` is kept beside the constant.

**`max_itd`**, the largest magnitude over the set, from the data, never a
constant. Phase 4 sizes its buffer from its ceiling.

The alternative was estimating the ITD from the minimum-phase split's
discarded excess phase. It was rejected because S0 measured the split's
residual as large and entirely phase. That was heard to be fine, but it
makes the excess phase a poor place to read a delay from.

## Decisions settled here

**The ITD is signed, positive when the left ear is far.** One representation
from here to the engine. Phase 5 turns it into a non-negative delay on the
far ear, as 05 requires.

**A set whose estimators disagree on the far ear is refused**, not used.
Below 99% agreement where there is a side to get wrong, the likeliest
causes are a mirrored set, swapped ears or a spurious peak, and each is a
quietly mirrored mix three phases on.

## Steps

1. **The ITD and its cross-check.** `itd()`, `onset_itd()`, the low-pass.
   Tests:
   - a synthetic pair delayed by a known fractional amount comes back
     within a tenth of a sample, with its sign, and its mirror image comes
     back with the other sign;
   - an ITD of 12 comes back as 12, which a constant tuned to SADIE's 39
     would fail;
   - a set built so that onset and correlation disagree on the far ear is
     refused, with the share;
   - stored delays shift the ITD by their difference.
2. **Minimum phase.** `minimum_phase()`, chunked. Tests:
   - the magnitude is within 0.1 dB of the source's over 100 Hz – 16 kHz;
   - over 90% of the energy falls in the first quarter of the taps, which
     a maximum-phase fold would fail;
   - a response with an exact null does not come back NaN.
3. **`decompose()` and SADIE II D1.** The `Decomposed` set, `max_itd`, and
   the checks on the real set where it is fetched:
   - agreement on the far ear ≥ 99% where `|ITD| > 3`, a median difference
     under 1 sample, and a p95 under 8;
   - the front near zero, the largest ITD at the interaural axis, and
     `ceil(max_itd)` is 39;
   - the whole set decomposes in a time recorded in the Notes.

## Files

`src/immersive/audio/hrtf/decompose.py` — new
`tests/test_decompose.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | the ITD's sign reversed | the synthetic pair and its mirror |
| 2 | no low-pass | SADIE's largest ITD at the axis, and 39 |
| 3 | no parabolic refinement | within a tenth of a sample |
| 4 | the magnitude stored, unsigned | the mirror comes back with the other sign |
| 5 | the cross-check never refuses | the disagreeing set is refused |
| 6 | the onset threshold at −20 dB | SADIE's agreement ≥ 99% |
| 7 | the cepstral `nfft` at 1024 | the magnitude within 0.1 dB |
| 8 | the fold anticausal (maximum phase) | 90% of the energy in the first quarter |
| 9 | no floor under the magnitude | an exact null does not come back NaN |
| 10 | stored delays ignored | stored delays shift the ITD |
| 11 | `max_itd` a constant | an ITD of 12 comes back as 12 |

## Risks and unknowns

- **Decomposing all 8802 directions took S0 7.6 s**, most of it the
  minimum-phase pass at 8192. On opening a project that is too long to
  repeat every time. Phase 4's cache is where it stops being paid twice,
  and that phase should cache the decomposition as well as the bank.
- **A synthetic fractional delay is only as good as the pulse carrying it.**
  A band-limited pulse, delayed in the frequency domain, is used, so the
  delay is exact and the test measures the estimator rather than the
  stimulus.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Interpolating the ITD or the responses | phase 3 |
| Applying the delay as a phase ramp | phase 5 |
| Caching the decomposition | phase 4 |

## Outcome

Filled in at the end.
