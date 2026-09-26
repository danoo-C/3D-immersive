"""What plays: a snapshot of the arrangement, and one channel's share of a
block read out of it (05, *Scheduler*).

**The snapshot is built on the UI thread and never written after** (D-105).
It holds, per channel, the clips in order, each with its samples - the
session's decoded array, shared, not copied (D-17) - its gain as a factor,
and its fade tables with D-42's implicit edges already decided. Nothing in
it is a model object, so the audio thread never reads the model. The only
arrays in it that change are `targets` and `levels`, each channel's gain,
and those are the engine's to write once the snapshot is handed over.

**A block finds its clips by a binary search on their ends**, not by a
cursor. At tens of clips a channel it costs as little, and it keeps no
state, so a seek or a swap needs nothing reset.

**`fill()` writes into a buffer that already exists**, one row per ear, and
makes no array (D-106): every read is a view of the decoded sample, and
every gain and fade a multiply into the row with `out=`.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from immersive.audio.dsp import IMPLICIT_FADE, Samples, db_to_gain, fade_in, fade_out
from immersive.core.io.media import Decoded
from immersive.core.model import Clip, Fade, FadeShape, Project, audible

Audio = npt.NDArray[np.float32]


@dataclass(frozen=True, eq=False)
class Placed:
    """One clip, ready to be read: where it is on the timeline, where in its
    sample it starts, the sample itself or `None` when it is not here, its
    gain, and the tables its head and tail are multiplied by."""

    start: int
    end: int
    offset: int
    audio: Audio | None
    gain: float
    head: Samples | None
    tail: Samples | None


@dataclass(frozen=True, eq=False)
class Lane:
    """One channel's clips, in order, and their ends for the search."""

    channel_id: str
    clips: tuple[Placed, ...]
    ends: tuple[int, ...]


@dataclass(frozen=True, eq=False)
class Snapshot:
    """Everything the engine plays, as of one moment of the project."""

    generation: int
    lanes: tuple[Lane, ...]
    #: Each channel's gain as a factor, mute and solo folded in (D-105):
    #: what the next block ramps to. Written by the engine after handover.
    targets: npt.NDArray[np.float64] = field(repr=False)
    #: Each channel's gain at the end of the last block played. Filled from
    #: the snapshot before, by `carry`, when this one is taken up.
    levels: npt.NDArray[np.float64] = field(repr=False)
    #: For each channel, its index in the snapshot before, or -1.
    carry: tuple[int, ...] = ()


def gains(project: Project) -> list[float]:
    """Each channel's gain as a factor, silent where `audible()` says so
    (D-62): what a command carries, and what a snapshot starts from."""
    heard = audible(project.channels)
    return [
        db_to_gain(channel.gain_db) if on else 0.0
        for channel, on in zip(project.channels, heard, strict=True)
    ]


def edges(clip: Clip, frames: int) -> tuple[Samples | None, Samples | None]:
    """The tables a clip's head and tail are multiplied by.

    An explicit fade is its own table. Without one, an edge that is not its
    file's own start or end gets D-42's 32-sample linear fade, never more
    than half the clip; an edge that is gets nothing, which is what keeps a
    whole-sample clip bit-transparent.
    """
    implicit = min(IMPLICIT_FADE, clip.length // 2)
    head = _table(clip.fade_in, implicit if clip.offset != 0 else 0, fade_in)
    at_end = clip.offset + clip.length == frames
    tail = _table(clip.fade_out, implicit if not at_end else 0, fade_out)
    return head, tail


def _table(
    fade: Fade, implicit: int, make: Callable[[FadeShape, int], Samples]
) -> Samples | None:
    if fade.length > 0:
        return make(fade.shape, fade.length)
    if implicit > 0:
        return make(FadeShape.LINEAR, implicit)
    return None


def build(
    project: Project,
    audio: Callable[[str], Decoded | None],
    previous: Snapshot | None = None,
) -> Snapshot:
    """The snapshot of `project` as it stands, reading samples through
    `audio`. On the UI thread only: it allocates freely."""
    frames = {media.id: media.frames for media in project.media_pool}
    lanes = []
    for channel in project.channels:
        placed = []
        for clip in channel.clips:
            decoded = audio(clip.media_id)
            head, tail = edges(clip, frames.get(clip.media_id, 0))
            placed.append(
                Placed(
                    start=clip.start,
                    end=clip.end,
                    offset=clip.offset,
                    audio=decoded.audio if decoded is not None else None,
                    gain=db_to_gain(clip.gain_db),
                    head=head,
                    tail=tail,
                )
            )
        lanes.append(
            Lane(channel.id, tuple(placed), tuple(clip.end for clip in placed))
        )
    before = (
        {lane.channel_id: index for index, lane in enumerate(previous.lanes)}
        if previous is not None
        else {}
    )
    targets = np.array(gains(project), dtype=np.float64)
    return Snapshot(
        generation=previous.generation + 1 if previous is not None else 1,
        lanes=tuple(lanes),
        targets=targets,
        levels=targets.copy(),
        carry=tuple(before.get(channel.id, -1) for channel in project.channels),
    )


def empty() -> Snapshot:
    """Nothing to play: what an engine starts with."""
    none = np.zeros(0, dtype=np.float64)
    return Snapshot(generation=0, lanes=(), targets=none, levels=none.copy())


def fill(lane: Lane, t: int, left: Samples, right: Samples) -> bool:
    """Write `lane`'s share of the block starting at sample `t` into `left`
    and `right`, one row per ear, silence where no clip plays. Whether any
    clip played at all, so a silent channel can be passed over.

    A mono sample goes to both ears and a stereo one keeps its sides. A clip
    whose sample is not here plays silence, and the rest of the lane plays.
    """
    size = left.shape[0]
    stop = t + size
    clips = lane.clips
    index = bisect.bisect_right(lane.ends, t)
    wrote = False
    while index < len(clips):
        clip = clips[index]
        if clip.start >= stop:
            break
        index += 1
        if clip.audio is None:
            continue
        if not wrote:
            left.fill(0)
            right.fill(0)
            wrote = True
        first = max(t, clip.start)
        last = min(stop, clip.end)
        read = clip.offset + (first - clip.start)
        count = last - first
        at = first - t
        into_l = left[at : at + count]
        into_r = right[at : at + count]
        sample = clip.audio
        np.copyto(into_l, sample[read : read + count, 0])
        np.copyto(into_r, sample[read : read + count, sample.shape[1] - 1])
        if clip.gain != 1.0:
            np.multiply(into_l, clip.gain, out=into_l)
            np.multiply(into_r, clip.gain, out=into_r)
        if clip.head is not None:
            _envelope(into_l, into_r, clip.head, first - clip.start, count)
        if clip.tail is not None:
            length = clip.tail.shape[0]
            _envelope(
                into_l, into_r, clip.tail, first - (clip.end - length), count
            )
    return wrote


def _envelope(
    left: Samples, right: Samples, table: Samples, into: int, count: int
) -> None:
    """Multiply the part of `left` and `right` that lies over `table` by it.

    `into` is how far into the table the rows' first sample is - negative
    when the rows begin before it - and `count` how long the rows are.
    """
    begin = max(into, 0)
    end = min(into + count, table.shape[0])
    if begin >= end:
        return
    part = table[begin:end]
    row_l = left[begin - into : end - into]
    row_r = right[begin - into : end - into]
    np.multiply(row_l, part, out=row_l)
    np.multiply(row_r, part, out=row_r)
