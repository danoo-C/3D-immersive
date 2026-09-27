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
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from immersive.core.io.peaks import Level, Pyramid
from immersive.ui import theme

#: What a sample whose file has gone says, beside being drawn in `warn` -
#: missing media is never shown by colour alone (04, *Accessibility and feel*).
MISSING_TEXT = "⚠ missing"


def level_for(pyramid: Pyramid, width: int, frames: int | None = None) -> Level:
    """The coarsest level with at least one bucket per pixel column, when
    `frames` of the sample - all of it by default - span `width` columns."""
    per_column = (pyramid.frames if frames is None else frames) / max(width, 1)
    chosen = pyramid.levels[0]
    for level in pyramid.levels:
        if level.bucket <= per_column:
            chosen = level
    return chosen


def envelope(
    pyramid: Pyramid,
    width: int,
    *,
    start: int = 0,
    frames: int | None = None,
    columns: range | None = None,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Each column's lowest and highest sample, `(columns, channels)` each.

    `frames` of the sample from `start` - the whole of it by default - are
    spread across `width` columns, and `columns` says which of them to work
    out: a clip trimmed to its middle, of which only a strip is on screen,
    asks for that strip of that middle. A column covers the same frames
    whichever run of columns it is asked for in, so strips painted as a view
    scrolls meet without a seam.

    One `reduceat` per bound over the chosen level. A column narrower than a
    bucket - a short sample in a wide widget - repeats the bucket it falls
    in rather than leaving a gap.
    """
    frames = pyramid.frames - start if frames is None else frames
    level = level_for(pyramid, width, frames)
    wanted = range(width) if columns is None else columns
    index = np.arange(wanted.start, wanted.stop, dtype=np.int64)
    starts = (start + (index * frames) // width) // level.bucket
    starts = np.minimum(starts, level.buckets - 1)
    # Where the last column asked for ends, so it stops there rather than at
    # the end of the sample, which is where reduceat reads to past its last
    # index. Inside the range that is where the next column begins, rounded
    # as every column's start is, so a strip's last column is the whole's
    # column exactly and strips meet without a seam; at the range's own end
    # it is rounded up, to take in the partial bucket the range ends in.
    after = start + (wanted.stop * frames) // width
    end = -(-after // level.bucket) if wanted.stop >= width else after // level.bucket
    bounds = starts if end >= level.buckets else np.append(starts, end)
    lows = np.minimum.reduceat(level.low, bounds, axis=0)[: len(starts)]
    highs = np.maximum.reduceat(level.high, bounds, axis=0)[: len(starts)]
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
            paint_peaks(painter, self.rect(), self._pyramid, missing=self._missing)
        finally:
            painter.end()


def paint_peaks(
    painter: QPainter, area: QRect, pyramid: Pyramid | None, *, missing: bool = False
) -> None:
    """Draw `pyramid` into `area`, or the reason there is none.

    A function rather than only a method, so the media pool's thumbnail
    column paints with exactly this and not a copy of it.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    ground = QColor(theme.group_color("waveform", "background"))
    painter.fillRect(area, ground)

    if missing:
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

    if pyramid is None or area.width() <= 0:
        return

    paint_envelope(
        painter,
        area,
        pyramid,
        fill=QColor(theme.group_color("waveform", "fill")),
        centre=QColor(theme.group_color("waveform", "centre")),
    )


def paint_envelope(
    painter: QPainter,
    area: QRect,
    pyramid: Pyramid,
    *,
    fill: QColor,
    centre: QColor | None,
    start: int = 0,
    frames: int | None = None,
    columns: range | None = None,
) -> None:
    """Draw `frames` of `pyramid` from `start` across `area`, one lane per
    channel - or only `columns` of it, for a strip of something wider.

    The one drawing of a waveform: the pool's thumbnail, the parameters
    pane's view and a clip in its lane all come here, each with its own
    colours. `centre` of `None` draws no zero line.
    """
    wanted = range(area.width()) if columns is None else columns
    if not wanted:
        return
    lows, highs = envelope(
        pyramid, area.width(), start=start, frames=frames, columns=wanted
    )
    # The envelope is built as an image and drawn in one call. One line per
    # column in Python was a line call per pixel of every waveform on screen,
    # and five hundred clips took five times a 60 Hz frame to repaint.
    rows = area.height()
    pixels = np.zeros((rows, len(wanted)), dtype=np.uint32)
    row = np.arange(rows)[:, None]
    lane_height = rows / pyramid.channels
    for channel in range(pyramid.channels):
        top = round(channel * lane_height)
        bottom = round((channel + 1) * lane_height) - 1
        middle = (top + bottom) / 2
        half = (bottom - top) / 2
        if centre is not None:
            painter.setPen(centre)
            painter.drawLine(
                area.left() + wanted.start,
                area.top() + round(middle),
                area.left() + wanted.stop - 1,
                area.top() + round(middle),
            )
        # Overs are drawn to the lane's edge and no further: a float
        # sample above full scale must not paint into the next channel.
        high = np.round(middle - np.clip(highs[:, channel], -1.0, 1.0) * half)
        low = np.round(middle - np.clip(lows[:, channel], -1.0, 1.0) * half)
        pixels[(row >= high[None, :]) & (row <= low[None, :])] = fill.rgba()
    image = QImage(
        pixels.data, len(wanted), rows, len(wanted) * 4, QImage.Format.Format_ARGB32
    )
    # Unset pixels are transparent, so the zero line drawn first shows
    # wherever the envelope does not cover it, as it did.
    painter.drawImage(area.left() + wanted.start, area.top(), image)
