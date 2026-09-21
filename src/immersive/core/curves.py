"""Keyframes, curves, and evaluating one at a time.

`hold` and `linear` are arithmetic. `ease` is a cubic Bezier through the two
keyframes and their facing handles, which needs a root find: a query arrives as
a *time* and a Bezier is parameterised by `u`, so `B_x(u) = t` is solved before
`B_y(u)` can be read off.

The field names come from the Entities block of docs/03-data-model.md, with
one deliberate divergence noted on `Handles`.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from enum import StrEnum

#: Newton stops here. The solve runs in *normalised* curve time - the segment
#: mapped onto [0, 1] - so this is scale-free: a segment three samples long and
#: one three million samples long get the same relative precision, and a
#: tolerance in raw samples would have been meaninglessly tight at one end and
#: useless at the other.
_SOLVE_TOLERANCE = 1e-9

#: Newton alone can stall on a near-flat segment, so the solve keeps a bracket
#: and bisects whenever Newton's step escapes it. That makes the iteration
#: count bounded by construction rather than by hope; measured worst case over
#: 20 000 random curves is 8, and this is the guard against the case nobody
#: generated.
_SOLVE_LIMIT = 32


def _bezier(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    v = 1.0 - u
    return v * v * v * p0 + 3.0 * v * v * u * p1 + 3.0 * v * u * u * p2 + u * u * u * p3


def _bezier_slope(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    v = 1.0 - u
    return 3.0 * (v * v * (p1 - p0) + 2.0 * v * u * (p2 - p1) + u * u * (p3 - p2))


def _solve_u(x1: float, x2: float, target: float) -> float:
    """Find `u` where a unit-span Bezier's x equals `target`.

    Newton-Raphson with a bisection fallback, the shape browsers use for CSS
    `cubic-bezier`. Because the control x's are clamped into the span, B_x is
    monotonic and the root is unique - which is what makes asking "which u is
    this time" a well-posed question at all.
    """
    low, high, u = 0.0, 1.0, target
    for _ in range(_SOLVE_LIMIT):
        error = _bezier(0.0, x1, x2, 1.0, u) - target
        if abs(error) < _SOLVE_TOLERANCE:
            return u
        if error > 0.0:
            high = u
        else:
            low = u
        slope = _bezier_slope(0.0, x1, x2, 1.0, u)
        if slope > _SOLVE_TOLERANCE:
            step = u - error / slope
            u = step if low < step < high else 0.5 * (low + high)
        else:
            u = 0.5 * (low + high)
    return u


class Interp(StrEnum):
    """How the segment *after* a keyframe behaves (03-data-model.md)."""

    LINEAR = "linear"
    EASE = "ease"
    HOLD = "hold"


@dataclass
class Handles:
    """Bezier control points, present only when `interp` is `ease`.

    `03` calls these "out" and "in": `out` leaves its own keyframe going
    forward, `in` arrives at its keyframe from behind, so a segment is shaped
    by the left keyframe's `outgoing` and the right one's `incoming`. They are
    spelled out here because `in` is a Python keyword and `in_` reads badly at
    every call site; project_io maps the two names back for the file.

    Each is `(dt, dv)` in samples and value units, relative to its own
    keyframe. `dt` is positive for `outgoing` and negative for `incoming`.
    """

    outgoing: tuple[float, float] = (0.0, 0.0)
    incoming: tuple[float, float] = (0.0, 0.0)


@dataclass
class Keyframe:
    """One point on a curve, at an absolute timeline time in samples (D-7)."""

    t: int
    value: float
    interp: Interp = Interp.LINEAR
    handles: Handles | None = None


@dataclass
class Curve:
    """Keyframes sorted by `t`, with `t` unique.

    Unique `t` is a real constraint rather than tidiness: a keyframe has no id
    and is identified by its time, so two at the same time are the same
    keyframe twice. M6 inherits the consequence — dragging one onto another is
    a collision, not a reordering.
    """

    keyframes: list[Keyframe] = field(default_factory=list)

    def value_at(self, t: float) -> float:
        """The curve's value at timeline time `t`, in samples.

        The **left** keyframe's `interp` governs the segment after it, which is
        what 03-data-model.md means by that phrase and why a query landing
        exactly on a keyframe treats it as the left of its pair.

        Before the first keyframe and after the last the curve holds flat,
        whatever interpolation is set — there is no segment out there to
        interpolate along.

        Pure: same arguments, same answer, nothing mutated. M4 calls this from
        the audio thread.
        """
        if not self.keyframes:
            raise ValueError(
                "an empty curve has no value — a channel with no keyframes for "
                "a parameter falls back to its static position, which is the "
                "caller's decision and not a zero this can invent"
            )

        index = bisect.bisect_right(self.keyframes, t, key=lambda k: k.t)
        if index == 0:
            return self.keyframes[0].value
        if index == len(self.keyframes):
            return self.keyframes[-1].value

        left, right = self.keyframes[index - 1], self.keyframes[index]
        if left.interp is Interp.HOLD:
            return left.value

        span = float(right.t - left.t)
        if span <= 0.0:  # duplicate times; the validator reports it, this copes
            return left.value

        if left.interp is Interp.LINEAR:
            return left.value + (right.value - left.value) * ((t - left.t) / span)
        return _ease(left, right, t, span)

    def sample(self, start: float, stop: float, count: int) -> list[float]:
        """`count` values evenly spaced over `[start, stop]`, both included.

        For drawing a curve (M6) and for anything that wants a trajectory
        rather than a point. `count` of 1 returns the value at `start`.
        """
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        if count == 1:
            return [self.value_at(start)]
        step = (stop - start) / (count - 1)
        return [self.value_at(start + step * i) for i in range(count)]

    def problems(self) -> list[str]:
        """Why this curve is not well-formed. Empty when it is."""
        times = [k.t for k in self.keyframes]
        found = []
        if times != sorted(times):
            found.append("keyframes are not sorted by t")
        if len(set(times)) != len(times):
            duplicates = sorted({t for t in times if times.count(t) > 1})
            found.append(f"duplicate keyframe times: {duplicates}")
        for keyframe in self.keyframes:
            if keyframe.interp is Interp.EASE and keyframe.handles is None:
                found.append(f"keyframe at t={keyframe.t} is ease with no handles")
        return found


def _ease(left: Keyframe, right: Keyframe, t: float, span: float) -> float:
    """A cubic Bezier through two keyframes and their facing handles.

    The control x's are **clamped into the span**, which is what
    03-data-model.md requires so "the curve can never double back in time".
    That clamp is sufficient: B_x' is a quadratic Bezier with control values
    `(x1-x0, x2-x1, x3-x2)`, and with both interior points inside the span its
    minimum on [0, 1] stays non-negative — checked over 200 000 random curves,
    where it never went below zero. Monotonic in time is what makes "which u
    is this time" have exactly one answer.

    Clamped **here, on local copies**, never on the stored keyframe. What
    someone typed is theirs: rewriting it would destroy the original the first
    time a neighbouring keyframe moved and the handle became legal again.

    A missing `handles` is treated as zero displacement, which makes P1 = P0
    and P2 = P3 — the classic smooth ease-in-out, and a sensible reading of
    "ease" for a keyframe the validator has already flagged.
    """
    outgoing = left.handles.outgoing if left.handles else (0.0, 0.0)
    incoming = right.handles.incoming if right.handles else (0.0, 0.0)

    # Normalised to the unit span, so the solver's tolerance is scale-free.
    x1 = min(max(outgoing[0] / span, 0.0), 1.0)
    x2 = min(max(1.0 + incoming[0] / span, 0.0), 1.0)

    u = _solve_u(x1, x2, (t - left.t) / span)
    return _bezier(
        left.value,
        left.value + outgoing[1],
        right.value + incoming[1],
        right.value,
        u,
    )
