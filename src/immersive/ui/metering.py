"""How a meter moves (D-118), without Qt.

A meter is fed the highest sample per side since the last frame - linear,
as the engine publishes it - thirty times a second, and shows:

- **the bar**, which rises at once and falls at `FALL` dB a second, so a
  transient shows the moment it happens and can still be read;
- **the hold**, the highest level for `HOLD` seconds, then falling at the
  same rate, never below the bar;
- **the clip latch**, set by a sample past full scale - above 1.0, not at
  it - and cleared only by `clear()`, which is the click on the master's
  light. A channel meter never reads it (D-117).

Levels are dBFS, floored at `FLOOR`. The clock is passed in, so a test steps
time rather than waiting for it. `ui/widgets/meter.py` draws this.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Final

#: The bottom of the scale, dBFS: below it a stem is lost under anything else.
FLOOR: Final = -60.0

#: Where headroom starts running out: the bar is drawn `meter.hot` above it.
HOT: Final = -6.0

#: How fast a bar, and a hold once it lets go, falls: dB a second.
FALL: Final = 24.0

#: How long the highest level is held, in seconds (F-54, 04).
HOLD: Final = 1.5

#: Full scale. A float bus carries more; a converter does not.
FULL_SCALE: Final = 1.0


def to_db(linear: float) -> float:
    """A sample's size as dBFS, no lower than `FLOOR`."""
    if linear <= 0.0:
        return FLOOR
    return max(20.0 * math.log10(linear), FLOOR)


def along(db: float) -> float:
    """Where `db` is on the scale, 0 at `FLOOR` to 1 at full scale."""
    return min(max((db - FLOOR) / -FLOOR, 0.0), 1.0)


class Ballistics:
    """Two sides' bars and holds, and the clip latch."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last = clock()
        self.levels = [FLOOR, FLOOR]
        self.holds = [FLOOR, FLOOR]
        self._held_until = [self._last, self._last]
        self.clipped = False

    def feed(self, left: float, right: float) -> bool:
        """One frame's peaks. Whether anything a meter shows has moved."""
        now = self._clock()
        elapsed = max(now - self._last, 0.0)
        self._last = now
        before = (*self.levels, *self.holds, self.clipped)
        for side, peak in enumerate((left, right)):
            if peak > FULL_SCALE:
                self.clipped = True
            db = to_db(peak)
            self.levels[side] = max(db, self.levels[side] - FALL * elapsed, FLOOR)
            if db >= self.holds[side]:
                self.holds[side] = db
                self._held_until[side] = now + HOLD
            elif now > self._held_until[side]:
                falling = now - max(self._held_until[side], now - elapsed)
                self.holds[side] = self.holds[side] - FALL * falling
            self.holds[side] = max(self.holds[side], self.levels[side], FLOOR)
        return (*self.levels, *self.holds, self.clipped) != before

    def clear(self) -> None:
        """The click on the master's clip light."""
        self.clipped = False
