"""The painted check box: on, off, a dash for several things that differ,
and its colours read when it paints (D-92). Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.ui import theme
from immersive.ui.widgets.check import BOX, GAP, CheckBox

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def a_box(text: str = "Mute") -> tuple[CheckBox, list[bool]]:
    box = CheckBox(text)
    box.resize(box.sizeHint())
    box.show()
    QApplication.processEvents()
    clicks: list[bool] = []
    box.clicked.connect(lambda on: clicks.append(on))
    return box, clicks


def test_a_click_turns_it_on_and_off() -> None:
    box, clicks = a_box()
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(BOX // 2, 8))
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(BOX // 2, 8))
    assert clicks == [True, False]


def test_a_click_on_its_label_counts() -> None:
    box, clicks = a_box("HRTF bypass")
    QTest.mouseClick(
        box, Qt.MouseButton.LeftButton, pos=QPoint(box.width() - 4, box.height() // 2)
    )
    assert clicks == [True]


def test_a_dash_is_turned_on_by_a_click() -> None:
    """Several things, some on: one click puts them all on."""
    box, clicks = a_box()
    box.set_mixed()
    assert box.mixed()
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(BOX // 2, 8))
    assert clicks == [True] and not box.mixed()


def pixel(box: CheckBox, x: int, y: int) -> QColor:
    return box.grab().toImage().pixelColor(x, y)


def test_it_paints_its_state_from_the_check_group() -> None:
    """Filled in `checked` when on, `background` when off - and the label
    in `text`, or in `disabled` once it is."""
    box, _ = a_box()
    middle = (BOX // 2 - 3, box.height() // 2 - 3)
    off = pixel(box, *middle)
    box.setChecked(True)
    on = pixel(box, *middle)
    assert on.name().upper() == theme.group_color("check", "checked").upper()
    assert off.name().upper() == theme.group_color("check", "background").upper()

    box.setEnabled(False)
    assert pixel(box, *middle).name().upper() != on.name().upper()


def test_it_is_as_wide_as_its_box_and_label() -> None:
    box, _ = a_box("Solo")
    assert box.sizeHint().width() >= BOX + GAP + box.fontMetrics().horizontalAdvance(
        "Solo"
    )
