"""A peak meter: the master's in the status bar, and each channel's in its
header (F-54, F-60, D-117).

Two bars, left and right, side by side - horizontal in the status bar,
vertical in a channel header - drawn from a `Ballistics` (D-118): the level
in `meter.level` and above -6 dBFS in `meter.hot`, the hold as a line in
`meter.hold`, on `meter.background`. The master alone has a clip light at
the end of its bars: `meter.clip` with a `!` in `meter.clip.text` while
latched, so the state is not colour alone, and a click on it clears it.

A painted group (D-92): the colours are read when it paints, so a theme
switch only asks for a repaint. It repaints only when the ballistics say
something moved, so a silent channel costs nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from immersive.ui.metering import FLOOR, HOT, Ballistics, along
from immersive.ui.theme import group_color

#: The master meter's bars, and its clip light beside them, in pixels.
BARS_LONG = 120
LIGHT = 12
GAP = 3

#: One side's bar across, and the room between the two.
BAR = 3
BETWEEN = 1

#: What the master meter says of itself.
MASTER_TIP = (
    "Output level, left and right - the peak holds for 1.5 s\n"
    "The light latches when the output passes full scale: click it to clear."
)


class Meter(QWidget):
    """Two bars and their holds, and - for the master - a clip light."""

    def __init__(
        self,
        orientation: Qt.Orientation,
        *,
        clip_light: bool = False,
        clock: Callable[[], float] = time.monotonic,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Meter")
        self.ballistics = Ballistics(clock)
        self._horizontal = orientation is Qt.Orientation.Horizontal
        self._clip_light = clip_light
        across = 2 * BAR + BETWEEN + 2
        if self._horizontal:
            light = LIGHT + GAP if clip_light else 0
            self.setFixedSize(BARS_LONG + light, max(across, LIGHT))
        else:
            self.setFixedWidth(across)
        if clip_light:
            self.setToolTip(MASTER_TIP)

    # ------------------------------------------------------------ feeding

    def feed(self, left: float, right: float) -> None:
        """One frame's peaks, linear; repainted only if anything moved."""
        if self.ballistics.feed(left, right):
            self.update()

    def clipped(self) -> bool:
        return self._clip_light and self.ballistics.clipped

    def clear(self) -> None:
        """The click on the clip light."""
        self.ballistics.clear()
        self.update()

    def retheme(self) -> None:
        self.update()

    # ------------------------------------------------------------ geometry

    def bars(self) -> QRectF:
        """Where both bars are drawn."""
        if self._horizontal:
            light = LIGHT + GAP if self._clip_light else 0
            return QRectF(0, 0, self.width() - light, self.height())
        return QRectF(0, 0, self.width(), self.height())

    def light(self) -> QRectF | None:
        """Where the clip light is, if this meter has one."""
        if not self._clip_light:
            return None
        return QRectF(self.width() - LIGHT, (self.height() - LIGHT) / 2, LIGHT, LIGHT)

    def span(self, side: int, start: float, end: float) -> QRectF:
        """One side's bar from `start` to `end` along the scale, 0 to 1."""
        bars = self.bars()
        offset = 1 + side * (BAR + BETWEEN)
        if self._horizontal:
            top = (bars.height() - (2 * BAR + BETWEEN)) / 2 + side * (BAR + BETWEEN)
            return QRectF(
                bars.left() + bars.width() * start,
                top,
                bars.width() * (end - start),
                BAR,
            )
        return QRectF(
            bars.left() + offset,
            bars.bottom() - bars.height() * end,
            BAR,
            bars.height() * (end - start),
        )

    # ------------------------------------------------------------ drawing

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        background = QColor(group_color("meter", "background"))
        painter.fillRect(self.bars(), background)
        hot_at = along(HOT)
        for side in (0, 1):
            level = along(self.ballistics.levels[side])
            painter.fillRect(
                self.span(side, 0.0, min(level, hot_at)),
                QColor(group_color("meter", "level")),
            )
            if level > hot_at:
                painter.fillRect(
                    self.span(side, hot_at, level),
                    QColor(group_color("meter", "hot")),
                )
            hold = self.ballistics.holds[side]
            if hold > FLOOR:
                at = along(hold)
                mark = self.span(side, at, at)
                if self._horizontal:
                    mark.setLeft(mark.left() - 1)
                    mark.setWidth(2)
                else:
                    mark.setTop(mark.top() - 1)
                    mark.setHeight(2)
                painter.fillRect(mark, QColor(group_color("meter", "hold")))
        light = self.light()
        if light is not None:
            if self.ballistics.clipped:
                painter.fillRect(light, QColor(group_color("meter", "clip")))
                font = QFont(painter.font())
                font.setBold(True)
                font.setPixelSize(LIGHT - 2)
                painter.setFont(font)
                painter.setPen(QColor(group_color("meter", "clip.text")))
                painter.drawText(light, Qt.AlignmentFlag.AlignCenter, "!")
            else:
                painter.fillRect(light, background)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        light = self.light()
        if light is not None and light.contains(QPointF(event.position())):
            self.clear()
            return
        super().mousePressEvent(event)
