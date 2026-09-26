"""The ruler above the lanes: ticks, labels, and where the playhead is.

It draws what `grid.ruler_marks` says for the span the shared axis has on
show, so it cannot disagree with the lanes below about where anything is
(D-94). Bars:beats or minutes:seconds (F-19); the lanes' grid is bars and
beats either way.

**Three gestures (D-109).** A press within `REACH` pixels of the playhead
takes it, and a drag moves it. A press anywhere else that moves draws a
loop region, handed on at the release; one that does not move is a click,
which seeks. Each snaps to the grid and to the clips' edges by the
project's setting, and `Alt` places exactly. The ruler keeps neither the
playhead nor the region: it says what was asked for, and the panel decides
what that means.

**The loop region is drawn as a band** in the `timeline` group's
`loop.region`: filled while looping is on, and an outline while it is off,
so the switch shows as a shape as well as a colour.

**Colours are read when it paints**, from the `ruler` group and the
`timeline` group's playhead (D-92), so `retheme()` only asks for a repaint.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from immersive.core.document import Document
from immersive.core.model import MIN_LOOP_LENGTH
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.dragging import snapped_point, targets
from immersive.ui.timeline.grid import Level, Unit, ruler_marks, tempo_of

#: Tall enough for a label over a tick.
HEIGHT = 22

#: Tick lengths, from the bottom edge, in pixels: bars, beats, divisions.
TICKS = {Level.BAR: 10, Level.BEAT: 6, Level.DIVISION: 3}

#: Label size in pixels, and how far a label sits right of its tick.
LABEL_PX = 10
LABEL_GAP = 3

#: How near the playhead's line, in pixels, a press takes the playhead.
REACH = 5

#: How far a press has to move before it is a drag rather than a click.
DRAG_THRESHOLD = 4

#: How much of `loop.region` a looping region is filled with.
LOOP_FILL = 0.45


class Ruler(QWidget):
    """Where the lanes below are in time, in the unit asked for."""

    #: A click, as the sample under it, snapped. `object` rather than `int`:
    #: a Qt `int` is 32 bits, and twelve hours of samples is more.
    clicked = Signal(object)
    #: The playhead dragged to a sample, snapped - at every movement.
    dragged = Signal(object)
    #: A loop region drawn, its start and end, at the release.
    looped = Signal(object, object)

    def __init__(
        self, document: Document, axis: TimeAxis, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._axis = axis
        self._unit = Unit.BARS
        self._playhead = 0
        self._looping = False
        #: Where a left press began and what it took, until the release.
        self._press: QPointF | None = None
        self._taking_playhead = False
        self._moved = False
        #: The clips' edges, gathered at the press, for snapping.
        self._edges: list[int] = []
        #: A loop region being drawn, start and end, until the release.
        self._drawing: tuple[int, int] | None = None
        self.setMouseTracking(True)
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

    def set_looping(self, on: bool) -> None:
        self._looping = on
        self.update()

    def drawing(self) -> tuple[int, int] | None:
        """The loop region being drawn, if one is."""
        return self._drawing

    def retheme(self) -> None:
        """Nothing is baked in - colours are read when it paints - so repaint."""
        self.update()

    # ------------------------------------------------------------ the mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        x = event.position().x()
        self._press = event.position()
        self._moved = False
        self._taking_playhead = self._on_playhead(x)
        self._edges = targets(self._document.project, [])
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        if self._press is None:
            self._point(x)
            return
        if not self._moved and abs(x - self._press.x()) < DRAG_THRESHOLD:
            return
        self._moved = True
        exact = _exact(event)
        if self._taking_playhead:
            self.dragged.emit(self._sample(x, exact))
        else:
            ends = sorted(
                (self._sample(self._press.x(), exact), self._sample(x, exact))
            )
            self._drawing = (ends[0], ends[1])
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton or self._press is None:
            super().mouseReleaseEvent(event)
            return
        drawn, self._drawing = self._drawing, None
        if not self._moved:
            self.clicked.emit(self._sample(event.position().x(), _exact(event)))
        elif drawn is not None and drawn[1] - drawn[0] >= MIN_LOOP_LENGTH:
            self.looped.emit(drawn[0], drawn[1])
        self._press = None
        self.update()
        event.accept()

    def _on_playhead(self, x: float) -> bool:
        return abs(x - self._axis.x_of(self._playhead)) <= REACH

    def _point(self, x: float) -> None:
        """Show, before any press, that a press here takes the playhead."""
        if self._on_playhead(x):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()

    def _sample(self, x: float, exact: bool) -> int:
        sample = max(round(self._axis.sample_at(x)), 0)
        return snapped_point(self._document.project, sample, self._edges, exact=exact)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(theme.group_color("ruler", "background")))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_loop(painter)

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
            painter.drawLine(x, bottom - TICKS[mark.level] + 1, x, bottom)
            if mark.label:
                painter.setPen(text)
                painter.drawText(
                    QRect(x + LABEL_GAP, 0, 200, bottom - TICKS[Level.BEAT]),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    mark.label,
                )

        # The playhead crosses the ruler too, so the line the eye follows down
        # into the lanes starts where the time is read.
        painter.setPen(QColor(theme.group_color("timeline", "playhead")))
        x = round(self._axis.x_of(self._playhead))
        painter.drawLine(x, 0, x, bottom)

    def _paint_loop(self, painter: QPainter) -> None:
        """The loop region, filled while looping and an outline while not,
        and a region being drawn as a dashed outline."""
        colour = QColor(theme.group_color("timeline", "loop.region"))
        loop = self._document.project.loop
        if loop is not None:
            band = self._band(loop.start, loop.end)
            if self._looping:
                fill = QColor(colour)
                fill.setAlphaF(LOOP_FILL)
                painter.fillRect(band, fill)
            painter.setPen(colour)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(band.adjusted(0, 0, -1, -1))
        if self._drawing is not None:
            pen = QPen(colour)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._band(*self._drawing).adjusted(0, 0, -1, -1))

    def _band(self, start: int, end: int) -> QRectF:
        left = self._axis.x_of(start)
        return QRectF(left, 0, max(self._axis.x_of(end) - left, 1), self.height())


def _exact(event: QMouseEvent) -> bool:
    return bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
