# M1 · Phase 2 — Curve evaluation

**Status:** ✅ complete · **Plan:**
[plans/phase_2_curve_evaluation.md](plans/phase_2_curve_evaluation.md)

## Goal

`Curve.value_at(t)` returns the right number for every interpolation mode, at
every `t`, including the awkward ones — before the first keyframe, after the
last, exactly on one, and between two with bezier handles. After this phase a
channel's automation describes a trajectory rather than a list of points.

The engine calls this once per channel per parameter per block, so it has to be
correct at the boundaries far more than it has to be fast.

## Scope

**In:** `linear`, `hold` and `ease` evaluation; the cubic bezier solve for
`ease`; handle clamping so a curve cannot double back in time; flat hold before
the first keyframe and after the last; the single-keyframe and empty-curve
cases; sampling a curve across a range.

**Out:** the curve *editor* and its bezier handles as a UI → M6. Reading curves
per block → M4. Which parameters are automatable is a data question already
settled by F-28; this phase evaluates whatever it is given.

## Acceptance

- [x] `hold` holds the left keyframe's value until the right one, and changes
      exactly at the right one — not one sample early or late. An off-by-one
      here is a click in M4 and nowhere visible before then.
- [x] `linear` interpolates, and hits both endpoints exactly at their own `t`.
- [x] `ease` solves the cubic bezier for `t` and evaluates for value, and
      reproduces `linear` to within 1e-9 when the handles are set to the
      collinear case. That equivalence is the cheapest proof the solver is not
      subtly wrong in a way that still looks like a curve.
- [x] **Handle `dt` is clamped so the curve cannot double back in time**
      ([03](../03-data-model.md), *Evaluating a curve*). Asserted with handles
      deliberately set past the far keyframe: the result stays monotonic in
      time, and the clamp is applied at evaluation rather than mutating what
      the user typed.
- [x] Before the first keyframe and after the last, the curve holds flat —
      whatever the interpolation mode of the keyframe involved.
- [x] A curve with one keyframe returns that value for all `t`; a curve with
      none is not asked (the channel falls back to its static `position`
      component, which is [phase 1](phase_1_dataclasses.md)'s rule, and a test
      covers the fallback rather than leaving it implied).
- [x] Evaluation is a pure function of the curve and `t`: called twice with the
      same arguments it returns the same value, and it mutates nothing. M4
      calls this from the audio thread.
- [x] A property test over pseudo-random curves with a fixed seed: the result
      is always finite, and always within the **convex hull of the four control
      values** — the two keyframes and their two handle-displaced points.

> **Amended before building.** This line asked for the result to stay "within
> the range of the keyframe values it sits between", and a Bézier does not do
> that and should not: measured over 50 000 random handle pairs, 86% overshoot
> the endpoints, and handles of `(0.0, 1.6)` between 0 and 1 peak at 1.135 —
> the "ease out back" shape, a wanted effect. `03` clamps `dt` and deliberately
> not `dv`. The convex-hull bound is a real guarantee rather than a weakened
> one (200 000 curves × 51 samples, zero violations) and still catches a solver
> that returns the wrong `u`, diverges, or reads the wrong keyframe. Amended
> explicitly per [09-workflow.md](../09-workflow.md); reasoning in
> [the plan](plans/phase_2_curve_evaluation.md).

## Implements

F-28, F-29. The *Evaluating a curve* section of
[03-data-model.md](../03-data-model.md). D-7 governs where keyframes live in
time, which this phase reads and does not decide.

## Notes

**Done. Every acceptance line passes**, one of them after being amended before
any code was written — see the note above the *Implements* section.

Measured cost of the finished evaluator: **2.55 µs** for an `ease` call,
0.49 µs for `linear`. At M4's roughly 12 000 calls a second that is about 3% of
one core, matching what the plan predicted from the solver alone.

### The tests were checked by breaking the code, and two of them were weak

Five deliberate mutations, each run against the suite:

| mutation | caught |
|---|---|
| `bisect_right` → `bisect_left` | ✅ two tests |
| `hold` returns the right value | ✅ two tests |
| linear interpolation reversed | ✅ three tests |
| drop the `dt` clamp | ❌ at first |
| Newton without the bisection bracket | ❌ still |

The clamp and the bracket are the two things the plan argued hardest for, and
neither was covered by the tests written to cover them.

**The clamp test was asserting the wrong property.** It checked that the curve
stays finite and monotonic, and an unclamped implementation does both — the
solver's bisection copes with a non-monotonic `B_x` well enough to return a
monotonic result anyway. What the clamp *does* change is the shape: up to
**0.18 in value** on the cases tried. So the test now asserts that two handles
differing only *past* the boundary produce an identical curve, with a second
assertion that a handle inside the span gives a genuinely different one, so it
cannot pass by everything being equal. That catches the mutation.

⚠️ **The bisection bracket is not observable and the suite does not claim it
is.** Searched 400 000 random in-range curves comparing the bracketed solver
against one that takes Newton's step unconditionally: worst divergence
**4.6e-9**, which is the tolerance. The slope guard in front of it already
falls back to bisection whenever the derivative is small, which is where Newton
would otherwise escape — so on everything findable the two are the same
function. It stays because it costs two comparisons and bounds the iteration
count by construction rather than by argument, but it is defence in depth, not
a tested behaviour, and pretending otherwise would be worse than saying so.

### Inherited by M4 and M6

| | |
|---|---|
| `Curve.value_at(t)` | float in, float out, pure; raises on an empty curve |
| `Curve.sample(start, stop, count)` | both ends included, for drawing a trajectory |
| cost | 2.55 µs eased, 0.49 µs linear |
| empty curves | raise rather than returning 0.0 — a silent zero would put a source at the origin and read as an M5 bug |

The plan's open question stands: `value_at` is the right shape for M1, M3 and
M6, and M4 may want a batched sampler over a whole block instead. Keeping it
pure and side-effect free is what makes that an addition rather than a rewrite.
