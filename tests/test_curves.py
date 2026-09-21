"""Curve and Keyframe as containers. Evaluation is phase 2."""

from __future__ import annotations

import math
import random
from copy import deepcopy
from itertools import pairwise

import pytest

from immersive.core.curves import Curve, Handles, Interp, Keyframe, _bezier, _solve_u


def test_an_empty_curve_is_well_formed() -> None:
    assert Curve().problems() == []


def test_a_sorted_curve_with_unique_times_is_well_formed() -> None:
    assert Curve([Keyframe(0, 0.0), Keyframe(100, 1.0)]).problems() == []


def test_out_of_order_keyframes_are_reported() -> None:
    problems = Curve([Keyframe(100, 1.0), Keyframe(0, 0.0)]).problems()
    assert any("not sorted" in p for p in problems)


def test_duplicate_times_are_reported_with_the_times() -> None:
    """A keyframe has no id and is identified by t, so two at one time are the
    same keyframe twice."""
    problems = Curve([Keyframe(0, 0.0), Keyframe(0, 1.0)]).problems()
    assert any("duplicate keyframe times: [0]" in p for p in problems)


def test_ease_without_handles_is_reported() -> None:
    problems = Curve([Keyframe(0, 0.0, Interp.EASE)]).problems()
    assert any("ease with no handles" in p for p in problems)


def test_ease_with_handles_is_fine() -> None:
    curve = Curve([Keyframe(0, 0.0, Interp.EASE, Handles((240.0, 0.5)))])
    assert curve.problems() == []


def test_interp_serialises_as_the_string_the_file_format_uses() -> None:
    """A StrEnum, so project_io writes these values with no mapping table."""
    assert [member.value for member in Interp] == ["linear", "ease", "hold"]


def test_handles_are_named_for_readability_not_for_the_file() -> None:
    """`in` is a Python keyword; project_io maps these back to in/out."""
    handles = Handles(outgoing=(24000.0, 0.0), incoming=(-24000.0, 0.0))
    assert handles.outgoing == (24000.0, 0.0)
    assert handles.incoming == (-24000.0, 0.0)


# --------------------------------------------------------------------------- #
# phase 2 — evaluation
# --------------------------------------------------------------------------- #


def _linear_handles(left: Keyframe, right: Keyframe) -> tuple[Handles, Handles]:
    """Handles that make an `ease` segment identical to a `linear` one.

    A cubic Bezier degenerates to a straight line exactly when its control
    points are collinear *and* evenly spaced — each a third of the way along.
    """
    dt = (right.t - left.t) / 3.0
    dv = (right.value - left.value) / 3.0
    return Handles(outgoing=(dt, dv)), Handles(incoming=(-dt, -dv))


# --- bracketing -------------------------------------------------------------


def test_a_query_on_a_keyframe_treats_it_as_the_left_of_its_pair() -> None:
    """03: interp governs the segment *after* its keyframe."""
    curve = Curve([Keyframe(0, 0.0, Interp.HOLD), Keyframe(100, 1.0)])
    assert curve.value_at(0) == 0.0
    assert curve.value_at(99) == 0.0
    # At 100 the pair advances, so the left keyframe is now the one at 100.
    assert curve.value_at(100) == 1.0


def test_bracketing_agrees_with_a_linear_scan() -> None:
    rng = random.Random(4)
    times = sorted(rng.sample(range(0, 100_000), 40))
    curve = Curve([Keyframe(t, rng.uniform(-5, 5)) for t in times])
    for _ in range(2_000):
        t = rng.uniform(-5_000, 105_000)
        scanned = [k for k in curve.keyframes if k.t <= t]
        expected = scanned[-1] if scanned else curve.keyframes[0]
        if t >= curve.keyframes[-1].t or t < curve.keyframes[0].t:
            assert curve.value_at(t) == expected.value
        else:
            following = curve.keyframes[curve.keyframes.index(expected) + 1]
            assert min(expected.value, following.value) - 1e-9 <= curve.value_at(t)
            assert curve.value_at(t) <= max(expected.value, following.value) + 1e-9


# --- hold and linear --------------------------------------------------------


def test_hold_changes_at_the_right_keyframe_not_beside_it() -> None:
    """An off-by-one here is a click at M4 and invisible until then."""
    curve = Curve([Keyframe(0, 5.0, Interp.HOLD), Keyframe(1000, -5.0, Interp.HOLD)])
    assert curve.value_at(999) == 5.0
    assert curve.value_at(1000) == -5.0


def test_linear_hits_both_endpoints_exactly() -> None:
    curve = Curve([Keyframe(100, 2.0), Keyframe(900, 6.0)])
    assert curve.value_at(100) == pytest.approx(2.0)
    assert curve.value_at(900) == pytest.approx(6.0)
    assert curve.value_at(500) == pytest.approx(4.0)


# --- ease -------------------------------------------------------------------


def test_ease_with_collinear_handles_reproduces_linear() -> None:
    """The cheapest proof the solver is not subtly wrong but still curve-shaped."""
    left, right = Keyframe(0, -3.0, Interp.EASE), Keyframe(4800, 7.0)
    left.handles, right.handles = _linear_handles(left, right)
    eased = Curve([left, right])
    straight = Curve([Keyframe(0, -3.0), Keyframe(4800, 7.0)])
    for i in range(0, 4801, 37):
        assert eased.value_at(i) == pytest.approx(straight.value_at(i), abs=1e-9)


def test_the_solver_lands_on_the_time_it_was_asked_for() -> None:
    """Residual in normalised time, across curves nobody hand-picked."""
    rng = random.Random(5)
    for _ in range(2_000):
        x1, x2 = rng.random(), rng.random()
        target = rng.random()
        u = _solve_u(x1, x2, target)
        assert abs(_bezier(0.0, x1, x2, 1.0, u) - target) < 1e-8
        assert 0.0 <= u <= 1.0


def test_a_handle_reaching_past_the_far_keyframe_cannot_fold_the_curve() -> None:
    """03: `dt` is clamped so the curve can never double back in time.

    Asserted as **monotonicity of the output**, not merely finiteness. With the
    handles' value displacement at zero the curve must rise steadily from one
    keyframe to the other whatever the times say, so a solve that lands on the
    wrong `u` shows up as the value going backwards. Finiteness alone let an
    unclamped implementation through.
    """
    left = Keyframe(0, 0.0, Interp.EASE, Handles(outgoing=(99_999.0, 0.0)))
    right = Keyframe(1000, 1.0, handles=Handles(incoming=(-99_999.0, 0.0)))
    seen = Curve([left, right]).sample(0, 1000, 201)

    assert all(math.isfinite(v) for v in seen)
    assert seen[0] == pytest.approx(0.0)
    assert seen[-1] == pytest.approx(1.0)
    for earlier, later in pairwise(seen):
        assert later >= earlier - 1e-9, "the curve doubled back in time"


def test_the_solver_survives_a_segment_that_is_flat_where_it_starts() -> None:
    """Newton alone escapes the bracket here; the bisection fallback is why
    the iteration count is bounded by construction rather than by hope.

    With both control x's at the start of the span, B_x(u) = u**3, whose slope
    near zero is nearly nothing. Newton's first step from a small target is
    five orders of magnitude outside [0, 1].
    """
    for target in (1e-9, 1e-6, 1e-3, 0.5, 1.0 - 1e-6):
        u = _solve_u(0.0, 0.0, target)
        assert 0.0 <= u <= 1.0, f"escaped the bracket at target {target}"
        assert abs(_bezier(0.0, 0.0, 0.0, 1.0, u) - target) < 1e-6

    # ...and the mirrored case, flat where it ends.
    for target in (1e-6, 0.5, 1.0 - 1e-9):
        u = _solve_u(1.0, 1.0, target)
        assert 0.0 <= u <= 1.0
        assert abs(_bezier(0.0, 1.0, 1.0, 1.0, u) - target) < 1e-6


def test_an_extreme_handle_still_evaluates_through_value_at() -> None:
    """The same pathology reached the way M4 will reach it."""
    left = Keyframe(0, 0.0, Interp.EASE, Handles(outgoing=(0.0, 0.0)))
    right = Keyframe(1000, 1.0, handles=Handles(incoming=(0.0, 0.0)))
    seen = Curve([left, right]).sample(0, 1000, 101)
    assert all(math.isfinite(v) for v in seen)
    for earlier, later in pairwise(seen):
        assert later >= earlier - 1e-9


def test_handles_beyond_the_span_clamp_to_the_same_curve() -> None:
    """The clamp is applied, asserted without reaching into the implementation.

    Two handles that differ only *past* the clamp boundary must produce an
    identical curve, because both are pinned to the far keyframe. Unclamped
    they differ by up to 0.18 in value, so this fails loudly if the clamp is
    dropped — which monotonicity alone did not, since the solver's bisection
    copes with a non-monotonic B_x anyway.
    """

    def curve_for(out_dt: float, in_dt: float) -> list[float]:
        left = Keyframe(0, 0.0, Interp.EASE, Handles(outgoing=(out_dt, 0.0)))
        right = Keyframe(1000, 1.0, handles=Handles(incoming=(in_dt, 0.0)))
        return Curve([left, right]).sample(0, 1000, 51)

    pinned = curve_for(2_000.0, -2_000.0)
    further = curve_for(50_000.0, -50_000.0)
    assert pinned == pytest.approx(further, abs=1e-9)

    # ...and a handle inside the span is genuinely a different curve, so the
    # comparison above is not passing because everything is the same.
    inside = curve_for(300.0, -300.0)
    assert max(abs(a - b) for a, b in zip(pinned, inside, strict=True)) > 0.05


def test_the_clamp_does_not_touch_the_stored_handles() -> None:
    """What someone typed is theirs; a neighbour may move and make it legal."""
    handles = Handles(outgoing=(99_999.0, 2.0))
    curve = Curve([Keyframe(0, 0.0, Interp.EASE, handles), Keyframe(1000, 1.0)])
    curve.value_at(500)
    assert handles.outgoing == (99_999.0, 2.0)


def test_ease_is_allowed_to_overshoot_its_endpoints() -> None:
    """The 'ease out back' shape. 03 clamps dt and deliberately not dv."""
    left = Keyframe(0, 0.0, Interp.EASE, Handles(outgoing=(333.0, 0.0)))
    right = Keyframe(1000, 1.0, handles=Handles(incoming=(-333.0, 0.6)))
    peak = max(Curve([left, right]).sample(0, 1000, 201))
    assert peak > 1.0


# --- edges ------------------------------------------------------------------


def test_the_curve_holds_flat_outside_its_keyframes() -> None:
    curve = Curve([Keyframe(100, 3.0, Interp.EASE), Keyframe(200, 8.0, Interp.HOLD)])
    assert curve.value_at(-10_000) == 3.0
    assert curve.value_at(99) == 3.0
    assert curve.value_at(200) == 8.0
    assert curve.value_at(10_000) == 8.0


def test_a_single_keyframe_holds_for_all_time() -> None:
    curve = Curve([Keyframe(500, 1.25)])
    assert curve.value_at(-1) == 1.25
    assert curve.value_at(500) == 1.25
    assert curve.value_at(10**9) == 1.25


def test_an_empty_curve_raises_rather_than_inventing_a_zero() -> None:
    """A silent 0.0 would put a source at the origin and look like an M5 bug."""
    with pytest.raises(ValueError, match="empty curve"):
        Curve().value_at(0)


def test_duplicate_times_do_not_crash_the_evaluator() -> None:
    """The validator reports them; evaluation still has to cope."""
    curve = Curve([Keyframe(10, 1.0), Keyframe(10, 2.0)])
    assert math.isfinite(curve.value_at(10))


# --- purity and the property test -------------------------------------------


def test_evaluation_is_pure() -> None:
    curve = Curve(
        [
            Keyframe(0, 0.0, Interp.EASE, Handles((120.0, 4.0), (-30.0, 1.0))),
            Keyframe(480, 2.0),
        ]
    )
    before = deepcopy(curve)
    first = [curve.value_at(t) for t in range(0, 481, 11)]
    second = [curve.value_at(t) for t in range(0, 481, 11)]
    assert first == second
    assert curve == before


def test_every_value_stays_inside_the_convex_hull_of_its_control_points() -> None:
    """A Bezier lies within the hull of its four control points — including the
    two handle-displaced ones, which is why overshoot is legal and a solver
    that reads the wrong keyframe still gets caught.

    This replaces an earlier line that asked for the value to stay between the
    two keyframes; see the amendment note in the phase doc.
    """
    rng = random.Random(6)
    for _ in range(5_000):
        left = Keyframe(
            0,
            rng.uniform(-9, 9),
            Interp.EASE,
            Handles(outgoing=(rng.uniform(-4000, 4000), rng.uniform(-9, 9))),
        )
        right = Keyframe(
            1000,
            rng.uniform(-9, 9),
            handles=Handles(incoming=(rng.uniform(-4000, 4000), rng.uniform(-9, 9))),
        )
        controls = [
            left.value,
            left.value + left.handles.outgoing[1],  # type: ignore[union-attr]
            right.value + right.handles.incoming[1],  # type: ignore[union-attr]
            right.value,
        ]
        low, high = min(controls), max(controls)
        for value in Curve([left, right]).sample(0, 1000, 41):
            assert math.isfinite(value)
            assert low - 1e-9 <= value <= high + 1e-9


def test_sample_includes_both_ends() -> None:
    curve = Curve([Keyframe(0, 0.0), Keyframe(100, 10.0)])
    assert curve.sample(0, 100, 11) == pytest.approx(
        [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    )
    assert curve.sample(50, 50, 1) == [5.0]
    with pytest.raises(ValueError, match="at least 1"):
        curve.sample(0, 100, 0)
