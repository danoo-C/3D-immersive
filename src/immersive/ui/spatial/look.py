"""What an icon says at a glance (04, *Icons and depth*; D-146).

**Radius from distance.** The distance is from the listener, in three
dimensions, so a source above the head is drawn as small as one as far
ahead: the top view tells of height that way. `RADIUS_AT_A_METRE` at 1 m,
`PER_DOUBLING` less each time the distance doubles, between `FARTHEST` and
`NEAREST`. In octaves rather than 1/d, a source at 8 m is still big enough
to click and to see its colour.

**Opacity from gain, like loudness.** Full at 0 dB and above. Below it,
the opacity falls towards `FLOOR`, its height above the floor halving
every `HALVING_DB`, which is roughly half as loud. A channel not heard -
muted, or silenced by another's solo - is `NOT_HEARD` whatever its gain,
and the floor is above it, so no gain looks muted.

Qt-free, so the 3D view reads the same rules.
"""

from __future__ import annotations

import math
from typing import Final

from immersive.core.model import Position

#: An icon's radius in pixels: at 1 m, how much less at each doubling of
#: the distance, and the limits.
RADIUS_AT_A_METRE: Final = 10.0
PER_DOUBLING: Final = 2.0
NEAREST: Final = 13.0
FARTHEST: Final = 5.0

#: An icon's opacity: the floor a quiet channel falls towards, the dB in
#: which its height above the floor halves, and a channel not heard.
FLOOR: Final = 0.4
HALVING_DB: Final = 10.0
NOT_HEARD: Final = 0.25


def radius(position: Position) -> float:
    """The radius, in pixels, of an icon at `position`."""
    distance = math.sqrt(position.x**2 + position.y**2 + position.z**2)
    if distance <= 0.0:
        return NEAREST
    return min(
        max(RADIUS_AT_A_METRE - PER_DOUBLING * math.log2(distance), FARTHEST), NEAREST
    )


def opacity(gain_db: float, *, heard: bool) -> float:
    """The opacity of a channel's icon at `gain_db`, heard or not."""
    if not heard:
        return NOT_HEARD
    if gain_db >= 0.0:
        return 1.0
    return FLOOR + (1.0 - FLOOR) * 2.0 ** (gain_db / HALVING_DB)
