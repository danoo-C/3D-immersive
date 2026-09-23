"""Notices - everything the application needs to report, and the log it goes in.

F-56: a missing sample, a malformed theme, a decode that failed, a device that
would not open. All of them mean the same thing - visible in the UI, not a
line on stderr nobody reads - and until M9 none of them had anywhere to
appear. The *Notices* section of docs/04-ui-spec.md is the specification and
this is its model (D-65).

**No Qt here, deliberately** (D-81). `theme_io` puts a `Severity` on every
problem it reports, so this module is upstream of the whole `.3dimtheme`
format - and `theme.py` keeps itself importable without a `QApplication` so
the palette and the stylesheet stay testable headless. A Qt import in this
file would reach both of them. The widget that draws all this lives in
`ui/widgets/notices.py` and may import whatever it likes.

One surface, not a dialog per caller. A modal for a cosmetic theme typo is
the behaviour F-47 exists to prevent; a `print()` is the same behaviour
through the other door.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from itertools import count


class Severity(StrEnum):
    """How loudly a notice should be shown.

    The three docs/04-ui-spec.md defines, and the ordering below is what the
    unread count is coloured by - an error must not go quiet behind a warning
    that happened to arrive after it.
    """

    #: Something the user asked for did not happen.
    ERROR = "error"
    #: It happened, with a caveat they need to know.
    WARN = "warn"
    #: It happened.
    INFO = "info"

    @property
    def rank(self) -> int:
        """Higher is louder. `StrEnum` has no ordering of its own."""
        return _RANK[self]


_RANK = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}


def worst(severities: Iterable[Severity]) -> Severity | None:
    """The loudest of `severities`, or `None` when there are none."""
    return max(severities, key=lambda severity: severity.rank, default=None)


@dataclass(frozen=True)
class Notice:
    """One thing the application reported, and when.

    `detail` is the lines behind the headline - a theme file's problems, a
    device's reason - kept apart from `message` because the status bar shows
    one line and the list behind it can afford more.

    `sequence` rather than `at` is what orders these. Two notices raised in
    the same millisecond are ordered by the counter that issued them, and a
    test that asserts ordering should not have to slow down to do it.
    """

    severity: Severity
    message: str
    sequence: int
    at: datetime
    detail: tuple[str, ...] = ()


@dataclass
class NoticeLog:
    """Everything reported this session, newest last, with an unread count.

    Notices persist for the session and are cleared explicitly, which is
    04-ui-spec.md's rule and the reason this holds a list rather than one
    current message: *a message you can only read in the second it appears
    has not been reported to anybody.*

    Not a Qt model. The widget observes this through a callback so that the
    log itself stays testable without a `QApplication`, and so that M2 can
    push missing media into it from code that has no widget in hand.
    """

    _notices: list[Notice] = field(default_factory=list)
    _read: int = 0
    _sequence: Iterator[int] = field(default_factory=lambda: count(1))
    _observers: list[object] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        message: str,
        detail: Sequence[str] = (),
    ) -> Notice:
        """Record a notice and tell anything watching."""
        notice = Notice(
            severity=severity,
            message=message,
            sequence=next(self._sequence),
            at=datetime.now(),
            detail=tuple(detail),
        )
        self._notices.append(notice)
        for observe in list(self._observers):
            observe()  # type: ignore[operator]
        return notice

    def observe(self, callback: object) -> None:
        """Call `callback` whenever anything changes. No Qt, no signals."""
        self._observers.append(callback)

    # ------------------------------------------------------------- reading

    def newest_first(self) -> list[Notice]:
        """Every notice this session, newest first, as the list shows them."""
        return sorted(self._notices, key=lambda n: n.sequence, reverse=True)

    def latest(self) -> Notice | None:
        """The one the status bar line carries, or `None` when there are none."""
        return self._notices[-1] if self._notices else None

    @property
    def unread(self) -> int:
        """How many have arrived since the list was last opened."""
        return len(self._notices) - self._read

    def unread_severity(self) -> Severity | None:
        """What to colour the count: the **worst** unread, not the newest.

        An `error` followed by a `warn` is still an error waiting to be read,
        and a count that took its colour from whichever arrived last would
        quietly downgrade it.
        """
        return worst(notice.severity for notice in self._notices[self._read :])

    # ------------------------------------------------------------- writing

    def mark_read(self) -> None:
        """Everything so far has been seen. What the list does on opening."""
        self._read = len(self._notices)

    def clear(self) -> None:
        """Forget everything. Explicit, because notices persist otherwise."""
        self._notices.clear()
        self._read = 0
        for observe in list(self._observers):
            observe()  # type: ignore[operator]

    def __len__(self) -> int:
        return len(self._notices)
