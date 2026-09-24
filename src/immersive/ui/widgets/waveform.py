"""A sample's peaks, drawn at whatever width the widget is given.

One lane per channel and one vertical stroke per pixel column, from the
column's lowest sample to its highest. The media pool's thumbnail now, the
inside of a clip at M3 and the parameters pane's full waveform after that.

**Colours are read when it paints** (D-76), from the `waveform` group, which
is a painted group rather than a stylesheet one (D-92). Nothing is baked in,
so a theme change has nothing to invalidate; `retheme()` exists only so
D-82's walk reaches it and asks for the repaint.

**The level is chosen from the width.** The coarsest level whose bucket fits
in one pixel column gives at least one bucket per column and, the next level
being four times coarser, fewer than four - so painting costs the widget's
width, never the sample's length.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from immersive.core.io.peaks import Level, Pyramid
from immersive.ui import theme

#: What a sample whose file has gone says, beside being drawn in `warn` -
#: missing media is never shown by colour alone (04, *Accessibility and feel*).
MISSING_TEXT = "⚠ missing"


def level_for(pyramid: Pyramid, width: int) -> Level:
    """The coarsest level with at least one bucket per pixel column."""
    per_column = pyramid.frames / max(width, 1)
    chosen = pyramid.levels[0]
    for level in pyramid.levels:
        if level.bucket <= per_column:
            chosen = level
    return chosen


def envelope(
    pyramid: Pyramid, width: int
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Each column's lowest and highest sample, `(width, channels)` each.

    One `reduceat` per bound over the chosen level. A column narrower than a
    bucket - a short sample in a wide widget - repeats the bucket it falls
    in rather than leaving a gap.
    """
    level = level_for(pyramid, width)
    columns = np.arange(width, dtype=np.int64)
    starts = (columns * pyramid.frames) // (width * level.bucket)
    starts = np.minimum(starts, level.buckets - 1)
    lows = np.minimum.reduceat(level.low, starts, axis=0)
    highs = np.maximum.reduceat(level.high, starts, axis=0)
    # reduceat with a repeated start returns that single row, and with the
    # next start earlier-or-equal it returns the row at the start: both are
    # the bucket the column falls in, which is what is wanted.
    return lows, highs


class Waveform(QWidget):
    """Peaks, or the reason there are none."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pyramid: Pyramid | None = None
        self._missing = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(12)

    def set_peaks(self, pyramid: Pyramid | None, *, missing: bool = False) -> None:
        """What to draw. `None` and not missing: nothing yet, just the ground."""
        self._pyramid = pyramid
        self._missing = missing
        self.update()

    def retheme(self) -> None:
        """Nothing to re-read - colours are read at paint time - so repaint."""
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            self._paint(painter, self.rect())
        finally:
            painter.end()

    def _paint(self, painter: QPainter, area: QRect) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        ground = QColor(theme.group_color("waveform", "background"))
        painter.fillRect(area, ground)

        if self._missing:
            warn = QColor(theme.group_color("waveform", "missing"))
            row = area.top() + area.height() // 2
            painter.setPen(QPen(warn, 1, Qt.PenStyle.DashLine))
            painter.drawLine(area.left(), row, area.right(), row)
            # The words sit on a patch of background, not across the line:
            # they are what makes this readable without colour, so the line
            # must not run through them.
            words = painter.boundingRect(
                area, Qt.AlignmentFlag.AlignCenter, MISSING_TEXT
            ).adjusted(-4, 0, 4, 0)
            painter.fillRect(words, ground)
            painter.setPen(warn)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, MISSING_TEXT)
            return

        pyramid = self._pyramid
        if pyramid is None or area.width() <= 0:
            return

        lows, highs = envelope(pyramid, area.width())
        lane_height = area.height() / pyramid.channels
        centre = QColor(theme.group_color("waveform", "centre"))
        fill = QColor(theme.group_color("waveform", "fill"))
        for channel in range(pyramid.channels):
            top = area.top() + round(channel * lane_height)
            bottom = area.top() + round((channel + 1) * lane_height) - 1
            middle = (top + bottom) / 2
            half = (bottom - top) / 2
            painter.setPen(centre)
            painter.drawLine(area.left(), round(middle), area.right(), round(middle))
            painter.setPen(fill)
            # Overs are drawn to the lane's edge and no further: a float
            # sample above full scale must not paint into the next channel.
            high = np.clip(highs[:, channel], -1.0, 1.0)
            low = np.clip(lows[:, channel], -1.0, 1.0)
            for x in range(area.width()):
                y_high = round(middle - high[x] * half)
                y_low = round(middle - low[x] * half)
                painter.drawLine(area.left() + x, y_high, area.left() + x, y_low)
