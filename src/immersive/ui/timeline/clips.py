"""A clip in its lane: its body, its name, and its part of its sample.

One `QGraphicsItem` per clip, placed and sized by the view from the shared
time axis, and painted from what it was last shown: the clip, its channel's
colour, its sample's name, whether that sample is missing, and the session's
peaks for it. Nothing about where clips go is decided here - that is
`DropClips` and, from phase 5, the edits.

**Cached by Qt, per device pixel.** `DeviceCoordinateCache` keeps what the
clip last painted and reuses it as the view scrolls; a zoom changes the
item's geometry and so its cache, and `present` asks for a repaint only when
something the clip draws has changed. Qt's cache is as large as the view,
not as the item, which matters for an hour-long clip at a close zoom.

⚠️ **The first paint is told the whole item is exposed**, even when only
the view's width of it is on the painter's device. So the painted part is
what is exposed *and* lands on the device, mapped back into the item: an
exposed rectangle taken at its word would walk millions of columns of an
hour-long clip to draw eight hundred of them.

**Colours are read when it paints** (D-92), from the `clip` group. `body`
and `waveform` are `channel` in the built-in theme, resolved against the
channel's own colour, which is what keeps 04's colour thread whole.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from immersive.core.io.peaks import Pyramid
from immersive.core.model import Clip
from immersive.ui import theme
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.widgets.waveform import MISSING_TEXT, paint_envelope

#: A clip fills its lane but for a pixel above and the lane's line below.
TOP = 1
HEIGHT = LANE_HEIGHT - 2

#: The strip along the top that holds the name.
NAME_HEIGHT = 16

#: Narrower than this, a clip is its body alone: a waveform squeezed into a
#: few columns says nothing, and costs as much to draw as a wide one.
MIN_WAVEFORM = 8

#: Narrower than this, it has no name either - not even an ellipsis fits.
MIN_NAME = 24

#: How much of the channel's colour the body is, over its lane. The
#: waveform, drawn solid over it, is what stands out.
BODY_ALPHA = 0.35

#: A selected clip's border, drawn inside its edges: a shape as well as a
#: colour, so a selection is never shown by colour alone.
SELECTED_BORDER = 2

#: Where a sample's peaks come from: the session's store, by media id.
Peaks = Callable[[str], Pyramid | None]


class ClipItem(QGraphicsItem):
    """One clip, as its lane shows it."""

    def __init__(self, peaks: Peaks) -> None:
        super().__init__()
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self._peaks = peaks
        self.clip: Clip | None = None
        self._width = 1.0
        self._look: tuple[object, ...] = ()
        #: The lane it was last shown in: its channel's index.
        self.lane = 0
        #: How many times it has painted - read by tests of the cache.
        self.paints = 0

    def present(
        self,
        clip: Clip,
        *,
        colour: str,
        name: str,
        missing: bool,
        lane: int,
        scale: float,
        selected: bool = False,
    ) -> None:
        """Place and size it for `scale`, and repaint only if its look changed."""
        self.clip = clip
        width = max(clip.length / scale, 1.0)
        if width != self._width:
            self.prepareGeometryChange()
            self._width = width
        self.setPos(clip.start / scale, lane * LANE_HEIGHT + TOP)
        self.lane = lane
        look = (
            clip.media_id,
            clip.offset,
            clip.length,
            colour,
            name,
            missing,
            selected,
        )
        if look != self._look:
            self._look = look
            self.update()

    @property
    def colour(self) -> str:
        return str(self._look[3]) if self._look else ""

    @property
    def name(self) -> str:
        return str(self._look[4]) if self._look else ""

    @property
    def missing(self) -> bool:
        return bool(self._look[5]) if self._look else False

    @property
    def selected(self) -> bool:
        return bool(self._look[6]) if self._look else False

    @property
    def shows_waveform(self) -> bool:
        """Wide enough for a waveform, and with a sample to draw it from."""
        return not self.missing and self._width >= MIN_WAVEFORM

    @property
    def shows_name(self) -> bool:
        return self._width >= MIN_NAME

    def label(self) -> str:
        """What its name strip says: missing in words, never by colour alone."""
        return f"{MISSING_TEXT}  {self.name}" if self.missing else self.name

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, HEIGHT)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        self.paints += 1
        clip = self.clip
        if clip is None:
            return
        # See the module's warning: exposed, and on the device.
        device = painter.device()
        inverse, _ = painter.worldTransform().inverted()
        on_device = inverse.mapRect(QRectF(0, 0, device.width(), device.height()))
        drawn = option.exposedRect.intersected(on_device).intersected(
            self.boundingRect()
        )
        if drawn.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self.missing:
            body = QColor(theme.group_color("clip", "missing"))
        else:
            body = QColor(theme.channel_group_color("clip", "body", self.colour))
        edge = QColor(body)
        body.setAlphaF(BODY_ALPHA)
        painter.fillRect(drawn, body)
        # Its own colour, solid, down each end: where one clip stops and the
        # next begins, when they touch.
        painter.setPen(edge)
        right = math.ceil(self._width) - 1
        painter.drawLine(0, 0, 0, HEIGHT - 1)
        painter.drawLine(right, 0, right, HEIGHT - 1)

        width = int(self._width)
        pyramid = self._peaks(clip.media_id) if self.shows_waveform else None
        if pyramid is not None:
            first = max(int(drawn.left()), 0)
            last = min(math.ceil(drawn.right()), width)
            paint_envelope(
                painter,
                QRect(0, NAME_HEIGHT, width, HEIGHT - NAME_HEIGHT - 2),
                pyramid,
                fill=QColor(theme.channel_group_color("clip", "waveform", self.colour)),
                centre=None,
                start=clip.offset,
                frames=clip.length,
                columns=range(first, last),
            )

        if self.selected:
            pen = QPen(QColor(theme.group_color("clip", "selected.border")))
            pen.setWidth(SELECTED_BORDER)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = SELECTED_BORDER / 2
            painter.drawRect(
                QRectF(
                    inset,
                    inset,
                    self._width - SELECTED_BORDER,
                    HEIGHT - SELECTED_BORDER,
                )
            )

        if self.shows_name:
            room = QRect(4, 1, width - 8, NAME_HEIGHT - 1)
            text = painter.fontMetrics().elidedText(
                self.label(), Qt.TextElideMode.ElideRight, room.width()
            )
            # An ellipsis and nothing else says nothing; leave the strip empty.
            if text.strip("…"):
                painter.setPen(QColor(theme.group_color("clip", "text")))
                painter.drawText(
                    room,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
