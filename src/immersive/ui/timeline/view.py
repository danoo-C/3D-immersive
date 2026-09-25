"""The lanes: the grid behind them, and the playhead over them.

A `QGraphicsView` on the shared time axis (D-94). **A scene x is pixels at
the axis's scale** - a sample sits at `sample / scale` - so the view's own
horizontal scrollbar *is* the axis's offset: the axis changing moves the
scrollbar, the scrollbar moving moves the axis, and the ruler above, which
draws from the axis, cannot come apart from what the view has scrolled. A
zoom changes the scene's width; phase 3's clips are laid out again when it
does.

**The grid is drawn, not placed.** `drawBackground` asks `grid.grid_lines`
what is in the exposed span and draws those, so there are never more lines
than pixels allow and none as scene items.

**Colours are read when it paints**, from the `timeline` group (D-92), so
`retheme()` only asks for a repaint. Items put in the scene later read theirs
the same way, which is M9's warning about scene items answered: the view's
repaint reaches them because they have nothing to re-read.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QWidget

from immersive.core.document import Document
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import ClipItem, Peaks
from immersive.ui.timeline.grid import Level, grid_lines, tempo_of
from immersive.ui.timeline.metrics import LANE_HEIGHT

#: How far one wheel notch zooms. Five notches is about a factor of three.
ZOOM_STEP = 1.25

#: How far one wheel notch scrolls sideways, in pixels.
SCROLL_STEP = 60

#: What Qt counts one wheel notch as.
NOTCH = 120


class TimelineView(QGraphicsView):
    """The timeline's lanes, drawn against the shared axis."""

    def __init__(
        self,
        document: Document,
        axis: TimeAxis,
        peaks: Peaks | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._axis = axis
        self._peaks: Peaks = peaks or (lambda _media_id: None)
        #: One item per clip, by the clip's identity; see `_lay_out`.
        self._items: dict[int, ClipItem] = {}
        #: The scale the items were last laid out at: a zoom lays them out
        #: again, and a scroll, which changes only the offset, does not.
        self._laid_out_at: float | None = None
        #: Set while the axis is being written into the scrollbar, so the
        #: scrollbar's own signal does not write it back.
        self._syncing = False
        self._playhead = 0
        #: Where a middle-button pan began, and the axis offset and vertical
        #: scroll it began from; `None` when no pan is under way.
        self._pan: tuple[QPointF, int, int] | None = None

        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        # A scene narrower than the view sits at the left, where time starts,
        # not in the middle.
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.horizontalScrollBar().valueChanged.connect(self._scrolled)
        axis.observe(self._axis_changed)
        document.observe(self._project_changed)
        self._axis_changed()

    @property
    def axis(self) -> TimeAxis:
        return self._axis

    def set_playhead(self, sample: int) -> None:
        """Where to draw the playhead. The panel decides where it is."""
        self._playhead = sample
        self.viewport().update()

    def retheme(self) -> None:
        """Nothing is baked in - colours are read when they paint - so repaint.

        The clips too, one by one: each keeps what it last painted in Qt's
        cache, and a repaint of the viewport alone would show it again.
        """
        for item in self._items.values():
            item.update()
        self.viewport().update()

    def clip_items(self) -> list[ClipItem]:
        return list(self._items.values())

    def media_changed(self) -> None:
        """Peaks arrived, or a sample went missing or came back: every clip
        is shown again, and draws what it now has."""
        self._lay_out()
        for item in self._items.values():
            item.update()

    # ------------------------------------------------------------- the axis

    def _axis_changed(self) -> None:
        self._syncing = True
        try:
            # As tall as the lanes and one more, so the vertical scrollbar
            # reaches past the last, where a drop makes a new channel. The
            # grid is background, drawn across the whole view.
            lanes = (len(self._document.project.channels) + 1) * LANE_HEIGHT
            self.setSceneRect(QRectF(0, 0, self._axis.span(), lanes))
            self.horizontalScrollBar().setValue(self._axis.offset)
        finally:
            self._syncing = False
        if self._axis.scale != self._laid_out_at:
            self._lay_out()
        self.viewport().update()

    def _project_changed(self) -> None:
        """Channels and clips come and go, and the tempo draws the grid: lay
        out and repaint on every change the document reports."""
        self._lay_out()
        self._axis_changed()

    def _lay_out(self) -> None:
        """Bring the items into line with the project's clips, at the axis's
        scale.

        Kept by identity, as the headers keep channels: an item still
        belonging to its clip is shown again, which repaints it only if what
        it draws has changed; a new clip gets a new item; a gone clip's item
        leaves the scene.
        """
        project = self._document.project
        media = {entry.id: entry for entry in project.media_pool}
        scale = self._axis.scale
        seen: set[int] = set()
        for lane, channel in enumerate(project.channels):
            for clip in channel.clips:
                item = self._items.get(id(clip))
                if item is not None and item.clip is not clip:
                    # An id Python reused for a different clip.
                    self.scene().removeItem(item)
                    item = None
                if item is None:
                    item = ClipItem(self._peaks)
                    self.scene().addItem(item)
                    self._items[id(clip)] = item
                sample = media.get(clip.media_id)
                item.present(
                    clip,
                    colour=channel.color,
                    name=sample.name if sample is not None else clip.media_id,
                    missing=sample is None or sample.missing,
                    lane=lane,
                    scale=scale,
                )
                seen.add(id(clip))
        for key in [key for key in self._items if key not in seen]:
            self.scene().removeItem(self._items.pop(key))
        self._laid_out_at = scale

    def _scrolled(self, value: int) -> None:
        if not self._syncing:
            self._axis.scroll_to(value)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._axis.set_width(self.viewport().width())
        self._axis_changed()

    # ------------------------------------------------------------ the wheel

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ctrl+wheel zooms about the cursor, Shift+wheel or a sideways wheel
        scrolls along time, and the wheel alone scrolls the lanes (04).

        Shift+wheel arrives as a vertical delta with Shift held on some
        platforms and as a horizontal one on others, so both are sideways.
        """
        delta = event.angleDelta()
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            notches = (delta.y() or delta.x()) / NOTCH
            self._axis.zoom_about(event.position().x(), ZOOM_STEP ** (-notches))
            event.accept()
        elif modifiers & Qt.KeyboardModifier.ShiftModifier or (
            delta.x() and not delta.y()
        ):
            notches = (delta.x() or delta.y()) / NOTCH
            self._axis.scroll_by(round(-notches * SCROLL_STEP))
            event.accept()
        else:
            super().wheelEvent(event)

    # ------------------------------------------------- the middle button

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """A middle-button drag pans both ways, the lanes following the hand.

        It is how a mouse with no sideways wheel scrolls through time without
        holding a key - the gesture pro audio tools give it - and, with
        channels, through them at the same time.
        """
        if event.button() is Qt.MouseButton.MiddleButton:
            self._pan = (
                event.position(),
                self._axis.offset,
                self.verticalScrollBar().value(),
            )
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan is not None:
            # Measured from where the drag began rather than added up move by
            # move, so a long drag cannot drift from the hand by rounding.
            start, offset, vertical = self._pan
            moved = event.position() - start
            self._axis.scroll_to(offset - round(moved.x()))
            self.verticalScrollBar().setValue(vertical - round(moved.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ----------------------------------------------------------- painting

    def drawBackground(self, painter: QPainter, exposed: QRectF | QRect) -> None:
        rect = QRectF(exposed)
        painter.fillRect(rect, QColor(theme.group_color("timeline", "background")))

        scale = self._axis.scale
        tempo = tempo_of(self._document.project)
        pens = {
            Level.DIVISION: QColor(theme.group_color("timeline", "grid.division")),
            Level.BEAT: QColor(theme.group_color("timeline", "grid.beat")),
            Level.BAR: QColor(theme.group_color("timeline", "grid")),
        }
        top, bottom = int(rect.top()) - 1, int(rect.bottom()) + 1
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for line in grid_lines(
            max(rect.left(), 0) * scale,
            rect.right() * scale,
            scale,
            bpm=tempo.bpm,
            time_signature=tempo.time_signature,
            division=tempo.division,
            triplet=tempo.triplet,
        ):
            x = round(line.sample / scale)
            painter.setPen(pens[line.level])
            painter.drawLine(x, top, x, bottom)

        # The line under each lane, over the grid, so the lanes read as rows.
        painter.setPen(QColor(theme.group_color("timeline", "separator")))
        left, right = int(rect.left()) - 1, int(rect.right()) + 1
        for lane in range(1, len(self._document.project.channels) + 1):
            y = lane * LANE_HEIGHT - 1
            if top <= y <= bottom:
                painter.drawLine(left, y, right, y)

    def drawForeground(self, painter: QPainter, exposed: QRectF | QRect) -> None:
        """The playhead, over everything the scene holds (04, *Timeline*)."""
        rect = QRectF(exposed)
        x = round(self._playhead / self._axis.scale)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QColor(theme.group_color("timeline", "playhead")))
        painter.drawLine(x, int(rect.top()) - 1, x, int(rect.bottom()) + 1)
