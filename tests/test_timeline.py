"""The timeline: its view on the shared axis, and the grid it draws.

Marked gui. Built widget by widget rather than as a `MainWindow`, which costs
fifty milliseconds a test for a window none of these look at.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme, theme_io
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.view import SCROLL_STEP, ZOOM_STEP, TimelineView

pytestmark = pytest.mark.gui

WIDTH, HEIGHT = 800, 120
HOUR = SAMPLE_RATE * 3600

#: At 120 BPM and 480 samples a pixel a beat is 50 px and a bar 200.
SCALE = 480.0
BAR_PX = 200

#: Multipliers and offsets that give every token a colour unlike any other.
SPREAD = ((37, 11), (53, 7), (71, 3))


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    before = theme.active()
    yield
    theme.use(before)


def viewed(
    scale: float = SCALE, *, snapping: bool = False
) -> tuple[TimelineView, Document]:
    document = Document()
    document.project.snap.enabled = snapping
    view = TimelineView(document, TimeAxis(scale, extent=HOUR))
    view.resize(WIDTH, HEIGHT)
    view.show()
    return view, document


def grabbed(view: TimelineView) -> QImage:
    return view.viewport().grab().toImage()


def colour(key: str) -> str:
    return theme.group_color("timeline", key).upper()


def at(image: QImage, x: int) -> str:
    return image.pixelColor(x, image.height() // 2).name().upper()


def row(image: QImage) -> set[str]:
    return {at(image, x) for x in range(image.width())}


def wheel(
    view: TimelineView,
    x: float,
    *,
    dx: int = 0,
    dy: int = 0,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    point = QPointF(x, 10)
    event = QWheelEvent(
        point,
        view.viewport().mapToGlobal(point),
        QPoint(),
        QPoint(dx, dy),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


# --------------------------------------------------------------------------- #
# the grid, where the axis says
# --------------------------------------------------------------------------- #


def test_bar_lines_are_drawn_where_the_axis_puts_them() -> None:
    view, _ = viewed()
    view.axis.scroll_to(130)
    image = grabbed(view)
    first, last = view.axis.visible()

    bars = [n * BAR_PX * SCALE for n in range(int(first // (BAR_PX * SCALE)) + 1, 40)]
    columns = [round(view.axis.x_of(sample)) for sample in bars if sample < last]
    assert len(columns) >= 3
    for x in columns:
        assert at(image, x) == colour("grid"), x
        assert at(image, x + BAR_PX // 8) == colour("background"), "between beats"
    assert at(image, columns[0] + BAR_PX // 4) == colour("grid.beat")


def test_division_lines_follow_the_snap_setting() -> None:
    on, _ = viewed(snapping=True)  # 1/16 is 12.5 px: room
    off, _ = viewed(snapping=False)

    assert colour("grid.division") in row(grabbed(on))
    assert colour("grid.division") not in row(grabbed(off))


def test_a_theme_change_repaints_every_colour() -> None:
    view, _ = viewed(snapping=True)
    before = row(grabbed(view))
    builtin = theme_io.builtin()
    loud = replace(
        builtin,
        tokens={
            name: "#" + "".join(f"{(n * k + c) % 256:02X}" for k, c in SPREAD)
            for n, name in enumerate(sorted(builtin.tokens))
        },
    )
    theme.use(loud)

    view.retheme()

    assert not before & row(grabbed(view))


# --------------------------------------------------------------------------- #
# the scrollbar is the axis
# --------------------------------------------------------------------------- #


def test_the_axis_is_as_wide_as_the_lanes() -> None:
    view, _ = viewed()
    assert view.axis.width == view.viewport().width()

    view.resize(WIDTH + 150, HEIGHT)

    assert view.axis.width == view.viewport().width()


def test_moving_the_scrollbar_moves_the_axis() -> None:
    view, _ = viewed()

    view.horizontalScrollBar().setValue(1234)

    assert view.axis.offset == 1234


def test_moving_the_axis_moves_the_scrollbar() -> None:
    view, _ = viewed()

    view.axis.scroll_to(777)

    assert view.horizontalScrollBar().value() == 777


def test_the_scrollbar_reaches_exactly_the_axis_extent() -> None:
    view, _ = viewed()
    assert view.horizontalScrollBar().maximum() == view.axis.span() - view.axis.width


# --------------------------------------------------------------------------- #
# the wheel
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("notch", "factor"), [(120, 1 / ZOOM_STEP), (-120, ZOOM_STEP)])
def test_ctrl_wheel_zooms_about_the_cursor(notch: int, factor: float) -> None:
    view, _ = viewed()
    view.axis.scroll_to(view.axis.span() // 2)
    before = view.axis.sample_at(300)

    wheel(view, 300, dy=notch, modifiers=Qt.KeyboardModifier.ControlModifier)

    assert view.axis.scale == pytest.approx(SCALE * factor)
    assert abs(view.axis.sample_at(300) - before) <= 0.5 * view.axis.scale


@pytest.mark.parametrize(
    ("dx", "dy", "modifiers"),
    [
        (0, -120, Qt.KeyboardModifier.ShiftModifier),
        (-120, 0, Qt.KeyboardModifier.ShiftModifier),
        (-120, 0, Qt.KeyboardModifier.NoModifier),
    ],
    ids=["shift and a vertical delta", "shift and a sideways one", "sideways alone"],
)
def test_shift_wheel_or_a_sideways_wheel_scrolls_along_time(
    dx: int, dy: int, modifiers: Qt.KeyboardModifier
) -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    wheel(view, 300, dx=dx, dy=dy, modifiers=modifiers)

    assert view.axis.offset == 1000 + SCROLL_STEP
    assert view.axis.scale == SCALE
    assert view.verticalScrollBar().value() == 0


def test_the_wheel_alone_leaves_time_where_it_is() -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    wheel(view, 300, dy=-120)

    assert (view.axis.offset, view.axis.scale) == (1000, SCALE)
