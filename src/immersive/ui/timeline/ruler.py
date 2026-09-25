"""The ruler above the lanes: ticks, labels, and where the playhead is.

It draws what `grid.ruler_marks` says for the span the shared axis has on
show, so it cannot disagree with the lanes below about where anything is
(D-94). Bars:beats or minutes:seconds (F-19); the lanes' grid is bars and
beats either way.

A click puts the playhead there. The ruler does not keep the playhead - the
panel does, and tells both widgets - so a click says where it was, and the
panel decides what that means. At phase 9 that is also where a seek comes
from.

**Colours are read when it paints**, from the `ruler` group and the
`timeline` group's playhead (D-92), so `retheme()` only asks for a repaint.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from immersive.core.document import Document
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.grid import Unit, ruler_marks, tempo_of

#: Tall enough for a label over a tick.
HEIGHT = 22

#: Tick lengths, from the bottom edge, in pixels.
MAJOR_TICK = 10
MINOR_TICK = 4

#: Label size in pixels, and how far a label sits right of its tick.
LABEL_PX = 10
LABEL_GAP = 3


class Ruler(QWidget):
    """Where the lanes below are in time, in the unit asked for."""

    #: A click, as the sample under it. `object` rather than `int`: a Qt
    #: `int` is 32 bits, and twelve hours of samples is more.
    clicked = Signal(object)

    def __init__(
        self, document: Document, axis: TimeAxis, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._axis = axis
        self._unit = Unit.BARS
        self._playhead = 0
        self.setFixedHeight(HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        axis.observe(self.update)
        document.observe(self.update)

    @property
    def unit(self) -> Unit:
        return self._unit

    def set_unit(self, unit: Unit) -> None:
        self._unit = unit
        self.update()

    def set_playhead(self, sample: int) -> None:
        self._playhead = sample
        self.update()

    def retheme(self) -> None:
        """Nothing is baked in - colours are read when it paints - so repaint."""
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            sample = max(round(self._axis.sample_at(event.position().x())), 0)
            self.clicked.emit(sample)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(theme.group_color("ruler", "background")))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        tempo = tempo_of(self._document.project)
        first, last = self._axis.visible()
        tick = QColor(theme.group_color("ruler", "tick"))
        text = QColor(theme.group_color("ruler", "text"))
        font = painter.font()
        font.setPixelSize(LABEL_PX)
        painter.setFont(font)
        bottom = self.height() - 1

        for mark in ruler_marks(
            first,
            last,
            self._axis.scale,
            self._unit,
            bpm=tempo.bpm,
            time_signature=tempo.time_signature,
            division=tempo.division,
            triplet=tempo.triplet,
        ):
            x = round(self._axis.x_of(mark.sample))
            painter.setPen(tick)
            length = MAJOR_TICK if mark.major else MINOR_TICK
            painter.drawLine(x, bottom - length + 1, x, bottom)
            if mark.label:
                painter.setPen(text)
                painter.drawText(
                    QRect(x + LABEL_GAP, 0, 200, bottom - MINOR_TICK),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    mark.label,
                )

        # The playhead crosses the ruler too, so the line the eye follows down
        # into the lanes starts where the time is read.
        painter.setPen(QColor(theme.group_color("timeline", "playhead")))
        x = round(self._axis.x_of(self._playhead))
        painter.drawLine(x, 0, x, bottom)
