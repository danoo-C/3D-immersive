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

**A drag on clips edits nothing until the release.** While it lasts, the
command the release would push is worked out at every movement - by
`dragging` for where the pointer snaps and by the command for how far the
clips may go - and the clips are drawn where it would leave them. The
release pushes that one command (02, *Undo*); `Esc` drops it.

**Colours are read when it paints**, from the `timeline` group (D-92), so
`retheme()` only asks for a repaint. Items put in the scene later read theirs
the same way, which is M9's warning about scene items answered: the view's
repaint reaches them because they have nothing to re-read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QWidget

from immersive.core.document import Document
from immersive.core.edits import Edge, FadeClips, MoveClips, TrimClips
from immersive.core.model import Channel, Clip, Fade
from immersive.core.selection import Kind, between, lane_of
from immersive.ui import theme
from immersive.ui.explorer.media_pool import MIME
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import NAME_HEIGHT, ClipItem, Peaks
from immersive.ui.timeline.dragging import (
    Part,
    handle_at,
    lanes_moved,
    part_at,
    snapped_move,
    snapped_trim,
    targets,
)
from immersive.ui.timeline.grid import Level, grid_lines, tempo_of
from immersive.ui.timeline.landing import Landing, dropped, landing
from immersive.ui.timeline.metrics import LANE_HEIGHT

#: How far one wheel notch zooms. Five notches is about a factor of three.
ZOOM_STEP = 1.25

#: How far one wheel notch scrolls sideways, in pixels.
SCROLL_STEP = 60

#: What Qt counts one wheel notch as.
NOTCH = 120

#: How far a press has to move before it is a drag rather than a click.
DRAG_THRESHOLD = 4

#: How much of its outline's colour the rubber band is filled with.
BAND_FILL = 0.12


@dataclass
class _Drag:
    """A press on a selected clip, and what it takes: the clip, which part,
    and the lane it was in. Once it has moved far enough it holds the
    selection it drags, the edges it may snap to, and the edit the release
    would push."""

    grabbed: Clip
    part: Part
    home: int
    clips: list[Clip] = field(default_factory=list)
    edges: list[int] = field(default_factory=list)
    edit: MoveClips | TrimClips | FadeClips | None = None


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
        #: Where a drag from the pool would land, while one is over the lanes.
        self._landing: Landing | None = None
        #: Where a left press began, until its release.
        self._press: QPointF | None = None
        #: A selected clip pressed without a modifier: selected alone on the
        #: release, unless the press became a drag (phase 5 drags them all).
        self._alone_on_release: Clip | None = None
        #: Where a Shift+click's range runs from: the clip last clicked or
        #: Ctrl-clicked.
        self._anchor: Clip | None = None
        #: The channel last clicked, through its header or one of its clips -
        #: what Ctrl+A selects first.
        self._focused: Channel | None = None
        #: A rubber band being dragged, in scene coordinates, and the clips
        #: that were selected when it began if it adds to them.
        self._band: QRectF | None = None
        self._band_keeps: list[Clip] = []
        #: A press on a selected clip, and the drag it becomes; see `_Drag`.
        self._drag: _Drag | None = None
        #: Where each dragged clip is drawn while the drag lasts, by the
        #: clip's identity: its lane, start, offset, length and fades.
        self._preview: dict[int, tuple[int, int, int, int, Fade, Fade]] = {}
        # The pointer says which edge a press would take before it presses.
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
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
        document.selection.observe(self._lay_out)
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

    # ----------------------------------------------------------- selecting

    def focus(self, channel: Channel) -> None:
        """The channel Ctrl+A selects the clips of first."""
        self._focused = channel

    def focused(self) -> Channel | None:
        """The channel last clicked, while it is still in the project."""
        channels = self._document.project.channels
        return next((c for c in channels if c is self._focused), None)

    def select_all(self) -> None:
        """Every clip on the focused channel - and, once those are selected,
        every clip in the project (04, *Selection*)."""
        project = self._document.project
        selection = self._document.selection
        channel = self.focused()
        on_channel = list(channel.clips) if channel is not None else []
        already = [id(clip) for clip in selection.clips()]
        if on_channel and already != [id(clip) for clip in on_channel]:
            selection.select(Kind.CLIPS, on_channel)
        else:
            everything = [clip for c in project.channels for clip in c.clips]
            selection.select(Kind.CLIPS, everything)

    def _clip_at(self, position: QPointF) -> ClipItem | None:
        item = self.itemAt(position.toPoint())
        return item if isinstance(item, ClipItem) else None

    def _click(self, item: ClipItem, modifiers: Qt.KeyboardModifier) -> None:
        """What a press on a clip does to the selection (04, *Selection*)."""
        project = self._document.project
        selection = self._document.selection
        clip = item.clip
        assert clip is not None
        self._focused = project.channels[item.lane]
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        anchor = self._anchor
        if anchor is not None:
            try:
                lane_of(project, anchor)
            except ValueError:
                anchor = None  # an Undo took it away
        if shift and anchor is not None:
            span = between(project, anchor, clip)
            if ctrl:
                selection.add(Kind.CLIPS, span)
            else:
                selection.select(Kind.CLIPS, span)
            return
        self._anchor = clip
        if ctrl:
            selection.toggle(Kind.CLIPS, clip)
        elif clip in selection:
            self._alone_on_release = clip
        else:
            selection.select(Kind.CLIPS, [clip])

    def band(self) -> QRectF | None:
        """The rubber band being dragged, in scene coordinates, if one is."""
        return self._band

    def _banding(self, event: QMouseEvent) -> bool:
        """A left drag from empty lane space: select every clip the band
        touches, across channels, as it is dragged. With Ctrl or Shift it
        adds to what was selected when the drag began."""
        assert self._press is not None
        moved = event.position() - self._press
        if self._band is None:
            if abs(moved.x()) + abs(moved.y()) < DRAG_THRESHOLD:
                return False
            adds = event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            )
            self._band_keeps = self._document.selection.clips() if adds else []
        corner = self.mapToScene(self._press.toPoint())
        here = self.mapToScene(event.position().toPoint())
        self._band = QRectF(corner, here).normalized()
        touched = {
            id(item.clip)
            for item in self._items.values()
            if item.sceneBoundingRect().intersects(self._band)
        }
        project = self._document.project
        self._document.selection.select(
            Kind.CLIPS,
            [
                *self._band_keeps,
                *(
                    clip
                    for channel in project.channels
                    for clip in channel.clips
                    if id(clip) in touched
                ),
            ],
        )
        self.viewport().update()
        return True

    def landing(self) -> Landing | None:
        """Where the drag over the lanes would land now, if one is."""
        return self._landing

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
                shown = self._preview.get(id(clip))
                at = shown[0] if shown is not None else lane
                item.present(
                    clip,
                    selected=clip in self._document.selection,
                    colour=project.channels[at].color,
                    name=sample.name if sample is not None else clip.media_id,
                    missing=sample is None or sample.missing,
                    lane=at,
                    scale=scale,
                    placing=shown[1:4] if shown is not None else None,
                    fades=shown[4:6] if shown is not None else None,
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
        if event.button() is Qt.MouseButton.LeftButton:
            self._press = event.position()
            self._alone_on_release = None
            self._drag = None
            item = self._clip_at(event.position())
            if item is not None:
                # Handles are on selected clips; a press that is what selects
                # one takes its body or an edge, as the pointer promised.
                handles = (
                    item.clip is not None and item.clip in self._document.selection
                )
                self._click(item, event.modifiers())
                self._grab(item, event.position(), handles=handles)
            event.accept()
            return
        self._pan_press(event)

    def _grab(self, item: ClipItem, position: QPointF, *, handles: bool) -> None:
        """Take the part of `item` under `position` - if its clip is
        selected once the press is done, so a Ctrl+press that toggled it out
        drags nothing. With `handles`, a fade handle is a part it may take."""
        clip = item.clip
        if clip is None or clip not in self._document.selection:
            return
        self._drag = _Drag(clip, self._part_of(item, position, handles), item.lane)

    def _part_of(self, item: ClipItem, position: QPointF, handles: bool) -> Part:
        """Which part of `item` a press at `position` would take: a fade
        handle in the name strip of a selected clip, else an edge or the body."""
        local = item.mapFromScene(self.mapToScene(position.toPoint()))
        width = item.boundingRect().width()
        if handles:
            fade_in, fade_out = item.fade_widths()
            found = handle_at(
                local.x(), local.y(), width, fade_in, fade_out, NAME_HEIGHT
            )
            if found is not None:
                return found
        return part_at(local.x(), width)

    def dragging(self) -> bool:
        """Whether a drag on clips is under way - past the threshold."""
        return self._drag is not None and self._drag.edit is not None

    def _dragged(self, event: QMouseEvent) -> None:
        """Work out what releasing here would do, and draw it."""
        drag, press = self._drag, self._press
        assert drag is not None and press is not None
        moved = event.position() - press
        if drag.edit is None:
            if abs(moved.x()) + abs(moved.y()) < DRAG_THRESHOLD:
                return
            drag.clips = self._document.selection.clips()
            if drag.part.fade is None:
                drag.edges = targets(self._document.project, drag.clips, drag.part.edge)
        project = self._document.project
        offset = round(moved.x() * self._axis.scale)
        exact = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        edge = drag.part.edge
        lanes_of = {id(item.clip): item.lane for item in self._items.values()}
        if drag.part.fade is not None:
            # Right lengthens a fade-in and shortens a fade-out.
            fades = FadeClips(
                drag.clips,
                drag.part.fade,
                offset if drag.part.fade is Edge.START else -offset,
            )
            drag.edit = fades
            self._preview = {
                id(clip): (lanes_of[id(clip)], *placing)
                for clip, placing in fades.fades()
            }
        elif edge is None:
            lanes = lanes_moved(
                self.mapToScene(press.toPoint()).y(),
                self.mapToScene(event.position().toPoint()).y(),
            )
            delta = snapped_move(
                project, drag.grabbed, drag.home, offset, lanes, drag.edges, exact=exact
            )
            move = MoveClips(project, drag.clips, delta, lanes)
            drag.edit = move
            self._preview = {
                id(clip): (
                    lane,
                    start,
                    clip.offset,
                    clip.length,
                    clip.fade_in,
                    clip.fade_out,
                )
                for clip, lane, start in move.placed()
            }
        else:
            channel = project.channels[drag.home]
            delta = snapped_trim(
                project, drag.grabbed, channel, edge, offset, drag.edges, exact=exact
            )
            trim = TrimClips(project, drag.clips, edge, delta)
            drag.edit = trim
            self._preview = {
                id(clip): (lanes_of[id(clip)], *placing)
                for clip, placing in trim.trims()
            }
        self._lay_out()

    def _end_drag(self) -> MoveClips | TrimClips | FadeClips | None:
        """Stop drawing a drag, and hand back the edit it would make."""
        edit = self._drag.edit if self._drag is not None else None
        self._drag = None
        if self._preview:
            self._preview = {}
            self._lay_out()
        return edit

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """`Esc` during a drag puts everything back and makes no edit."""
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._end_drag()
            self._press = None
            self._alone_on_release = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().keyPressEvent(event)

    def _pointing(self, position: QPointF) -> None:
        """Show, before any press, which edge a press here would take."""
        item = self._clip_at(position)
        part = Part.BODY
        if item is not None:
            selected = item.clip is not None and item.clip in self._document.selection
            part = self._part_of(item, position, selected)
        if part is Part.BODY:
            self.viewport().unsetCursor()
        else:
            self.viewport().setCursor(Qt.CursorShape.SizeHorCursor)

    def _pan_press(self, event: QMouseEvent) -> None:
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
        if self._press is not None and self._drag is not None:
            self._dragged(event)
            event.accept()
            return
        if self._press is None and self._pan is None:
            self._pointing(event.position())
        if (
            self._press is not None
            and self._alone_on_release is None
            and self._clip_at(self._press) is None
            and self._banding(event)
        ):
            event.accept()
            return
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
        if event.button() is Qt.MouseButton.LeftButton and self._press is not None:
            moved = event.position() - self._press
            clicked = abs(moved.x()) + abs(moved.y()) < DRAG_THRESHOLD
            empty = self._clip_at(self._press) is None
            modifiers = event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            )
            edit = self._end_drag()
            if edit is not None:
                if edit.changes:
                    self._document.push(edit)
            elif self._band is not None:
                self._band = None
                self.viewport().update()
            elif clicked and self._alone_on_release is not None:
                self._document.selection.select(Kind.CLIPS, [self._alone_on_release])
            elif clicked and empty and not modifiers:
                self._document.selection.clear()
            self._press = None
            self._alone_on_release = None
            event.accept()
            return
        self._pan_release(event)

    def _pan_release(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------ dropping from the pool

    def _landing_of(self, event: QDropEvent) -> Landing | None:
        """What dropping `event` here would do: the pool's samples, at the
        lane and sample under the pointer, as `landing` works it out."""
        data = event.mimeData()
        if not data.hasFormat(MIME):
            return None
        try:
            ids = json.loads(bytes(data.data(MIME).data()).decode("utf-8"))
        except ValueError:
            return None
        if not isinstance(ids, list):
            return None
        point = self.mapToScene(event.position().toPoint())
        modifiers = event.modifiers()
        return landing(
            self._document.project,
            [str(each) for each in ids],
            point.x(),
            point.y(),
            self._axis.scale,
            exact=bool(modifiers & Qt.KeyboardModifier.AltModifier),
            refuse_overlap=bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
        )

    def _hover(self, event: QDragMoveEvent) -> None:
        """Show where it would land, or refuse it - so the pointer says no
        before the release, rather than accepting and doing nothing."""
        where = self._landing_of(event)
        self._landing = where if where is not None and not where.refused else None
        if self._landing is None:
            event.ignore()
        else:
            event.acceptProposedAction()
        self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self._hover(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self._hover(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._landing = None
        self.viewport().update()

    def dropEvent(self, event: QDropEvent) -> None:
        """One command, whatever the drop does (F-4)."""
        where = self._landing_of(event)
        self._landing = None
        self.viewport().update()
        if where is None or where.refused:
            event.ignore()
            return
        project = self._document.project
        self._document.push(dropped(project, where, theme.active().channels))
        event.acceptProposedAction()

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
        """Where a drag would land, and the playhead, over everything the
        scene holds (04, *Timeline*)."""
        rect = QRectF(exposed)
        if self._band is not None:
            outline = QColor(theme.group_color("timeline", "band"))
            fill = QColor(outline)
            fill.setAlphaF(BAND_FILL)
            painter.setPen(outline)
            painter.setBrush(fill)
            painter.drawRect(self._band)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._landing is not None:
            scale = self._axis.scale
            pen = QPen(QColor(theme.group_color("timeline", "drop")))
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            top = self._landing.lane * LANE_HEIGHT + 1
            for sample, start in self._landing.placed:
                painter.drawRect(
                    QRectF(start / scale, top, sample.frames / scale, LANE_HEIGHT - 3)
                )
        x = round(self._playhead / self._axis.scale)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QColor(theme.group_color("timeline", "playhead")))
        painter.drawLine(x, int(rect.top()) - 1, x, int(rect.bottom()) + 1)
