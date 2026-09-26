"""Anything slow, begun, updated and finished: what the info box shows (D-116).

A piece of work that takes long enough to wonder about *begins an activity*
with a label and a maximum, *updates* its value - and its label, and its
maximum - as it goes, and *finishes* it. It may offer a cancel, which the
box shows as a ✕; the work finishes its own activity once it has stopped.

    work = activities.begin("Importing 0 of 22 files", maximum=total, cancel=stop)
    work.update(done, label=f"Importing {count} of 22 files")
    work.finish()

A maximum of 0 means busy, with no measure - `QProgressBar`'s own
convention. An activity is shown once it has run for `SHOW_AFTER`, so work
that is over in a moment never flashes a bar.

**The UI thread only.** Begun, updated and finished there, as every widget
is touched (02, the threading table). Work on a worker reports through a
value the UI thread reads - `core.progress.Progress`, for the importer - and
the UI thread updates the activity from it.

Qt-free, like the notice log (D-81): the box in `ui/widgets/info_box.py`
draws it, and this is tested without a widget.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

#: How long an activity runs before it is shown, in seconds.
SHOW_AFTER: Final = 0.25


class Activity:
    """One piece of work, as the box shows it."""

    def __init__(
        self,
        board: Activities,
        label: str,
        maximum: int,
        cancel: Callable[[], None] | None,
        began: float,
    ) -> None:
        self._board = board
        self.label = label
        self.maximum = max(maximum, 0)
        self.value = 0
        #: What the ✕ calls, if the work can be stopped.
        self.cancel = cancel
        self.began = began

    @property
    def running(self) -> bool:
        return self in self._board.running()

    @property
    def fraction(self) -> float | None:
        """How far through it is, 0 to 1 - or `None` while busy with no measure."""
        if self.maximum == 0:
            return None
        return self.value / self.maximum

    def update(
        self,
        value: int | None = None,
        *,
        maximum: int | None = None,
        label: str | None = None,
    ) -> None:
        """Change whichever is given. The value is held between 0 and the
        maximum. An activity already finished is left as it is."""
        if not self.running:
            return
        if maximum is not None:
            self.maximum = max(maximum, 0)
        if value is not None:
            self.value = value
        self.value = min(max(self.value, 0), self.maximum)
        if label is not None:
            self.label = label
        self._board.changed()

    def finish(self) -> None:
        """Done, or stopped: the box lets go of it. A second call does nothing."""
        self._board.finished(self)


class Activities:
    """Every activity running, in the order they began."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._running: list[Activity] = []
        self._observers: list[Callable[[], None]] = []

    def begin(
        self,
        label: str,
        maximum: int = 0,
        *,
        cancel: Callable[[], None] | None = None,
    ) -> Activity:
        activity = Activity(self, label, maximum, cancel, self._clock())
        self._running.append(activity)
        self.changed()
        return activity

    def running(self) -> list[Activity]:
        return list(self._running)

    def shown(self) -> list[Activity]:
        """Those that have run for `SHOW_AFTER`, first begun first."""
        now = self._clock()
        return [each for each in self._running if now - each.began >= SHOW_AFTER]

    def next_shown_in(self) -> float | None:
        """Seconds until the next activity not yet shown will be, or `None`
        if none is waiting - when the box has to look again unprompted."""
        now = self._clock()
        waiting = [
            each.began + SHOW_AFTER - now
            for each in self._running
            if now - each.began < SHOW_AFTER
        ]
        return max(min(waiting), 0.0) if waiting else None

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` after every begin, update and finish."""
        self._observers.append(callback)

    def changed(self) -> None:
        for callback in list(self._observers):
            callback()

    def finished(self, activity: Activity) -> None:
        if activity in self._running:
            self._running.remove(activity)
            self.changed()
