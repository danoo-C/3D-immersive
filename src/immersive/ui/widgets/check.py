"""A check box that paints itself, from the painted `check` group (D-92).

The stylesheet can colour a check box's label but not its box: a sheet that
styles the indicator at all loses the style's own tick, and the style left
to itself draws an unchecked box nearly invisible on a dark panel and a
disabled one exactly like an enabled one. So it is painted, like the
waveform and the clips, and reads its colours when it paints.

**On is a tick as well as a colour**, and a box standing for several things
that differ holds a dash (04, *Selection*), so its state never rests on
colour alone. Clicking a dash turns every one of them on.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QCheckBox, QWidget

from immersive.ui import theme

#: The box's side, and the room between it and the label.
BOX = 14
GAP = 6


class CheckBox(QCheckBox):
    """A labelled check box, which may also read as mixed."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)

    def set_mixed(self) -> None:
        """Hold a dash: several things, some on and some off."""
        self.setCheckState(Qt.CheckState.PartiallyChecked)

    def mixed(self) -> bool:
        return self.checkState() is Qt.CheckState.PartiallyChecked

    def nextCheckState(self) -> None:
        """A click turns a dash on, like a box that was off."""
        on = self.checkState() is not Qt.CheckState.Checked
        self.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def retheme(self) -> None:
        """Nothing is baked in, so repaint."""
        self.update()

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        return QSize(
            BOX + GAP + metrics.horizontalAdvance(self.text()) + 2,
            max(BOX, metrics.height()) + 4,
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            enabled = self.isEnabled()
            state = self.checkState()
            filled = state is not Qt.CheckState.Unchecked
            disabled = QColor(theme.group_color("check", "disabled"))
            box = QRectF(0.5, (self.height() - BOX) / 2 + 0.5, BOX - 1, BOX - 1)

            edge = QColor(theme.group_color("check", "box")) if enabled else disabled
            if filled and enabled:
                fill = QColor(theme.group_color("check", "checked"))
            else:
                fill = QColor(theme.group_color("check", "background"))
            painter.setPen(QPen(fill if filled and enabled else edge, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(box, 3, 3)

            if filled:
                mark = QPen(
                    QColor(theme.group_color("check", "tick")) if enabled else disabled
                )
                mark.setWidthF(2)
                mark.setCapStyle(Qt.PenCapStyle.RoundCap)
                mark.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(mark)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                left, top, side = box.left(), box.top(), box.width()
                if state is Qt.CheckState.Checked:
                    painter.drawPolyline(
                        QPolygonF(
                            [
                                QPointF(left + side * 0.24, top + side * 0.52),
                                QPointF(left + side * 0.42, top + side * 0.72),
                                QPointF(left + side * 0.78, top + side * 0.30),
                            ]
                        )
                    )
                else:
                    middle = top + side / 2
                    painter.drawLine(
                        QPointF(left + side * 0.26, middle),
                        QPointF(left + side * 0.74, middle),
                    )

            if self.hasFocus():
                painter.setPen(QPen(QColor(theme.group_color("check", "focus")), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box.adjusted(-2, -2, 2, 2), 4, 4)

            painter.setPen(
                QColor(theme.group_color("check", "text")) if enabled else disabled
            )
            painter.drawText(
                QRect(BOX + GAP, 0, self.width() - BOX - GAP, self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.text(),
            )
        finally:
            painter.end()
