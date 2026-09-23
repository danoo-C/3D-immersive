# Plan — M1 · Phase 2 — Curve evaluation

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

`Curve.value_at(t)` finds the bracketing keyframe pair and evaluates according
to the **left** keyframe's `interp`, which is what
[03-data-model.md](../../03-data-model.md) means by "governs the segment
*after* it". Bracketing is a binary search over a list already sorted by `t`
(a [phase 1](../phase_1_dataclasses.md) invariant the validator enforces), so
this is `bisect` and not a scan.

`hold` and `linear` are one line each. `ease` is a cubic Bézier through
`(t, value)` with the left keyframe's `outgoing` and the right keyframe's
`incoming` as control points, which needs a root find: a query arrives as a
*time*, and a Bézier is parameterised by `u`, so `B_x(u) = t` has to be solved
before `B_y(u)` can be evaluated.

**Newton-Raphson with a bisection fallback**, the same shape browsers use for
CSS `cubic-bezier`. Newton alone can step outside the bracket on a
near-flat segment; keeping a `[lo, hi]` bracket and bisecting whenever Newton
escapes it makes the solve unconditionally convergent for the price of two
comparisons. Measured over 20 000 random curves: **mean 4.6 iterations, worst
8, residual ≤ 1e-9, 2.8 µs a solve**. M4 calls this roughly 12 000 times a
second (32 channels × 4 parameters × 94 blocks), which is about 3% of one
core — acceptable, and not the thing to optimise before the FFT.

## ⚠️ One acceptance line is wrong and has to be replaced

The phase doc asks for a property test where the result is *"always within the
range of the keyframe values it sits between"*. **That is not true of a Bézier
and should not be.** Measured over 50 000 random handle pairs, **86% overshoot
the endpoint values**, and deliberately so: handles of `(0.0, 1.6)` between
endpoints 0 and 1 peak at **1.135**, which is the "ease out back" shape — a
source that flies slightly past its target and settles. `03` clamps `dt` and
says nothing about `dv`, which is the right call; clamping value would delete a
wanted effect to satisfy a test.

**The replacement is the convex-hull property**, which is a real guarantee
rather than a weakened one: a Bézier curve lies within the convex hull of its
control points, so `B_y(u)` is always inside
`[min, max]` of its **four** control values — the two keyframes *and* the two
handle-displaced points. Verified at 200 000 curves × 51 samples with **zero
violations**.

That still catches everything the original line was reaching for. A solver
that returns the wrong `u`, diverges, or reads the wrong keyframe produces a
value outside the hull almost immediately, while legitimate overshoot stays
inside it. Amending explicitly, per [09](../../09-workflow.md).

## The clamp, and why it is sufficient

`03` requires handle `dt` to be clamped "so the curve can never double back in
time". The clamp is: **control point x's into `[t_left, t_right]`**.

That is sufficient, and it is worth recording why, because the obvious worry —
that an outgoing handle reaching past an incoming one still folds the curve —
turns out not to happen. `B_x'(u)` is a quadratic Bézier with control values
`(x1-x0, x2-x1, x3-x2)`, and with both interior points inside the span its
minimum on `[0, 1]` is non-negative. Measured at 200 000 random curves ×
201 samples: **the minimum derivative never went below 0**. Monotonic in time
means a query time maps to exactly one `u`, which is what makes the solve
well-posed at all.

Clamped **at evaluation, not on the stored keyframe**. What someone typed is
theirs; a clamp that rewrites the data loses the original when the neighbouring
keyframe later moves and the handle would have been legal again.

## Steps

1. **Bracketing.** Given `t`, find the keyframe pair to interpolate between,
   plus the before-first and after-last cases.
   *Test:* `bisect` agrees with a linear scan over pseudo-random curves;
   querying exactly at a keyframe's `t` selects it as the *left* of its pair,
   so `interp` governs the segment after it as `03` says.

2. **`hold` and `linear`.**
   *Test:* `hold` holds the left value until the right keyframe and changes
   **at** it, not one sample either side — an off-by-one here is a click at M4
   and invisible until then. `linear` hits both endpoints exactly at their own
   `t`.

3. **The Bézier solve.** Control points from the two keyframes and their facing
   handles; the `dt` clamp; Newton with the bisection fallback.
   *Test:* with collinear handles `ease` reproduces `linear` to 1e-9 — the
   cheapest proof the solver is not subtly wrong in a way that still looks like
   a curve. Residual `|B_x(u) - t| < 1e-9` across random curves, and the
   iteration count is bounded.

4. **Edges.** Flat hold before the first keyframe and after the last whatever
   the interp; the single-keyframe curve; the empty curve.
   *Test:* each stated explicitly. Empty raises rather than returning a
   plausible zero — the channel's fallback to its static `position` is the
   caller's decision ([phase 1](../phase_1_dataclasses.md)'s rule), and a
   silent 0.0 would put a source at the origin and look like a bug in M5.

5. **Purity, and the property test.** Same arguments in, same value out,
   nothing mutated — M4 calls this from the audio thread.
   *Test:* the convex-hull bound above, over seeded random curves including
   extreme handles; results always finite; calling twice returns identical
   values and leaves the curve unchanged, handles included.

Five steps, inside the six [09](../../09-workflow.md) allows.

## Files

```
src/immersive/core/curves.py    amended — value_at, the solve, the clamp
tests/test_curves.py            amended — evaluation and the property test
docs/m1_core_model/phase_2_curve_evaluation.md   amended — the acceptance line
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The off-by-one at a keyframe boundary | A click at M4, blamed on the scheduler or the crossfade, three milestones from here | Step 1 and 2 both assert the boundary explicitly rather than testing a midpoint and assuming the ends |
| Newton stalls on a near-flat segment | A hang, or a silently wrong value | The bracket is kept and bisected whenever Newton's step escapes it, so the iteration count is bounded by construction rather than by hope. Measured worst case 8 |
| Float `t` versus int `t` | Keyframe `t` is int samples; a query at a non-integer time is meaningful for M6's drawing but not for M4 | Accept a float `t`, return a float value, and say so. Nothing rounds |
| The clamp is applied to the stored keyframe by accident | The user's handle is destroyed the first time a neighbour moves | Clamping happens inside the evaluator on a local copy; step 5 asserts the curve is unchanged after evaluation |
| `ease` on the *last* keyframe, which has no segment after it | An index error, or a silent wrong answer | It is the after-last case: hold flat. Covered in step 4 |

The genuine unknown is **whether `value_at` should be the hot-path shape at
all**. M4 wants one value per channel per parameter per block, and calling a
Python method 12 000 times a second to get it is 3% of a core before any DSP
runs. It is fine for M1, M3 and M6, and M4 may want a vectorised sampler over a
whole block instead. This phase does not guess: it keeps `value_at` pure and
side-effect free, which is what makes a batched version a later addition rather
than a rewrite.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The curve *editor*, dragging handles, the interpolation menu | M6 |
| Reading curves per block, and any vectorised sampler | M4 |
| Which parameters are automatable | Settled data: F-28, and [phase 1](../phase_1_dataclasses.md)'s `Interpolatable` |
| The channel's fallback to its static `position` when a curve is absent | [Phase 1](../phase_1_dataclasses.md) states the rule; M4 and M5 are the first callers that need it |
| Serialising handles as `in`/`out` | [Phase 5](../phase_5_project_io.md) |

## Outcome

**Every acceptance line passes.** The finished evaluator costs 2.55 µs eased
and 0.49 µs linear — the microbenchmark held up, since the solve is almost all
of the work.

**What the plan got right.** Catching the overshoot line before writing code.
It would have failed on 86% of random handles, and the natural reaction to a
failing property test is to suspect the solver rather than the assertion.

**What it got wrong, and it is the same mistake in two places.** The plan
argued at length for the `dt` clamp and the bisection bracket, and then
specified tests that could not tell whether either was present. Both mutations
survived the first suite.

- The clamp test asserted **finiteness and monotonicity**, and an unclamped
  implementation has both: the solver's bisection copes with a non-monotonic
  `B_x` well enough to return monotonic output. What the clamp actually changes
  is the *shape*, by up to 0.18 in value. Fixed by asserting that two handles
  differing only past the boundary give an identical curve.
- The bracket turned out to be **genuinely unobservable**: 400 000 random
  curves, worst divergence 4.6e-9. The slope guard already bisects wherever
  Newton would escape. It stays as cheap defence in depth, and the phase Notes
  say plainly that no test covers it rather than implying one does.

The lesson is narrower than "write better tests": arguing hard for a mechanism
in a plan creates a pull toward writing a test that *mentions* it rather than
one that *distinguishes* it. Running the mutation is what separates the two,
and it took four minutes.

**Unrelated but worth recording:** `zip(a, a[1:], strict=True)` raises, because
zipping a list with its own tail is deliberately unequal. Same slip as in S0
phase 1. `itertools.pairwise` is the right tool and ruff says so.
