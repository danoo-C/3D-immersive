"""Where a drag on clips in the lanes lands: which part of a clip a press
took, and where the edge under the pointer snaps to.

Qt-free, like `landing.py` for a drop from the pool: the view reads a press
and a movement off the mouse, and everything about what they mean is here,
tested without a window. What the edit then does to the project - how far
it may go, what it overwrites - is the command's (D-97, D-98).

- **A press** takes a clip's start or end within `EDGE` pixels of it, and
  its body elsewhere. A zone is at most a third of the clip, so a narrow
  clip can still be moved.
- **A trim** snaps the edge being dragged.
- **A move** snaps the grabbed clip's start to the grid and to clip edges,
  or its end to clip edges, whichever is nearer: a clip can be butted
  against a neighbour from either side, and a clip whose length is not a
  whole number of grid steps is not pulled off the grid by its end.
- **The setting** is the channel's the edge lands in (F-18) - for a move to
  another lane, that lane's - or none while `Alt` is held.
- **The dragged edges are not targets.** Their own positions would pin
  every small drag to where it began.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Sequence
from enum import StrEnum

from immersive.core.edits import Edge
from immersive.core.model import Channel, Clip, Project, effective_snap
from immersive.core.time import snap
from immersive.ui.timeline.metrics import LANE_HEIGHT

#: How near a clip's end, in pixels, a press takes that end.
EDGE = 6


class Part(StrEnum):
    """What a press on a clip takes."""

    BODY = "body"
    START = "start"
    END = "end"

    @property
    def edge(self) -> Edge | None:
        """The end a trim from this part moves; `None` for the body."""
        return {Part.START: Edge.START, Part.END: Edge.END}.get(self)


def part_at(x: float, width: float) -> Part:
    """The part of a clip `width` pixels wide that a press `x` pixels into
    it takes."""
    zone = min(EDGE, width / 3)
    if x < zone:
        return Part.START
    if x >= width - zone:
        return Part.END
    return Part.BODY


def lanes_moved(pressed_y: float, y: float) -> int:
    """How many lanes a drag from `pressed_y` to `y` has crossed, down
    positive."""
    return int(y // LANE_HEIGHT) - int(pressed_y // LANE_HEIGHT)


def targets(
    project: Project, dragged: Iterable[Clip], edge: Edge | None = None
) -> list[int]:
    """Every clip edge a drag may snap to, sorted: all of them but the ones
    being dragged - both edges of a moved clip, or the one edge a trim
    moves. Gathered once when a drag begins."""
    left_out = {id(clip) for clip in dragged}
    found: set[int] = set()
    for channel in project.channels:
        for clip in channel.clips:
            if id(clip) not in left_out:
                found.update((clip.start, clip.end))
            elif edge is Edge.START:
                found.add(clip.end)
            elif edge is Edge.END:
                found.add(clip.start)
    return sorted(found)


def snapped_move(
    project: Project,
    grabbed: Clip,
    home: int,
    delta: int,
    lanes: int,
    edges: Sequence[int],
    *,
    exact: bool = False,
) -> int:
    """The time offset a move of the selection by `delta` samples and
    `lanes` lanes takes, once the grabbed clip - on lane `home` - has
    snapped as the module says."""
    channels = project.channels
    lane = min(max(home + lanes, 0), len(channels) - 1)
    setting = effective_snap(project, channels[lane])
    if exact or not setting.enabled:
        return delta
    start = grabbed.start + delta
    by_start = (
        snap(
            start,
            bpm=project.bpm,
            time_signature=project.time_signature,
            division=setting.division,
            triplet=setting.triplet,
            edges=edges,
        )
        - start
    )
    end = grabbed.end + delta
    nearest = _nearest(edges, end)
    by_end = nearest - end if nearest is not None else None
    if by_end is not None and abs(by_end) < abs(by_start):
        return delta + by_end
    return delta + by_start


def snapped_trim(
    project: Project,
    clip: Clip,
    channel: Channel,
    edge: Edge,
    delta: int,
    edges: Sequence[int],
    *,
    exact: bool = False,
) -> int:
    """The offset a trim of `clip`'s `edge` by `delta` samples takes once
    that edge has snapped by `channel`'s setting."""
    setting = effective_snap(project, channel)
    if exact or not setting.enabled:
        return delta
    before = clip.start if edge is Edge.START else clip.end
    return (
        snap(
            before + delta,
            bpm=project.bpm,
            time_signature=project.time_signature,
            division=setting.division,
            triplet=setting.triplet,
            edges=edges,
        )
        - before
    )


def _nearest(edges: Sequence[int], sample: int) -> int | None:
    """The edge nearest `sample`, the later on a tie; `None` for none."""
    index = bisect.bisect_left(edges, sample)
    around = edges[max(index - 1, 0) : index + 1]
    if not around:
        return None
    return min(around, key=lambda edge: (abs(edge - sample), -edge))
