"""Which span of the timeline is visible, and at what zoom (D-94).

One axis is shared by everything drawn against timeline time - the timeline
now, the curve editor at M6 - and none of them owns it. Each observes it and
draws what it says, which is the risk register's answer to the two drifting
apart (06-roadmap.md).

**Qt-free**, like the theme modules, because the arithmetic is where the bugs
would be: a zoom that creeps away from the cursor or a click that lands a
sample off is found here in milliseconds, with no window.

**The scroll offset is whole pixels, not samples.** `QGraphicsView` scrolls
in whole pixels, so a scene's x is `sample / scale` and the view's scrollbar
value is exactly `offset`. An offset in fractional samples would leave the
ruler - drawn from this - and the lanes - scrolled by the view - a fraction
of a pixel apart, with nothing to say which was right. What it costs is that
`zoom_about` holds its point to within half a pixel rather than exactly.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

from immersive.core.time import SAMPLE_RATE

#: The closest zoom: one sample per pixel. Closer would draw each sample
#: wider than a pixel and show nothing new.
MIN_SCALE: Final = 1.0

#: The widest: a minute per pixel, so an hour fits in sixty.
MAX_SCALE: Final = float(SAMPLE_RATE * 60)

#: Where a new axis starts: a hundred pixels a second.
DEFAULT_SCALE: Final = SAMPLE_RATE / 100


def _clamped(scale: float) -> float:
    return min(max(scale, MIN_SCALE), MAX_SCALE)


class TimeAxis:
    """A scale, a scroll offset, and the span they make visible."""

    def __init__(
        self, scale: float = DEFAULT_SCALE, *, width: int = 0, extent: float = 0
    ) -> None:
        self._scale = _clamped(scale)
        self._offset = 0
        self._width = max(width, 0)
        self._extent = max(extent, 0.0)
        self._observers: list[Callable[[], None]] = []

    # ------------------------------------------------------------- reading

    @property
    def scale(self) -> float:
        """Samples per pixel."""
        return self._scale

    @property
    def offset(self) -> int:
        """Pixels scrolled past the timeline's start, at the current scale."""
        return self._offset

    @property
    def width(self) -> int:
        """Pixels of timeline on show."""
        return self._width

    @property
    def extent(self) -> float:
        """The last sample the axis can be scrolled to show."""
        return self._extent

    def x_of(self, sample: float) -> float:
        """Where `sample` is, in pixels from the left of what is on show."""
        return sample / self._scale - self._offset

    def sample_at(self, x: float) -> float:
        """The sample at `x` pixels from the left of what is on show."""
        return (x + self._offset) * self._scale

    def visible(self) -> tuple[float, float]:
        """The first and last samples on show."""
        return self.sample_at(0), self.sample_at(self._width)

    def span(self) -> int:
        """Pixels the whole scrollable timeline takes at the current scale."""
        return self._span(self._scale)

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` after anything here changes.

        Plain callbacks, as `Document.observe` uses, so this works with no
        `QApplication`. A change that changes nothing calls nobody: a view
        repaints on every call, and mouse-moves arrive by the hundred.
        """
        self._observers.append(callback)

    # ------------------------------------------------------------ changing

    def scroll_to(self, offset: int) -> None:
        self._set(self._scale, offset)

    def scroll_by(self, pixels: int) -> None:
        self._set(self._scale, self._offset + pixels)

    def zoom_about(self, x: float, factor: float) -> None:
        """Scale by `factor`, keeping the sample at `x` where it is.

        Greater than one zooms out. The new offset is rounded to a whole
        pixel, so the sample stays within half a pixel of `x` - see the
        module's note - unless the offset had to be clamped at either end.
        """
        anchor = self.sample_at(x)
        scale = _clamped(self._scale * factor)
        self._set(scale, round(anchor / scale - x))

    def set_width(self, width: int) -> None:
        self._set(self._scale, self._offset, width=max(width, 0))

    def set_extent(self, extent: float) -> None:
        self._set(self._scale, self._offset, extent=max(extent, 0.0))

    # ------------------------------------------------------------ internal

    def _span(self, scale: float, extent: float | None = None) -> int:
        return math.ceil((self._extent if extent is None else extent) / scale)

    def _set(
        self,
        scale: float,
        offset: int,
        *,
        width: int | None = None,
        extent: float | None = None,
    ) -> None:
        """Every change comes through here, and is told once.

        The offset is clamped here, against the new width and extent, so
        narrowing the timeline's end past what is on show scrolls back rather
        than leaving the view past the end. The scale arrives clamped:
        `zoom_about` is the only thing that computes a new one, and it needs
        the clamped value to place its anchor.
        """
        width = self._width if width is None else width
        extent = self._extent if extent is None else extent
        offset = min(max(offset, 0), max(self._span(scale, extent) - width, 0))
        after = (scale, offset, width, extent)
        if after == (self._scale, self._offset, self._width, self._extent):
            return
        self._scale, self._offset, self._width, self._extent = after
        for callback in list(self._observers):
            callback()
