"""The top and front views (04, *Workspace (centre)*; D-49, D-143).

One `OrthoView` draws one plane of the scene around the listener: the top
view X across and Y up-screen, the front view X across and Z up-screen.
Screen-right is +X in both (03, *Coordinate system*), so the front view is
the listener's own front, seen from behind them. Both read one `Scale`,
which zooms and pans them together sideways.

**What is drawn**, back to front: the background; the top view's rings,
a metre apart or wider as it zooms out, and the front view's ear-level
line; the head, fixed at the centre and a fixed size, since it marks where
the listener is rather than how big a head is; then every channel that is
not bypassed, its point or its pair's two sides joined, in the channel's
colour; and the selected channels last, ringed, so they are drawn over the
others. A bypassed channel has no position, and so is on no canvas (D-36).

**A painted group** (D-92): the colours are the `spatial` group's, read when
it paints, so a theme switch only asks for a repaint. `icon` and `pair` may
be the reserved `channel` value, as the clips' are.

**Selecting.** A click selects the channel under the pointer, the one drawn
on top first; Ctrl-click toggles it; a click on nothing clears. It goes
through the document's selection, so the headers and the pane follow.

**Dragging** (D-144, D-145). A press on an icon selects it, and once the
pointer has moved `DRAG_THRESHOLD` pixels the drag begins: the side grabbed
follows the pointer at the offset it was grabbed at, the top view setting X
and Y and the front view X and Z. Where it would be is held by the
`Placing` both views and the pane share, and both views draw the channel
being dragged from it. The model is left alone until the release, which
pushes the one edit the drag makes. Esc drops the drag.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from immersive.core.document import Document
from immersive.core.model import Channel, Position, paired, sides
from immersive.core.selection import Kind
from immersive.ui.spatial.placing import Placing
from immersive.ui.spatial.scale import Plane, Scale
from immersive.ui.theme import channel_group_color, group_color

#: An icon's radius in pixels: a channel's one point, and each side of a
#: pair. Phase 3 makes them say distance; here they are one size.
POINT_RADIUS: Final = 7.0
SIDE_RADIUS: Final = 6.0

#: How far beyond an icon a click still takes it, and the selected ring's
#: width and gap, in pixels.
REACH: Final = 3.0
RING: Final = 2.0
RING_GAP: Final = 3.0

#: The head glyph's radius, pixels.
HEAD: Final = 12.0

#: The fewest pixels between two rings: zoomed out, rings are drawn every
#: 2, 5, 10 ... metres rather than packing into a grey disc.
RING_SPACING: Final = 28.0
RING_STEPS: Final = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)

#: One notch of a mouse wheel zooms by this much.
WHEEL_ZOOM: Final = 1.15

#: How far a press must move, in pixels, before it is a drag and not a
#: click: the timeline's own threshold.
DRAG_THRESHOLD: Final = 4


@dataclass(frozen=True)
class Icon:
    """One drawn icon: whose, which side (-1 for a channel's one point, 0 for
    a pair's left, 1 for its right), where, and how big."""

    channel: Channel
    side: int
    centre: QPointF
    radius: float


@dataclass(frozen=True)
class _Press:
    """A press on an icon: where, the side's position then, and how far from
    it in metres the press was, so a drag does not make the icon jump."""

    icon: Icon
    at: QPointF
    grabbed: Position
    offset: tuple[float, float]


class OrthoView(QWidget):
    """One plane of the scene, drawn around the listener."""

    def __init__(
        self,
        document: Document,
        scale: Scale,
        plane: Plane,
        placing: Placing | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TopView" if plane == "top" else "FrontView")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(160, 160)
        self._document = document
        self._scale = scale
        self._plane: Plane = plane
        self._panning: QPointF | None = None
        self._placing = placing if placing is not None else Placing()
        self._press: _Press | None = None
        document.observe(self._project_changed)
        document.selection.observe(self.update)
        scale.observe(self.update)
        self._placing.observe(self.update)

    @property
    def plane(self) -> Plane:
        return self._plane

    def retheme(self) -> None:
        """A theme switch: the colours are read when it paints."""
        self.update()

    def _project_changed(self) -> None:
        """Repaint. An edit made while this view's drag goes on - an undo,
        a delete, anything the window's keys push - drops the drag as Esc
        does, since it was placed against a model that has changed. The
        release ends the press before it pushes, so its own edit is not."""
        if self._press is not None:
            self._press = None
            self._placing.cancel()
        self.update()

    # ------------------------------------------------------------ geometry

    def point_of(self, position: Position) -> QPointF:
        """Where `position` is drawn in this view."""
        up = position.y if self._plane == "top" else position.z
        x, y = self._scale.pixel(
            self._plane, self.width(), self.height(), position.x, up
        )
        return QPointF(x, y)

    def icons(self) -> list[Icon]:
        """Every icon, in the order it is drawn: the selected last."""
        project = self._document.project
        selection = self._document.selection
        drawn: list[Icon] = []
        on_top: list[Icon] = []
        for channel in project.channels:
            if channel.hrtf_bypass:
                continue
            into = on_top if channel in selection else drawn
            placed = self._placing.sides(channel) or sides(channel)
            if paired(project, channel):
                left, right = placed
                into.append(Icon(channel, 0, self.point_of(left), SIDE_RADIUS))
                into.append(Icon(channel, 1, self.point_of(right), SIDE_RADIUS))
            else:
                centre = self.point_of(placed[0])
                into.append(Icon(channel, -1, centre, POINT_RADIUS))
        return drawn + on_top

    def icon_at(self, point: QPointF) -> Icon | None:
        """The icon drawn on top at `point`, or None."""
        for icon in reversed(self.icons()):
            reach = icon.radius + REACH
            offset = point - icon.centre
            if offset.x() ** 2 + offset.y() ** 2 <= reach * reach:
                return icon
        return None

    # ------------------------------------------------------------- drawing

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(group_color("spatial", "background")))
        if self._plane == "top":
            self._draw_rings(painter)
        else:
            self._draw_level(painter)
        self._draw_head(painter)
        icons = self.icons()
        self._draw_pairs(painter, icons)
        selection = self._document.selection
        for icon in icons:
            self._draw_icon(painter, icon, selected=icon.channel in selection)
        painter.end()

    def _step(self) -> float:
        """Metres between rings, or between height lines: one, or more as
        it zooms out, so they stay at least `RING_SPACING` apart."""
        per = self._scale.per_metre(self.width(), self.height())
        return next((s for s in RING_STEPS if s * per >= RING_SPACING), RING_STEPS[-1])

    def _draw_rings(self, painter: QPainter) -> None:
        """A ring a metre apart about the head - or wider apart, zoomed out -
        each labelled on its right."""
        per = self._scale.per_metre(self.width(), self.height())
        step = self._step()
        centre = self.point_of(Position())
        farthest = (
            (self.width() ** 2 + self.height() ** 2) ** 0.5
            + abs(centre.x() - self.width() / 2)
            + abs(centre.y() - self.height() / 2)
        )
        painter.setFont(_small(painter.font()))
        ring = QPen(QColor(group_color("spatial", "ring")), 1.0)
        label = QColor(group_color("spatial", "ring.label"))
        metres = step
        while metres * per <= farthest:
            radius = metres * per
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, radius, radius)
            painter.setPen(label)
            painter.drawText(
                QPointF(centre.x() + radius + 3, centre.y() - 3), f"{metres:g} m"
            )
            metres += step

    def _draw_level(self, painter: QPainter) -> None:
        """The front view's heights: a line a metre apart - or wider apart,
        zoomed out - each labelled, and the one at Z = 0, ear level, in its
        own colour."""
        step = self._step()
        _, top = self._scale.metres(self._plane, self.width(), self.height(), 0, 0)
        _, bottom = self._scale.metres(
            self._plane, self.width(), self.height(), 0, self.height()
        )
        painter.setFont(_small(painter.font()))
        label = QColor(group_color("spatial", "ring.label"))
        height = step * int(bottom // step)
        while height <= top:
            y = self.point_of(Position(0.0, 0.0, height)).y()
            line = (
                group_color("spatial", "level")
                if height == 0
                else group_color("spatial", "ring")
            )
            painter.setPen(QPen(QColor(line), 1.0))
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
            painter.setPen(label)
            text = "ear level" if height == 0 else f"{height:+g} m"
            painter.drawText(QPointF(4, y - 4), text)
            height += step

    def _draw_head(self, painter: QPainter) -> None:
        """The listener, at the origin: from above, facing up-screen with a
        nose; from behind, in the front view, with its ears either side."""
        centre = self.point_of(Position())
        painter.setPen(QPen(QColor(group_color("spatial", "head")), 1.5))
        painter.setBrush(QColor(group_color("spatial", "head.fill")))
        for side in (-1.0, 1.0):  # the ears
            painter.drawEllipse(
                QPointF(centre.x() + side * HEAD, centre.y()), HEAD / 4, HEAD / 2.5
            )
        painter.drawEllipse(centre, HEAD, HEAD)
        if self._plane == "top":
            nose = QPainterPath()
            nose.moveTo(centre.x() - HEAD / 3, centre.y() - HEAD + 1)
            nose.lineTo(centre.x(), centre.y() - HEAD - HEAD / 2)
            nose.lineTo(centre.x() + HEAD / 3, centre.y() - HEAD + 1)
            painter.drawPath(nose)

    def _draw_pairs(self, painter: QPainter, icons: list[Icon]) -> None:
        """The line joining each pair's two sides, under their icons."""
        left: dict[str, Icon] = {}
        for icon in icons:
            if icon.side == 0:
                left[icon.channel.id] = icon
            elif icon.side == 1 and icon.channel.id in left:
                colour = channel_group_color("spatial", "pair", icon.channel.color)
                painter.setPen(QPen(QColor(colour), 1.5))
                painter.drawLine(left[icon.channel.id].centre, icon.centre)

    def _draw_icon(self, painter: QPainter, icon: Icon, *, selected: bool) -> None:
        colour = QColor(channel_group_color("spatial", "icon", icon.channel.color))
        if selected:
            painter.setPen(QPen(QColor(group_color("spatial", "selected")), RING))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            around = icon.radius + RING_GAP
            painter.drawEllipse(icon.centre, around, around)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(icon.centre, icon.radius, icon.radius)
        if icon.side >= 0:
            painter.setPen(QColor(group_color("spatial", "background")))
            painter.setFont(_small(painter.font(), bold=True))
            box = QRectF(
                icon.centre.x() - icon.radius,
                icon.centre.y() - icon.radius,
                2 * icon.radius,
                2 * icon.radius,
            )
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "LR"[icon.side])

    # --------------------------------------------------------------- mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.MiddleButton:
            self._panning = event.position()
            event.accept()
            return
        if event.button() is not Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus()
        icon = self.icon_at(event.position())
        selection = self._document.selection
        if icon is None:
            selection.clear()
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            selection.toggle(Kind.CHANNELS, icon.channel)
        else:
            if icon.channel not in selection:
                selection.select(Kind.CHANNELS, [icon.channel])
            grabbed = sides(icon.channel)[max(icon.side, 0)]
            across, up = self._metres(event.position())
            self._press = _Press(
                icon,
                event.position(),
                grabbed,
                (grabbed.x - across, self._up(grabbed) - up),
            )
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning is not None:
            moved = event.position() - self._panning
            self._panning = event.position()
            self._scale.pan(
                self._plane, self.width(), self.height(), moved.x(), moved.y()
            )
            event.accept()
            return
        press = self._press
        if press is None:
            super().mouseMoveEvent(event)
            return
        if self._placing.channel is None:
            moved = event.position() - press.at
            if abs(moved.x()) + abs(moved.y()) < DRAG_THRESHOLD:
                return
            self._placing.begin(press.icon.channel, press.icon.side)
        across, up = self._metres(event.position())
        self._placing.move(
            self._placed(press.grabbed, across + press.offset[0], up + press.offset[1])
        )
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.MiddleButton:
            self._panning = None
            event.accept()
            return
        if event.button() is Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            if self._placing.channel is not None:
                # The edit first, then the clearing: whatever is told of the
                # drag ending finds the model already where it put the source.
                edit = self._placing.edit()
                if edit is not None:
                    self._document.push(edit)
                self._placing.clear()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def event(self, event: QEvent) -> bool:
        """Esc is the window's Stop too: during a drag this view claims it,
        so it drops the drag, as the timeline's drags claim it."""
        if (
            self._press is not None
            and event.type() == QEvent.Type.ShortcutOverride
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._press is not None:
            self._press = None
            self._placing.cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def _metres(self, point: QPointF) -> tuple[float, float]:
        """The metres across and up under `point`."""
        return self._scale.metres(
            self._plane, self.width(), self.height(), point.x(), point.y()
        )

    def _up(self, position: Position) -> float:
        return position.y if self._plane == "top" else position.z

    def _placed(self, grabbed: Position, across: float, up: float) -> Position:
        """`grabbed` moved to `across` and `up` in this view's plane: its
        third axis left where it was."""
        if self._plane == "top":
            return replace(grabbed, x=across, y=up)
        return replace(grabbed, x=across, z=up)

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120
        if notches:
            where = event.position()
            self._scale.zoom_about(
                self._plane,
                self.width(),
                self.height(),
                where.x(),
                where.y(),
                WHEEL_ZOOM ** (-notches),
            )
        event.accept()


def _small(font: QFont, *, bold: bool = False) -> QFont:
    smaller = QFont(font)
    smaller.setPointSizeF(max(font.pointSizeF() - 2, 6.0))
    smaller.setBold(bold)
    return smaller
