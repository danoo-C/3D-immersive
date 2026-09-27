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

**`fill()` writes into a buffer that already exists**, one row per ear and
one for mono clips, and makes no array (D-106): every read is a view of the
decoded sample, and every gain and fade a multiply into the row with `out=`.

**A channel's gain is four factors** (D-125): how much of a mono clip goes
left and right, and how much of a stereo clip's left and right is kept. Pan
is a bypassed channel's, so it is only there that they differ.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from immersive.audio.dsp import (
    IMPLICIT_FADE,
    Samples,
    balance,
    db_to_gain,
    fade_in,
    fade_out,
    pan_law,
)
from immersive.audio.hrtf.bank import Bank
from immersive.audio.spatial import Space
from immersive.core.io.media import Decoded
from immersive.core.model import Clip, Fade, FadeShape, Project, audible

Audio = npt.NDArray[np.float32]

#: A channel's four factors (D-125): a mono clip to the left and to the
#: right, and a stereo clip's left and right.
Sides = tuple[float, float, float, float]

#: What `fill()` wrote, as bits: the stereo rows, the mono row.
STEREO = 1
MONO = 2


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
    #: `(channels, 4)` each channel's `Sides`, mute, solo and pan folded in
    #: (D-105, D-125): what the next block ramps to. Written by the engine
    #: after handover.
    targets: npt.NDArray[np.float64] = field(repr=False)
    #: The same, as the last block played left them. Filled from the
    #: snapshot before, by `carry`, when this one is taken up.
    levels: npt.NDArray[np.float64] = field(repr=False)
    #: Each channel's highest sample per side since the UI thread last took
    #: them, `(channels, 2)`: what it adds to the bus, for its meter (D-117).
    #: Raised by the engine, read and zeroed by `Engine.take_channel_peaks`.
    peaks: npt.NDArray[np.float64] = field(repr=False)
    #: `(channels, 3)` each channel's position, metres; written by the
    #: engine from `POSITION` commands after handover (D-121).
    positions: npt.NDArray[np.float64] = field(repr=False)
    #: Each channel's row in `space`, or -1 for a channel played flat.
    slots: tuple[int, ...] = ()
    #: The spatial channels' buffers and the bank, or None: no bank yet,
    #: or every channel bypassed.
    space: Space | None = field(default=None, repr=False)
    #: For each channel, its index in the snapshot before, or -1.
    carry: tuple[int, ...] = ()
    #: The generation `carry` counts in: the snapshot this was built from.
    based_on: int = 0
    #: The master gain as a factor, and the limiter's switch as 1 or 0
    #: (D-126); written by the engine from `MASTER` commands after handover.
    master: npt.NDArray[np.float64] = field(
        default_factory=lambda: np.array([1.0, 1.0]), repr=False
    )


def even(gain: float) -> Sides:
    """A channel's four factors when nothing pans it: the gain four times."""
    return gain, gain, gain, gain


def gains(project: Project) -> list[Sides]:
    """Each channel's four factors, silent where `audible()` says so (D-62):
    what a command carries, and what a snapshot starts from. A bypassed
    channel's are its gain through the pan law and the balance (D-125);
    every other channel's are its gain four times."""
    heard = audible(project.channels)
    sides: list[Sides] = []
    for channel, on in zip(project.channels, heard, strict=True):
        gain = db_to_gain(channel.gain_db) if on else 0.0
        if channel.hrtf_bypass:
            mono_l, mono_r = pan_law(channel.pan)
            left, right = balance(channel.pan)
            sides.append((gain * mono_l, gain * mono_r, gain * left, gain * right))
        else:
            sides.append(even(gain))
    return sides


def master(project: Project) -> tuple[float, float]:
    """The master gain as a factor, and the limiter's switch as 1 or 0."""
    return db_to_gain(project.master.gain_db), 1.0 if project.master.limiter_on else 0.0


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
    bank: Bank | None = None,
) -> Snapshot:
    """The snapshot of `project` as it stands, reading samples through
    `audio`. With a `bank`, every channel not bypassed is spatial. On the UI
    thread only: it allocates freely."""
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
    targets = np.array(gains(project), dtype=np.float64).reshape(len(lanes), 4)
    positions = np.array(
        [(c.position.x, c.position.y, c.position.z) for c in project.channels],
        dtype=np.float64,
    ).reshape(len(lanes), 3)
    spatial = tuple(
        index
        for index, channel in enumerate(project.channels)
        if bank is not None and not channel.hrtf_bypass
    )
    slot_of = {index: slot for slot, index in enumerate(spatial)}
    return Snapshot(
        generation=previous.generation + 1 if previous is not None else 1,
        lanes=tuple(lanes),
        targets=targets,
        levels=targets.copy(),
        peaks=np.zeros((len(lanes), 2), dtype=np.float64),
        positions=positions,
        slots=tuple(slot_of.get(index, -1) for index in range(len(lanes))),
        space=(
            Space.build(bank, spatial, positions, project.distance)
            if bank is not None and spatial
            else None
        ),
        carry=tuple(before.get(channel.id, -1) for channel in project.channels),
        based_on=previous.generation if previous is not None else 0,
        master=np.array(master(project), dtype=np.float64),
    )


def empty() -> Snapshot:
    """Nothing to play: what an engine starts with."""
    none = np.zeros((0, 4), dtype=np.float64)
    return Snapshot(
        generation=0,
        lanes=(),
        targets=none,
        levels=none.copy(),
        peaks=np.zeros((0, 2), dtype=np.float64),
        positions=np.zeros((0, 3), dtype=np.float64),
    )


def fill(lane: Lane, t: int, left: Samples, right: Samples, mono: Samples) -> int:
    """Write `lane`'s share of the block starting at sample `t`: a stereo
    clip's sides into `left` and `right`, a mono clip into `mono`, silence
    where no clip of that kind plays. Which rows were written, as `STEREO`
    and `MONO` bits, so a silent channel can be passed over and a row no
    clip wrote is not read. A clip whose sample is not here plays silence,
    and the rest of the lane plays."""
    size = left.shape[0]
    stop = t + size
    clips = lane.clips
    index = bisect.bisect_right(lane.ends, t)
    wrote = 0
    while index < len(clips):
        clip = clips[index]
        if clip.start >= stop:
            break
        index += 1
        sample = clip.audio
        if sample is None:
            continue
        first = max(t, clip.start)
        last = min(stop, clip.end)
        read = clip.offset + (first - clip.start)
        count = last - first
        at = first - t
        if sample.shape[1] == 1:
            if not wrote & MONO:
                mono.fill(0)
                wrote |= MONO
            _place(clip, mono[at : at + count], sample[read : read + count, 0], first)
        else:
            if not wrote & STEREO:
                left.fill(0)
                right.fill(0)
                wrote |= STEREO
            _place(clip, left[at : at + count], sample[read : read + count, 0], first)
            _place(
                clip,
                right[at : at + count],
                sample[read : read + count, sample.shape[1] - 1],
                first,
            )
    return wrote


def _place(clip: Placed, into: Samples, samples: Samples, first: int) -> None:
    """One side of `clip` from timeline sample `first`: its samples, at its
    gain, through its fades."""
    np.copyto(into, samples)
    if clip.gain != 1.0:
        np.multiply(into, clip.gain, out=into)
    count = into.shape[0]
    if clip.head is not None:
        _envelope(into, clip.head, first - clip.start, count)
    if clip.tail is not None:
        length = clip.tail.shape[0]
        _envelope(into, clip.tail, first - (clip.end - length), count)


def _envelope(row: Samples, table: Samples, into: int, count: int) -> None:
    """Multiply the part of `row` that lies over `table` by it.

    `into` is how far into the table the row's first sample is - negative
    when the row begins before it - and `count` how long the row is.
    """
    begin = max(into, 0)
    end = min(into + count, table.shape[0])
    if begin >= end:
        return
    part = row[begin - into : end - into]
    np.multiply(part, table[begin:end], out=part)
