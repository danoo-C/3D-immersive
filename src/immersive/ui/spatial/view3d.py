"""The 3D view (04, *3D view — read-only*; D-49, D-148).

The scene from a fixed camera, drawn with `QPainter` under an orthographic
projection. It is for reading the scene at a glance and for screen
recordings, so it has no controls and takes no mouse input: nothing in it
can be knocked out of place mid-take.

**The camera** (D-148) is a true isometric: a metre along X, Y or Z is the
same length on screen, so a height reads like a distance on the ground. It
is behind the listener, as the front view's is, and to their left. Their
right goes up and to the right, their front up and to the left, and up is
up. The head stays at the centre, and the ground about it runs from -R to
+R metres, R the smallest of `HALF_SIZES` holding every placed source, so
the view rescales only when a source crosses a step. Up and down, it fits
the ground's diamond, or the source farthest up or down the screen, again
in steps.

**What is drawn**, back to front: the ground grid at ear level, Z = 0,
with a *front* label; each source's drop line to its point on the ground,
which is what shows its height; each pair's line; the head and every icon,
farthest from the camera first, so a nearer one covers a farther one and
the head covers what is behind it; and the selected channels' rings last,
over everything. Icons follow the ortho views' rules (D-146). A bypassed
channel is not drawn (D-36).
"""

from __future__ import annotations

import math
from typing import Final

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from immersive.core.document import Document
from immersive.core.model import Position, audible, paired, sides
from immersive.ui.spatial import look
from immersive.ui.spatial.ortho_view import (
    HEAD,
    RING,
    RING_GAP,
    Icon,
    draw_icon,
    small_font,
)
from immersive.ui.spatial.placing import Placing
from immersive.ui.theme import channel_group_color, group_color

COS_30: Final = math.cos(math.radians(30.0))
SIN_30: Final = 0.5

#: How far the ground runs from the head, metres: the smallest that holds
#: every placed source in X, Y and Z.
HALF_SIZES: Final = (2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0)

#: How far up or down the screen the scene is drawn, as a part of R: the
#: ground's own diamond, or higher in steps for the sources above it.
REACH_STEPS: Final = (1.0, 1.25, 1.5, 1.75, 2.0)

#: Metres between the grid's lines: the smallest leaving at most
#: `GRID_LINES` a side.
GRID_STEPS: Final = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
GRID_LINES: Final = 8

#: Room around the scene, and the dot where a drop line meets the ground,
#: pixels.
MARGIN: Final = 24.0
FOOT: Final = 2.5


class View3D(QWidget):
    """The scene from a fixed isometric camera; read-only."""

    def __init__(
        self,
        document: Document,
        placing: Placing | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("View3D")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumSize(160, 160)
        self._document = document
        self._placing = placing if placing is not None else Placing()
        document.observe(self.update)
        document.selection.observe(self.update)
        self._placing.observe(self.update)

    def retheme(self) -> None:
        """A theme switch: the colours are read when it paints."""
        self.update()

    # ------------------------------------------------------------ geometry

    def half_size(self) -> float:
        """R: how far the ground runs from the head, metres."""
        farthest = max(
            (max(abs(where.x), abs(where.y), abs(where.z)) for where in self._placed()),
            default=0.0,
        )
        return next((r for r in HALF_SIZES if farthest <= r), HALF_SIZES[-1])

    def reach(self) -> float:
        """How far above or below the head the scene is drawn, metres of
        screen: the ground's diamond, R, or the source farthest up or down
        the screen, in steps of a quarter of R so the view holds still."""
        half = self.half_size()
        tallest = max(
            (abs(SIN_30 * (where.x + where.y) + where.z) for where in self._placed()),
            default=0.0,
        )
        return next(
            (half * k for k in REACH_STEPS if tallest <= half * k),
            half * REACH_STEPS[-1],
        )

    def per_metre(self) -> float:
        """Pixels a metre, along any axis: the ground's diamond across, and
        `reach()` up and down, inside the margin."""
        across = (self.width() / 2 - MARGIN) / (2 * self.half_size() * COS_30)
        up = (self.height() / 2 - MARGIN) / self.reach()
        return max(min(across, up), 0.0)

    def point_of(self, position: Position) -> QPointF:
        """Where `position` is drawn."""
        per = self.per_metre()
        return QPointF(
            self.width() / 2 + per * COS_30 * (position.x - position.y),
            self.height() / 2 - per * (SIN_30 * (position.x + position.y) + position.z),
        )

    def icons(self) -> list[Icon]:
        """Every icon, in the order it is drawn: farthest first."""
        return [icon for _, icon in sorted(self._icons(), key=lambda item: item[0])]

    # ------------------------------------------------------------- drawing

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(group_color("spatial", "background")))
        self._draw_grid(painter)
        icons = self._icons()
        self._draw_drops(painter, icons)
        self._draw_pairs(painter, [icon for _, icon in icons])
        head_drawn = False
        for near, icon in sorted(icons, key=lambda item: item[0]):
            if not head_drawn and near > 0.0:
                self._draw_head(painter)
                head_drawn = True
            draw_icon(painter, icon)
        if not head_drawn:
            self._draw_head(painter)
        selection = self._document.selection
        painter.setPen(QPen(QColor(group_color("spatial", "selected")), RING))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for _, icon in icons:
            if icon.channel in selection:
                around = icon.radius + RING_GAP
                painter.drawEllipse(icon.centre, around, around)
        painter.end()

    def _draw_grid(self, painter: QPainter) -> None:
        """The ground at ear level: a line every step, and *front* at its
        front edge."""
        half = self.half_size()
        step = next((s for s in GRID_STEPS if half / s <= GRID_LINES), GRID_STEPS[-1])
        painter.setPen(QPen(QColor(group_color("spatial", "grid")), 1.0))
        lines = int(half // step)
        for n in range(-lines, lines + 1):
            at = n * step
            painter.drawLine(
                self.point_of(Position(at, -half, 0.0)),
                self.point_of(Position(at, half, 0.0)),
            )
            painter.drawLine(
                self.point_of(Position(-half, at, 0.0)),
                self.point_of(Position(half, at, 0.0)),
            )
        painter.setPen(QColor(group_color("spatial", "ring.label")))
        painter.setFont(small_font(painter.font()))
        edge = self.point_of(Position(0.0, half, 0.0))
        painter.drawText(QPointF(edge.x() - 30, edge.y() - 4), "front")

    def _draw_drops(self, painter: QPainter, icons: list[tuple[float, Icon]]) -> None:
        """Each source's line to its point on the ground, and a dot there:
        its height, and whether it is ahead and high or behind and low."""
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for _, icon in icons:
            where = icon.position
            if where is None or abs(where.z) * self.per_metre() <= icon.radius:
                continue  # at ear level: the icon covers its own foot
            foot = self.point_of(Position(where.x, where.y, 0.0))
            colour = QColor(channel_group_color("spatial", "icon", icon.channel.color))
            painter.setOpacity(icon.opacity * 0.6)
            painter.setPen(QPen(colour, 1.0))
            painter.drawLine(icon.centre, foot)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(foot, FOOT, FOOT)
        painter.setOpacity(1.0)

    def _draw_pairs(self, painter: QPainter, icons: list[Icon]) -> None:
        """The line joining each pair's two sides."""
        left: dict[str, Icon] = {}
        for icon in icons:
            if icon.side == 0:
                left[icon.channel.id] = icon
        for icon in icons:
            if icon.side == 1 and icon.channel.id in left:
                colour = channel_group_color("spatial", "pair", icon.channel.color)
                painter.setOpacity(icon.opacity)
                painter.setPen(QPen(QColor(colour), 1.5))
                painter.drawLine(left[icon.channel.id].centre, icon.centre)
        painter.setOpacity(1.0)

    def _draw_head(self, painter: QPainter) -> None:
        """The listener at the origin: the head, the far ear behind it and
        the near one before it, and the nose toward their front."""
        centre = self.point_of(Position())
        right = QPointF(COS_30, -SIN_30)  # +X on screen, a unit
        front = QPointF(-COS_30, -SIN_30)  # +Y on screen, a unit
        painter.setPen(QPen(QColor(group_color("spatial", "head")), 1.5))
        painter.setBrush(QColor(group_color("spatial", "head.fill")))
        painter.drawEllipse(centre + right * HEAD, HEAD / 4, HEAD / 3)
        painter.drawEllipse(centre, HEAD, HEAD)
        painter.drawEllipse(centre - right * HEAD, HEAD / 4, HEAD / 3)
        tip = centre + front * (HEAD * 1.5)
        side = QPointF(-front.y(), front.x()) * (HEAD / 3)
        base = centre + front * (HEAD - 1)
        nose = QPainterPath()
        nose.addPolygon(QPolygonF([base - side, tip, base + side]))
        painter.drawPath(nose)

    # ------------------------------------------------------------ internal

    def _placed(self) -> list[Position]:
        """Where every placed side is, a drag's placing first."""
        project = self._document.project
        made: list[Position] = []
        for channel in project.channels:
            if channel.hrtf_bypass:
                continue
            placed = self._placing.sides(channel) or sides(channel)
            made += placed if paired(project, channel) else placed[:1]
        return made

    def _icons(self) -> list[tuple[float, Icon]]:
        """Every icon with its nearness to the camera, in channel order."""
        project = self._document.project
        heard = audible(project.channels)
        made: list[tuple[float, Icon]] = []
        for channel, is_heard in zip(project.channels, heard, strict=True):
            if channel.hrtf_bypass:
                continue
            placed = self._placing.sides(channel) or sides(channel)
            strength = look.opacity(channel.gain_db, heard=is_heard)
            each = [(0, placed[0]), (1, placed[1])]
            for side, where in each if paired(project, channel) else [(-1, placed[0])]:
                icon = Icon(
                    channel,
                    side,
                    self.point_of(where),
                    look.radius(where),
                    strength,
                    channel.solo,
                    where,
                )
                made.append((nearness(where), icon))
        return made


def nearness(position: Position) -> float:
    """How near the camera `position` is, along its direction: the larger,
    the nearer. The head's is 0."""
    return position.z - position.x - position.y
