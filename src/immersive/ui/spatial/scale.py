"""How the top and front views turn metres into pixels, and back (D-143).

One scale is shared by both ortho views, as one `TimeAxis` is shared by
everything drawn against timeline time (D-94). It holds how many metres a
view shows across its shorter side, and the metre of X at the views'
centre, which both views read, so a zoom or a sideways pan in either moves
both. Each view keeps its own vertical centre: Y in the top view, Z in the
front view, which are different axes.

Within a view a metre is as many pixels across as up, and screen-right is
+X in both views (03, *Coordinate system*). Up-screen is +Y in the top view
and +Z in the front view, and a pixel's y grows downwards, so the vertical
is turned over here and nowhere else.

**Qt-free**, like `TimeAxis`: the arithmetic is where a zoom creeping away
from the pointer would be, and it is found here in milliseconds, with no
window.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Literal

#: Which view a vertical centre is: the top view's is Y, the front's Z.
Plane = Literal["top", "front"]

#: What a view shows across its shorter side at first, and the closest and
#: widest a zoom goes, metres.
FIRST_SPAN: Final = 8.0
NARROWEST: Final = 2.0
WIDEST: Final = 200.0


def _clamped(span: float) -> float:
    return min(max(span, NARROWEST), WIDEST)


class Scale:
    """The metres across both views, the X at their centre, and each view's
    vertical centre."""

    def __init__(self) -> None:
        self._span = FIRST_SPAN
        self._x = 0.0
        self._centres: dict[Plane, float] = {"top": 0.0, "front": 0.0}
        self._observers: list[Callable[[], None]] = []

    # ------------------------------------------------------------- reading

    @property
    def span(self) -> float:
        """Metres across a view's shorter side."""
        return self._span

    @property
    def x(self) -> float:
        """The metre of X at the views' centre."""
        return self._x

    def centre(self, plane: Plane) -> float:
        """The metre of the view's vertical axis at its centre."""
        return self._centres[plane]

    def per_metre(self, width: float, height: float) -> float:
        """Pixels a metre, across and up alike, in a view of that size."""
        return max(min(width, height), 1.0) / self._span

    def pixel(
        self, plane: Plane, width: float, height: float, across: float, up: float
    ) -> tuple[float, float]:
        """Where the metres `across` (X) and `up` (Y or Z) are in the view."""
        scale = self.per_metre(width, height)
        return (
            width / 2 + (across - self._x) * scale,
            height / 2 - (up - self._centres[plane]) * scale,
        )

    def metres(
        self, plane: Plane, width: float, height: float, x: float, y: float
    ) -> tuple[float, float]:
        """The metres across and up at pixel `(x, y)` of the view."""
        scale = self.per_metre(width, height)
        return (
            self._x + (x - width / 2) / scale,
            self._centres[plane] - (y - height / 2) / scale,
        )

    # ------------------------------------------------------------ changing

    def zoom_about(
        self,
        plane: Plane,
        width: float,
        height: float,
        x: float,
        y: float,
        factor: float,
    ) -> None:
        """Show `factor` times as many metres, keeping the metre at pixel
        `(x, y)` of that view where it is. Greater than one zooms out."""
        across, up = self.metres(plane, width, height, x, y)
        span = _clamped(self._span * factor)
        scale = max(min(width, height), 1.0) / span
        centres = dict(self._centres)
        centres[plane] = up + (y - height / 2) / scale
        self._set(span, across - (x - width / 2) / scale, centres)

    def pan(
        self, plane: Plane, width: float, height: float, dx: float, dy: float
    ) -> None:
        """Move what a view shows with the pointer, by `(dx, dy)` pixels:
        sideways for both views, up and down for this one alone."""
        scale = self.per_metre(width, height)
        centres = dict(self._centres)
        centres[plane] = self._centres[plane] + dy / scale
        self._set(self._span, self._x - dx / scale, centres)

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` after anything here changes; a change that
        changes nothing calls nobody."""
        self._observers.append(callback)

    def _set(self, span: float, x: float, centres: dict[Plane, float]) -> None:
        if (span, x, centres) == (self._span, self._x, self._centres):
            return
        self._span, self._x, self._centres = span, x, centres
        for callback in list(self._observers):
            callback()
