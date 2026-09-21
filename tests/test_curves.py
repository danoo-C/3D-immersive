"""Curve and Keyframe as containers. Evaluation is phase 2."""

from __future__ import annotations

from immersive.core.curves import Curve, Handles, Interp, Keyframe


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
