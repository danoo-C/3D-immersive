# M1 · Phase 2 — Curve evaluation

**Status:** not started · **Plan:** not written yet

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

- [ ] `hold` holds the left keyframe's value until the right one, and changes
      exactly at the right one — not one sample early or late. An off-by-one
      here is a click in M4 and nowhere visible before then.
- [ ] `linear` interpolates, and hits both endpoints exactly at their own `t`.
- [ ] `ease` solves the cubic bezier for `t` and evaluates for value, and
      reproduces `linear` to within 1e-9 when the handles are set to the
      collinear case. That equivalence is the cheapest proof the solver is not
      subtly wrong in a way that still looks like a curve.
- [ ] **Handle `dt` is clamped so the curve cannot double back in time**
      ([03](../03-data-model.md), *Evaluating a curve*). Asserted with handles
      deliberately set past the far keyframe: the result stays monotonic in
      time, and the clamp is applied at evaluation rather than mutating what
      the user typed.
- [ ] Before the first keyframe and after the last, the curve holds flat —
      whatever the interpolation mode of the keyframe involved.
- [ ] A curve with one keyframe returns that value for all `t`; a curve with
      none is not asked (the channel falls back to its static `position`
      component, which is [phase 1](phase_1_dataclasses.md)'s rule, and a test
      covers the fallback rather than leaving it implied).
- [ ] Evaluation is a pure function of the curve and `t`: called twice with the
      same arguments it returns the same value, and it mutates nothing. M4
      calls this from the audio thread.
- [ ] A property test over pseudo-random curves with a fixed seed: the result
      is always finite, and always within the range of the keyframe values it
      sits between. `ease` with extreme handles is the case that breaks this if
      the solver is wrong.

## Implements

F-28, F-29. The *Evaluating a curve* section of
[03-data-model.md](../03-data-model.md). D-7 governs where keyframes live in
time, which this phase reads and does not decide.

## Notes

Appended while building.
