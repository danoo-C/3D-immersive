"""The numeric field: dragged or typed, and one commit per gesture. Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.ui.units import Duration
from immersive.ui.widgets.numeric import MIXED, THRESHOLD, NumericField

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def a_field(value: float = 0.0) -> tuple[NumericField, list[float]]:
    """A gain-like field, and the list of what it committed."""
    field = NumericField(
        value, minimum=-60.0, maximum=12.0, step=0.1, unit="dB", signed=True
    )
    field.resize(90, 22)
    field.show()
    field.activateWindow()
    commits: list[float] = []
    field.committed.connect(commits.append)
    return field, commits


def mouse(
    field: NumericField,
    kind: QEvent.Type,
    x: float,
    y: float = 10,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    left = Qt.MouseButton.LeftButton
    event = QMouseEvent(
        kind,
        QPointF(x, y),
        field.mapToGlobal(QPointF(x, y)),
        Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
        Qt.MouseButton.NoButton if kind is QEvent.Type.MouseButtonRelease else left,
        modifiers,
    )
    QApplication.sendEvent(field, event)


def drag(
    field: NumericField,
    xs: list[float],
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    mouse(field, QEvent.Type.MouseButtonPress, xs[0])
    for x in xs[1:]:
        mouse(field, QEvent.Type.MouseMove, x, modifiers=modifiers)
    mouse(field, QEvent.Type.MouseButtonRelease, xs[-1])


def typed(field: NumericField, text: str, *, key: Qt.Key = Qt.Key.Key_Return) -> None:
    drag(field, [40, 40])  # a click that never moved opens it for typing
    QTest.keyClicks(field, text)
    QTest.keyClick(field, key)


# --------------------------------------------------------------------------- #
# typing
# --------------------------------------------------------------------------- #


def test_it_shows_its_value_with_its_unit() -> None:
    field, _ = a_field(-6.0)
    assert field.text() == "-6.0 dB"
    assert field.isReadOnly()


def test_a_click_that_never_moved_opens_it_for_typing() -> None:
    field, commits = a_field(-6.0)

    drag(field, [40, 41])  # under the threshold

    assert not field.isReadOnly()
    assert field.selectedText() == "-6.0 dB", "all of it, ready to be replaced"
    assert commits == []


def test_a_typed_value_with_its_unit_commits_once() -> None:
    field, commits = a_field()

    typed(field, "-6 dB")

    assert commits == [-6.0]
    assert field.text() == "-6.0 dB"
    assert field.isReadOnly()


def test_escape_puts_back_what_was_there_and_commits_nothing() -> None:
    field, commits = a_field(-3.0)

    typed(field, "-20", key=Qt.Key.Key_Escape)

    assert commits == []
    assert field.value() == -3.0
    assert field.text() == "-3.0 dB"


def test_text_that_is_not_a_number_puts_back_the_old_value() -> None:
    field, commits = a_field(-3.0)

    typed(field, "loud")

    assert commits == []
    assert field.text() == "-3.0 dB"


def test_a_value_out_of_range_is_clamped_and_shown_clamped() -> None:
    field, commits = a_field()

    typed(field, "+40")

    assert commits == [12.0]
    assert field.text() == "+12.0 dB"


def test_retyping_the_same_value_commits_nothing() -> None:
    field, commits = a_field(-6.0)
    typed(field, "-6")
    assert commits == []


def test_leaving_the_field_keeps_what_was_typed() -> None:
    field, commits = a_field()
    drag(field, [40, 40])
    QTest.keyClicks(field, "-9")

    # Offscreen, the test's window is never the active one, so the field
    # never had the focus to lose; send what losing it sends.
    QApplication.sendEvent(
        field, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason)
    )

    assert commits == [-9.0]
    assert field.isReadOnly()


# --------------------------------------------------------------------------- #
# dragging
# --------------------------------------------------------------------------- #


def test_a_drag_of_many_steps_commits_once_on_release() -> None:
    field, commits = a_field()

    drag(field, [10 + x for x in range(0, 41)])  # forty pixels right

    assert commits == [4.0]
    assert field.isReadOnly(), "a drag never opens the field for typing"


def test_up_is_more_and_down_is_less() -> None:
    up, up_commits = a_field()
    mouse(up, QEvent.Type.MouseButtonPress, 40, 10)
    mouse(up, QEvent.Type.MouseMove, 40, -10)
    mouse(up, QEvent.Type.MouseButtonRelease, 40, -10)

    assert up_commits == [2.0]


def test_shift_drags_at_a_tenth_of_the_rate() -> None:
    field, commits = a_field()

    drag(field, [10, 110], modifiers=Qt.KeyboardModifier.ShiftModifier)

    assert commits == [1.0]


def test_a_drag_stops_at_the_ends_of_the_range() -> None:
    field, commits = a_field(10.0)

    drag(field, [10, 400])

    assert commits == [12.0]


def test_the_field_shows_the_value_while_it_is_dragged() -> None:
    field, commits = a_field()
    mouse(field, QEvent.Type.MouseButtonPress, 10)
    mouse(field, QEvent.Type.MouseMove, 10 + THRESHOLD + 17)

    assert field.text() == "+2.0 dB"
    assert commits == [], "nothing is committed until the release"


def test_setting_the_value_from_outside_commits_nothing() -> None:
    field, commits = a_field()
    field.set_value(-12.0)
    assert field.text() == "-12.0 dB"
    assert commits == []


# --------------------------------------------------------------------------- #
# shortcuts
# --------------------------------------------------------------------------- #

CTRL = Qt.KeyboardModifier.ControlModifier
KEYS = [Qt.Key.Key_C, Qt.Key.Key_X, Qt.Key.Key_V, Qt.Key.Key_A, Qt.Key.Key_Z]


def claims(field: NumericField, key: Qt.Key) -> bool:
    """Whether `field` keeps Ctrl+`key` from the window's shortcuts."""
    override = QKeyEvent(QEvent.Type.ShortcutOverride, key, CTRL, "")
    override.ignore()
    QApplication.sendEvent(field, override)
    return override.isAccepted()


@pytest.mark.parametrize("key", KEYS)
def test_at_rest_it_claims_no_shortcut(key: Qt.Key) -> None:
    """Not even after Enter, which leaves it at rest and still focused - so
    Ctrl+C there copies the selected clips, not "-6.0 dB"."""
    field, _ = a_field()
    typed(field, "-6")
    assert field.isReadOnly()

    assert not claims(field, key)


@pytest.mark.parametrize("key", KEYS)
def test_while_typing_it_claims_what_any_text_field_does(key: Qt.Key) -> None:
    field, _ = a_field()
    drag(field, [40, 40])
    assert not field.isReadOnly()

    assert claims(field, key)


# --------------------------------------------------------------------------- #
# reading `—`, and other formats
# --------------------------------------------------------------------------- #


def test_a_mixed_field_reads_a_dash_until_a_value_is_set() -> None:
    field, _ = a_field(-6.0)
    field.set_mixed()
    assert field.text() == MIXED and field.mixed()
    field.set_value(-3.0)
    assert field.text() == "-3.0 dB" and not field.mixed()


def test_a_press_on_a_mixed_field_opens_it_for_typing_not_dragging() -> None:
    field, commits = a_field(-6.0)
    field.set_mixed()

    drag(field, [40, 90, 140])

    assert not field.isReadOnly(), "open for typing"
    assert field.selectedText() == MIXED
    assert commits == [], "a drag from a dash has no value to start from"


def test_a_value_typed_over_a_dash_is_committed_even_if_it_matches() -> None:
    """It matched one of the things, and is new to the others."""
    field, commits = a_field(-6.0)
    field.set_mixed()
    typed(field, "-6")
    assert commits == [-6.0]
    assert field.text() == "-6.0 dB" and not field.mixed()


@pytest.mark.parametrize("key", [Qt.Key.Key_Escape, Qt.Key.Key_Return])
def test_escape_or_nonsense_over_a_dash_puts_the_dash_back(key: Qt.Key) -> None:
    field, commits = a_field(-6.0)
    field.set_mixed()
    typed(field, "loud", key=key)
    assert field.text() == MIXED and field.mixed() and commits == []


def test_set_mixed_leaves_what_is_being_typed_alone() -> None:
    field, _ = a_field(-6.0)
    drag(field, [40, 40])
    QTest.keyClicks(field, "-9")
    field.set_mixed()
    assert field.text() == "-9"


def test_a_field_shows_and_takes_its_format() -> None:
    """A duration: the value is samples, the text is seconds."""
    field = NumericField(
        48_000, minimum=0, maximum=480_000, step=480, decimals=0, format=Duration()
    )
    field.show()
    commits: list[float] = []
    field.committed.connect(commits.append)
    assert field.text() == "1.000 s"

    typed(field, "250 ms")

    assert commits == [12_000] and field.text() == "0.250 s"


def test_refresh_reads_the_format_again() -> None:
    shown = ["one"]

    class Changing:
        def show(self, value: float) -> str:
            return shown[0]

        def parse(self, text: str) -> float | None:
            return None

    field = NumericField(0, minimum=0, maximum=1, step=1, format=Changing())
    assert field.text() == "one"
    shown[0] = "two"
    field.refresh()
    assert field.text() == "two"


def test_a_narrow_field_shows_the_start_of_its_value() -> None:
    """A line edit keeps its cursor at the end of what it holds, which in a
    field narrower than its text shows the end: `000 ms` for `1000 ms`."""
    field = NumericField(
        48_000,
        minimum=0,
        maximum=10**9,
        step=480,
        decimals=0,
        format=Duration("ms", decimals=0),
    )
    field.setFixedWidth(30)
    field.show()
    field.set_value(96_000)
    assert field.text() == "2000 ms" and field.cursorPosition() == 0
    field.set_mixed()
    field.set_value(144_000)
    assert field.cursorPosition() == 0
