"""A source being dragged: where it would be if the drag ended now (D-144).

While a drag lasts, the model is left alone. `Placing` holds the channel
being dragged and its two sides as they would be. The views draw that
channel from it, the pane's fields show it, and the feed sends it to the
engine, so the drag is heard as it goes. Its release is `end()`, which
gives back the one edit the drag makes. Esc is `cancel()`, which gives
back nothing.

**The side grabbed leads (D-145).** A channel's one point moves as dragged.
A linked pair's other side follows in its mirror about the pivot, and the
edit stores the left side, the mirror of the right, since the mirror is its
own inverse (D-132). A free pair's side moves alone. These are the edits
the pane makes for a typed side.

Qt-free: plain callbacks, as `Scale` and `TimeAxis` have.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from immersive.core.commands import Command
from immersive.core.edits import SetAttribute
from immersive.core.model import Channel, Pairing, Position, mirror, sides

#: Which of a channel is grabbed: its one point, or a pair's left or right.
POINT, LEFT, RIGHT = -1, 0, 1


class Placing:
    """The channel being dragged, the side grabbed, and its sides as they
    would be now; or nothing, between drags."""

    def __init__(self) -> None:
        self._channel: Channel | None = None
        self._side = POINT
        self._sides: tuple[Position, Position] | None = None
        self._observers: list[Callable[[], None]] = []

    # ------------------------------------------------------------- reading

    @property
    def channel(self) -> Channel | None:
        """The channel being dragged, or None."""
        return self._channel

    @property
    def side(self) -> int:
        return self._side

    def sides(self, channel: Channel) -> tuple[Position, Position] | None:
        """`channel`'s left and right sides as the drag has them, or None
        when it is not the channel being dragged."""
        return self._sides if channel is self._channel else None

    # ------------------------------------------------------------ changing

    def begin(self, channel: Channel, side: int) -> None:
        """Start dragging `side` of `channel`, from where it is."""
        self._channel, self._side = channel, side
        self._sides = sides(channel)
        self._tell()

    def move(self, grabbed: Position) -> None:
        """The grabbed side is now at `grabbed`; the other follows."""
        channel = self._channel
        if channel is None:
            return
        placement = channel.placement
        left, right = sides(channel)
        if self._side == POINT:
            left = right = grabbed
        elif placement.mode is Pairing.LINKED:
            other = mirror(grabbed, placement.pivot, placement.mirrored)
            left, right = (grabbed, other) if self._side == LEFT else (other, grabbed)
        elif self._side == LEFT:
            left = grabbed
        else:
            right = grabbed
        if (left, right) != self._sides:
            self._sides = (left, right)
            self._tell()

    def end(self) -> Command | None:
        """The drag released: the one edit it makes, or None when it moved
        nothing. Nothing is being placed after."""
        channel, placed, side = self._channel, self._sides, self._side
        self._clear()
        if channel is None or placed is None or placed == sides(channel):
            return None
        left, right = placed
        placement = channel.placement
        if side == RIGHT and placement.mode is Pairing.FREE:
            return SetAttribute(channel, "placement", replace(placement, right=right))
        return SetAttribute(channel, "position", left)

    def cancel(self) -> None:
        """Esc: nothing placed, and no edit."""
        self._clear()

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` whenever what is placed changes, and when a drag
        ends or is cancelled."""
        self._observers.append(callback)

    # ------------------------------------------------------------ internal

    def _clear(self) -> None:
        if self._channel is None:
            return
        self._channel, self._side, self._sides = None, POINT, None
        self._tell()

    def _tell(self) -> None:
        for callback in list(self._observers):
            callback()
