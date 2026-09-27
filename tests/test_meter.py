"""The meter widget: what it paints, and its clip light (F-54, D-118).
Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.ui.metering import along
from immersive.ui.theme import group_color
from immersive.ui.widgets.meter import Meter

pytestmark = pytest.mark.gui

HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def db(value: float) -> float:
    return float(10 ** (value / 20))


def painted(meter: Meter) -> QImage:
    return meter.grab().toImage()


def colour(image: QImage, point: QPointF) -> str:
    return QColor(image.pixelColor(QPoint(int(point.x()), int(point.y())))).name()


def along_bar(meter: Meter, side: int, fraction: float) -> QPointF:
    """A point inside `side`'s bar, `fraction` of the way along it."""
    return meter.span(side, fraction, fraction).center()


def key(name: str) -> str:
    return QColor(group_color("meter", name)).name()


@pytest.mark.parametrize("orientation", [HORIZONTAL, VERTICAL])
def test_minus_30_dbfs_is_drawn_halfway(orientation: Qt.Orientation) -> None:
    meter = Meter(orientation)
    if orientation is VERTICAL:
        meter.resize(meter.width(), 60)
    meter.feed(db(-30.0), db(-30.0))
    image = painted(meter)
    for side in (0, 1):
        assert colour(image, along_bar(meter, side, 0.45)) == key("level")
        assert colour(image, along_bar(meter, side, 0.55)) == key("background")


def test_above_minus_6_the_bar_is_hot() -> None:
    meter = Meter(HORIZONTAL)
    meter.feed(db(-2.0), db(-2.0))
    image = painted(meter)
    assert colour(image, along_bar(meter, 0, along(-4.0))) == key("hot")
    assert colour(image, along_bar(meter, 0, along(-8.0))) == key("level")
    assert key("hot") != key("level")


def test_the_hold_is_drawn_where_the_peak_was() -> None:
    clock = [0.0]
    meter = Meter(HORIZONTAL, clock=lambda: clock[0])
    meter.feed(db(-12.0), db(-12.0))
    clock[0] += 1.0
    meter.feed(0.0, 0.0)
    image = painted(meter)
    assert colour(image, along_bar(meter, 0, along(-12.0))) == key("hold")


def click(meter: Meter, where: QPointF) -> None:
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            meter,
            QMouseEvent(
                kind,
                where,
                meter.mapToGlobal(where),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )


def test_the_clip_light_latches_says_so_in_more_than_colour_and_clears() -> None:
    meter = Meter(HORIZONTAL, clip_light=True)
    light = meter.light()
    assert light is not None
    meter.feed(1.5, 0.0)
    meter.feed(0.0, 0.0)
    assert meter.clipped()
    image = painted(meter)
    inside = {
        colour(image, QPointF(light.left() + x + 0.5, light.top() + y + 0.5))
        for x in range(int(light.width()))
        for y in range(int(light.height()))
    }
    assert key("clip") in inside and key("clip.text") in inside, "a `!` on it"

    click(meter, light.center())
    assert not meter.clipped()
    assert colour(painted(meter), light.center()) == key("background")


def test_a_click_on_the_bars_clears_nothing() -> None:
    meter = Meter(HORIZONTAL, clip_light=True)
    meter.feed(1.5, 0.0)
    click(meter, along_bar(meter, 0, 0.5))
    assert meter.clipped()


def test_no_clip_light_unless_asked_for() -> None:
    """A channel's meter (D-117): a channel of floats cannot clip."""
    meter = Meter(VERTICAL)
    meter.feed(2.0, 2.0)
    assert meter.light() is None and not meter.clipped()
