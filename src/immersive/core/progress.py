"""How far a piece of work on a worker has got, and whether to stop it.

One `Progress` per piece of work - per file, for the importer (F-59). The
worker writes `done`; the UI thread reads it, and sets `cancelled`, which the
worker reads between chunks. Each is one attribute assigned whole, which the
GIL makes safe to share without a lock, and nothing is signalled per chunk:
the UI thread looks when it wants to (02, the threading table).

Qt-free, like everything in `core/` (N-5).
"""

from __future__ import annotations

from dataclasses import dataclass


class Progress:
    """A fraction that only rises, from 0 to 1, and a request to stop."""

    def __init__(self) -> None:
        self.done = 0.0
        self.cancelled = False

    def reach(self, fraction: float) -> None:
        """Move to `fraction` - never back, and never past 1."""
        if fraction > self.done:
            self.done = min(fraction, 1.0)

    def part(self, start: float, end: float) -> Part:
        """The stretch of this progress from `start` to `end`, for one stage."""
        return Part(self, start, end)


@dataclass(frozen=True)
class Part:
    """One stage's stretch of a `Progress`: `at(0.5)` is halfway through it."""

    progress: Progress
    start: float
    end: float

    def at(self, fraction: float) -> None:
        self.progress.reach(self.start + (self.end - self.start) * fraction)

    def part(self, start: float, end: float) -> Part:
        """A stretch of this stretch, `start` and `end` counted within it."""
        span = self.end - self.start
        return Part(self.progress, self.start + span * start, self.start + span * end)

    @property
    def cancelled(self) -> bool:
        return self.progress.cancelled


@dataclass(frozen=True)
class Cancelled:
    """Work stopped because it was asked to: not a failure, and not reported.

    Beside `Refused`, as a value rather than an exception, for the same
    reason: a batch of forty turns every outcome into one result.
    """

    path: str
