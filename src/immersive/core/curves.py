"""Keyframes and curves, as containers.

Shapes only. `Curve.value_at` and the bezier solve are phase 2 — the model
needs the type to exist, not to work.

The field names come from the Entities block of docs/03-data-model.md, with
one deliberate divergence noted on `Handles`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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
