"""The info box: what is under way, at the right end of the transport
toolbar (D-116). Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QToolBar, QWidget

from immersive.app import build_application
from immersive.ui.activity import SHOW_AFTER, Activities
from immersive.ui.main_window import MainWindow
from immersive.ui.widgets.info_box import STEPS, InfoBox

pytestmark = pytest.mark.gui


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def boxed() -> tuple[InfoBox, Activities, Clock, QWidget]:
    clock = Clock()
    board = Activities(clock)
    holder = QWidget()
    box = InfoBox(board, holder)
    holder.show()
    QApplication.processEvents()
    return box, board, clock, holder


def later(box: InfoBox, clock: Clock, seconds: float = SHOW_AFTER) -> None:
    """Time passes; the box's own timer fires, as it would have."""
    clock.now += seconds
    box._timer.timeout.emit()


def test_nothing_shows_before_a_quarter_second() -> None:
    box, board, _, _ = boxed()
    board.begin("Importing 0 of 3 files", maximum=300)
    assert box.showing() is None and not box.isVisible()
    assert box._timer.isActive(), "and it will look again when one is due"
    assert 0 < box._timer.interval() <= SHOW_AFTER * 1000


def test_one_still_running_at_a_quarter_second_shows_unprompted() -> None:
    box, board, clock, _ = boxed()
    work = board.begin("Importing 0 of 3 files", maximum=300)
    later(box, clock)
    assert box.showing() is work and box.isVisible()
    assert box.label() == "Importing 0 of 3 files"


def test_the_label_and_the_value_of_the_maximum_are_drawn() -> None:
    box, board, clock, _ = boxed()
    work = board.begin("Importing 0 of 3 files", maximum=200)
    later(box, clock)
    work.update(50, label="Importing 1 of 3 files")
    assert box.label() == "Importing 1 of 3 files"
    bar = box.bar()
    assert (bar.minimum(), bar.maximum(), bar.value()) == (0, STEPS, STEPS // 4)


def test_a_maximum_past_32_bits_is_drawn_right() -> None:
    """An import counted in bytes passes 2 GB."""
    box, board, clock, _ = boxed()
    work = board.begin("x", maximum=6 * 2**31)
    later(box, clock)
    work.update(3 * 2**31)
    assert box.bar().value() == STEPS // 2


def test_a_maximum_of_0_is_busy() -> None:
    box, board, clock, _ = boxed()
    board.begin("Loading")
    later(box, clock)
    assert (box.bar().minimum(), box.bar().maximum()) == (0, 0)


def test_two_show_the_first_begun_and_how_many_more() -> None:
    box, board, clock, _ = boxed()
    first = board.begin("Importing 2 of 22 files", maximum=100)
    board.begin("Rendering", maximum=0)
    later(box, clock)
    first.update(40)
    assert box.showing() is first
    assert box.label() == "Importing 2 of 22 files", "drawn, not only chosen"
    assert box.bar().value() == STEPS * 2 // 5
    assert box.more() == "+1 more"
    assert box.toolTip() == "Importing 2 of 22 files — 40%\nRendering"


def test_a_cancel_shows_only_with_a_cancel_and_calls_it() -> None:
    box, board, clock, _ = boxed()
    stopped: list[int] = []
    plain = board.begin("Loading")
    later(box, clock)
    assert not box.can_cancel()
    plain.finish()

    board.begin("Importing", maximum=10, cancel=lambda: stopped.append(1))
    later(box, clock)
    assert box.can_cancel()
    box._cancel.click()
    assert stopped == [1]
    assert box._cancel.width() >= 20 and box._cancel.height() >= 20, (
        "no smaller a target than that"
    )


def test_empty_and_hidden_once_all_have_finished() -> None:
    box, board, clock, _ = boxed()
    work = board.begin("x", maximum=1)
    later(box, clock)
    assert box.isVisible()
    work.finish()
    assert box.showing() is None and not box.isVisible()
    assert box.toolTip() == ""


def test_in_the_window_it_is_last_and_moves_nothing() -> None:
    window = MainWindow()
    window.resize(1500, 950)
    window.show()
    QApplication.processEvents()
    [bar] = window.findChildren(QToolBar)
    box = window.info_box()
    assert bar.actions()[-1] is box._action
    assert not bar.widgetForAction(bar.actions()[-1]).isVisible()
    # Everything but the box, and the spacer that gives way to it.
    others = [
        w
        for w in bar.findChildren(QWidget)
        if w.isVisible() and w.parent() is bar and w.objectName() != "ToolbarSpacer"
    ]
    before = [w.geometry() for w in others]
    height = bar.height()

    clock = Clock()
    window.activities()._clock = clock
    work = window.activities().begin("Importing", maximum=10)
    later(box, clock)
    QApplication.processEvents()

    assert box.isVisible()
    assert box.geometry().right() >= bar.width() - 12, "at the right end"
    assert box.geometry().right() > max(g.right() for g in before)
    assert [w.geometry() for w in others] == before
    assert bar.height() == height, "no taller than the buttons"
    work.finish()
    QApplication.processEvents()
    assert not box.isVisible()
    assert [w.geometry() for w in others] == before
    window.deleteLater()


def test_at_the_windows_narrowest_it_gives_way_but_stays_in_sight() -> None:
    """Below its width Qt would fold it into the toolbar's overflow menu."""
    window = MainWindow()
    window.show()
    window.resize(window.minimumWidth(), 700)
    QApplication.processEvents()
    clock = Clock()
    window.activities()._clock = clock
    window.activities().begin("Importing 7 of 22 files", maximum=10)
    later(window.info_box(), clock)
    QApplication.processEvents()

    box = window.info_box()
    [bar] = window.findChildren(QToolBar)
    assert box.isVisible()
    assert box.width() < 260 and box.geometry().right() <= bar.width()
    assert box.label().startswith("Importing"), "the whole label, elided on screen"
    window.deleteLater()
