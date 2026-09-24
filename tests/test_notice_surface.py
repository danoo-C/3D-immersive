"""The notice surface draws what the log holds. Marked gui: needs a QApplication."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.ui import theme_io
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import NoticeLog, Severity
from immersive.ui.widgets.notices import NoticeCount

pytestmark = pytest.mark.gui


@pytest.fixture
def log() -> NoticeLog:
    return NoticeLog()


@pytest.fixture
def count(log: NoticeLog) -> Iterator[NoticeCount]:
    build_application([])
    widget = NoticeCount(log)
    log.observe(widget.refresh)
    yield widget
    widget.deleteLater()


def test_the_count_is_invisible_at_zero(count: NoticeCount) -> None:
    """04: the same rule the xrun counter already follows.

    A zero that is always on screen is a thing people stop seeing, which
    costs exactly the attention this widget exists to hold.
    """
    assert count.isHidden()
    assert count.text() == ""


def test_a_notice_makes_the_count_appear(count: NoticeCount, log: NoticeLog) -> None:
    log.add(Severity.WARN, "something")

    assert not count.isHidden()
    assert "1" in count.text()


def test_the_count_counts(count: NoticeCount, log: NoticeLog) -> None:
    for n in range(3):
        log.add(Severity.WARN, str(n))

    assert "3" in count.text()


def test_the_count_is_coloured_by_the_worst_unread(
    count: NoticeCount, log: NoticeLog
) -> None:
    """An error behind a later warning still shows as an error."""
    from immersive.ui import theme

    log.add(Severity.WARN, "mild")
    assert theme.color("warn") in count.styleSheet()

    log.add(Severity.ERROR, "bad")
    assert theme.color("error") in count.styleSheet()

    log.add(Severity.WARN, "mild again, afterwards")
    assert theme.color("error") in count.styleSheet(), "the error is still unread"


def test_severity_is_not_carried_by_colour_alone(
    count: NoticeCount, log: NoticeLog
) -> None:
    """04, *Accessibility and feel*. The glyphs differ, not only the hue."""
    log.add(Severity.WARN, "one")
    warned = count.text()

    log.clear()
    log.add(Severity.ERROR, "one")

    assert count.text() != warned


def test_opening_the_list_marks_everything_read(
    count: NoticeCount, log: NoticeLog
) -> None:
    log.add(Severity.WARN, "one")
    log.add(Severity.ERROR, "two")
    assert log.unread == 2

    count.open_list()

    assert log.unread == 0
    assert count.isHidden(), "and the count goes away"


def test_the_list_holds_one_row_per_notice(count: NoticeCount, log: NoticeLog) -> None:
    log.add(Severity.WARN, "first")
    log.add(Severity.ERROR, "second")

    count.open_list()
    rows = count._list.rows()

    assert len(rows) == 2
    assert "second" in rows[0].text(), "newest first"
    assert "first" in rows[1].text()


def test_an_empty_list_says_so_rather_than_showing_nothing(
    count: NoticeCount,
) -> None:
    count.open_list()
    rows = count._list.rows()

    assert len(rows) == 1
    assert "Nothing reported" in rows[0].text()


def test_a_notices_detail_reaches_the_list(count: NoticeCount, log: NoticeLog) -> None:
    """The status line shows one line; the list can afford the rest."""
    log.add(Severity.WARN, "ocean.3dimtheme has problems", ["tokens.nope", "bad hex"])

    count.open_list()

    assert "tokens.nope" in count._list.rows()[0].text()


def test_nothing_here_is_modal(count: NoticeCount, log: NoticeLog) -> None:
    """F-47's whole point: a cosmetic problem must not block anybody."""
    from PySide6.QtCore import Qt

    log.add(Severity.ERROR, "bad")
    count.open_list()

    assert not count._list.isModal()
    assert count._list.windowFlags() & Qt.WindowType.Popup


# --------------------------------------------------------------------------- #
# what the screenshot found
# --------------------------------------------------------------------------- #


def settle() -> None:
    """Let deferred layout land. One turn is not always enough for a status bar."""
    for _ in range(10):
        QApplication.processEvents()


def test_no_row_in_the_list_is_cut_off(count: NoticeCount, log: NoticeLog) -> None:
    """The problem lines are the ones that must not be cut off.

    A wrapped row's height depends on the width it gets, and both the popup's
    `adjustSize()` and a `Fixed` vertical policy sized rows from their hint -
    for a width of the label's own choosing. The last detail lines went
    behind the edge. The notices are the milestone journey's own - a theme
    chosen, then a broken one - because whether it happens depends on the
    wording and on how many rows share the width.
    """
    report = theme_io.loads(
        json.dumps(
            {
                "schema_version": theme_io.SCHEMA_VERSION,
                "tokens": {"accent": "not a colour", "invented": "#FF0000"},
                "groups": {"spaceship": {"hull": "#FF0000"}},
            }
        )
    )
    log.add(Severity.INFO, "Theme: Red accent")
    log.add(Severity.WARN, "Theme: Broken", [str(p) for p in report.problems])

    count.open_list()
    settle()
    shown = count._list

    for row in shown.rows():
        assert row.height() >= row.heightForWidth(row.width()), row.text()
    chrome = 4  # the popup's border and its layout's margin, both sides
    assert shown.height() - chrome >= shown._body.heightForWidth(shown.width() - chrome)


def test_the_first_notice_does_not_move_the_window() -> None:
    """`QStatusBar` sizes itself from hidden permanent widgets too.

    So a count that took its compact style only when it first appeared held
    the bar taller - in the toolbar buttons' metrics - until something was
    reported, and every panel in the window jumped when it was.
    """
    build_application([])
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    settle()
    before = window.statusBar().height()

    window.notices().add(Severity.WARN, "something")
    settle()

    assert window.statusBar().height() == before
    window.deleteLater()
