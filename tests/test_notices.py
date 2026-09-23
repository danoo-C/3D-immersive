"""The notice model: what was reported, in what order, and how loud.

No Qt anywhere in this file, because there is none in the module it tests —
D-81, and `test_layering.py` asserts it rather than trusting this docstring.
"""

from __future__ import annotations

import pytest

from immersive.ui import theme_io
from immersive.ui.notices import Notice, NoticeLog, Severity, worst


def test_severity_has_an_order() -> None:
    """`StrEnum` has none of its own, and the count is coloured by it."""
    assert Severity.ERROR.rank > Severity.WARN.rank > Severity.INFO.rank


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ((), None),
        ((Severity.INFO,), Severity.INFO),
        ((Severity.WARN, Severity.INFO), Severity.WARN),
        ((Severity.ERROR, Severity.WARN), Severity.ERROR),
        ((Severity.WARN, Severity.ERROR, Severity.INFO), Severity.ERROR),
    ],
)
def test_worst_picks_the_loudest(
    given: tuple[Severity, ...], expected: Severity | None
) -> None:
    assert worst(given) == expected


def test_the_log_keeps_everything_in_order() -> None:
    """Notices persist for the session; they are not a current message.

    04-ui-spec.md: a message you can only read in the second it appears has
    not been reported to anybody.
    """
    log = NoticeLog()
    log.add(Severity.INFO, "first")
    log.add(Severity.WARN, "second")
    log.add(Severity.ERROR, "third")

    assert len(log) == 3
    assert [notice.message for notice in log.newest_first()] == [
        "third",
        "second",
        "first",
    ]


def test_the_latest_is_what_the_status_line_carries() -> None:
    log = NoticeLog()
    assert log.latest() is None

    log.add(Severity.INFO, "first")
    newest = log.add(Severity.WARN, "second")

    assert log.latest() == newest


def test_sequence_orders_notices_raised_in_the_same_instant() -> None:
    """Two in the same millisecond still have an order, and it is this one."""
    log = NoticeLog()
    notices = [log.add(Severity.INFO, str(n)) for n in range(5)]

    assert [notice.sequence for notice in notices] == [1, 2, 3, 4, 5]


def test_unread_counts_until_the_list_is_opened() -> None:
    log = NoticeLog()
    log.add(Severity.WARN, "one")
    log.add(Severity.WARN, "two")
    assert log.unread == 2

    log.mark_read()
    assert log.unread == 0

    log.add(Severity.INFO, "three")
    assert log.unread == 1


def test_the_count_is_coloured_by_the_worst_unread_not_the_newest() -> None:
    """An error must not go quiet behind a warning that arrived after it."""
    log = NoticeLog()
    assert log.unread_severity() is None

    log.add(Severity.ERROR, "the bad one")
    log.add(Severity.WARN, "a later, milder one")

    assert log.unread_severity() is Severity.ERROR

    log.mark_read()
    log.add(Severity.WARN, "after reading")
    assert log.unread_severity() is Severity.WARN, "read ones stop counting"


def test_clearing_is_explicit() -> None:
    log = NoticeLog()
    log.add(Severity.ERROR, "one")

    log.clear()

    assert len(log) == 0
    assert log.unread == 0
    assert log.latest() is None


def test_observers_are_told_when_anything_changes() -> None:
    """A plain callback, not a Qt signal: the log has to work headless."""
    log = NoticeLog()
    seen: list[int] = []
    log.observe(lambda: seen.append(len(log)))

    log.add(Severity.INFO, "one")
    log.add(Severity.INFO, "two")
    log.clear()

    assert seen == [1, 2, 0]


def test_detail_is_kept_apart_from_the_headline() -> None:
    """The status bar shows one line; the list behind it can afford more."""
    log = NoticeLog()
    notice = log.add(Severity.WARN, "ocean.3dimtheme has problems", ["a", "b"])

    assert notice.message == "ocean.3dimtheme has problems"
    assert notice.detail == ("a", "b")


def test_a_theme_report_becomes_notices_with_its_severities_intact() -> None:
    """The join D-78 was written for, exercised end to end.

    The conversion is two lines at the call site rather than a method here,
    because a `NoticeLog` that knew about `ThemeReport` would import
    `theme_io`, which imports this module.
    """
    report = theme_io.loads('{"schema_version": 1, "tokens": {"nope": "#FF0000"}}')
    log = NoticeLog()
    for problem in report.problems:
        log.add(problem.severity, str(problem))

    assert len(log) == len(report.problems) == 1
    assert log.unread_severity() is Severity.WARN

    broken = theme_io.loads("{")
    for problem in broken.problems:
        log.add(problem.severity, str(problem))

    assert log.unread_severity() is Severity.ERROR


def test_a_notice_is_frozen() -> None:
    """Reported is reported; the list behind the count is not editable."""
    notice = NoticeLog().add(Severity.INFO, "done")

    with pytest.raises(AttributeError):
        notice.message = "something else"  # type: ignore[misc]

    assert isinstance(notice, Notice)
