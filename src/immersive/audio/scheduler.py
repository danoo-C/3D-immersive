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

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from immersive.audio.compiled import kernel, read
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
from immersive.audio.spatial import POINT, Space, Weighed
from immersive.core.io.loudness import StemSpectra, measure
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    Fade,
    FadeShape,
    Position,
    Project,
    audible,
    paired,
    sides,
)

Audio = npt.NDArray[np.float32]

#: A channel's four factors (D-125): a mono clip to the left and to the
#: right, and a stereo clip's left and right.
Sides = tuple[float, float, float, float]

#: What `fill()` wrote, as bits: the stereo rows, the mono row.
STEREO = 1
MONO = 2

#: A snapshot's clips as a table a kernel reads (D-140), a row per clip, in
#: each lane's order: where it sits on the timeline, where it starts in its
#: sample, the sample's address, frames and channels (all 0 when it is not
#: here), and its fades' tables' addresses and lengths (0 for none).
START, END, OFFSET, ADDRESS, FRAMES, CHANNELS = 0, 1, 2, 3, 4, 5
HEAD, HEAD_LENGTH, TAIL, TAIL_LENGTH = 6, 7, 8, 9
COLUMNS = 10

Table = npt.NDArray[np.int64]


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
    """One channel's clips, in order: as `Placed`, which hold the arrays
    alive, and as their rows of the snapshot's table, which a kernel reads."""

    channel_id: str
    clips: tuple[Placed, ...]
    table: Table = field(repr=False)
    gains: npt.NDArray[np.float64] = field(repr=False)


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
    #: `(channels, 2, 3)` each channel's left and right side, metres - its
    #: point twice when it is one (D-132); written by the engine from
    #: `POSITION` commands after handover (D-121).
    positions: npt.NDArray[np.float64] = field(repr=False)
    #: Each channel's row in `space` - its left side's, when it is a pair -
    #: or -1 for a channel played flat.
    slots: tuple[int, ...] = ()
    #: Whether each channel is heard as two sources, a pair (D-132): its
    #: right side is the row after its left.
    paired: tuple[bool, ...] = ()
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
    #: Every lane's clips as one table, each lane's rows from
    #: `lane_first[lane]` to `lane_first[lane + 1]`, and each clip's gain
    #: (D-140). It names arrays that `lanes` holds, so it is read only while
    #: the snapshot is.
    clips: Table = field(
        default_factory=lambda: np.zeros((0, COLUMNS), dtype=np.int64), repr=False
    )
    clip_gains: npt.NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0), repr=False
    )
    lane_first: npt.NDArray[np.int64] = field(
        default_factory=lambda: np.zeros(1, dtype=np.int64), repr=False
    )


def positioned(project: Project, channel: Channel) -> tuple[Position, Position]:
    """Where a channel's two sides are heard from: its placement's, when it
    is a pair, and its one point twice when it is not (D-132)."""
    if paired(project, channel):
        return sides(channel)
    return channel.position, channel.position


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
    spatial = tuple(
        index
        for index, channel in enumerate(project.channels)
        if bank is not None and not channel.hrtf_bypass
    )
    # Heard as two sources (D-132): a pair is not folded, so no fold.
    pairs = tuple(
        index in spatial and paired(project, channel)
        for index, channel in enumerate(project.channels)
    )
    held: list[tuple[str, list[Placed]]] = []
    for index, channel in enumerate(project.channels):
        placed = []
        for clip in channel.clips:
            decoded = audio(clip.media_id)
            head, tail = edges(clip, frames.get(clip.media_id, 0))
            gain = db_to_gain(clip.gain_db)
            if decoded is not None and index in spatial and not pairs[index]:
                # Folded to a point, a stereo clip gets back what the
                # folding loses (D-129); a mono one's fold is 1.
                gain *= decoded.fold
            placed.append(
                Placed(
                    start=clip.start,
                    end=clip.end,
                    offset=clip.offset,
                    # Read by address (D-140): C-contiguous float32, as a
                    # decode leaves it; `require` copies only if not.
                    audio=(
                        np.require(decoded.audio, np.float32, "C")
                        if decoded is not None
                        else None
                    ),
                    gain=gain,
                    head=head,
                    tail=tail,
                )
            )
        held.append((channel.id, placed))
    rows = [row(clip) for _, placed in held for clip in placed]
    clips = np.array(rows, dtype=np.int64).reshape(len(rows), COLUMNS)
    clip_gains = np.array(
        [clip.gain for _, placed in held for clip in placed], dtype=np.float64
    )
    lane_first = np.cumsum([0] + [len(placed) for _, placed in held]).astype(np.int64)
    lanes = [
        Lane(
            channel_id,
            tuple(placed),
            clips[lane_first[index] : lane_first[index + 1]],
            clip_gains[lane_first[index] : lane_first[index + 1]],
        )
        for index, (channel_id, placed) in enumerate(held)
    ]
    before = (
        {lane.channel_id: index for index, lane in enumerate(previous.lanes)}
        if previous is not None
        else {}
    )
    targets = np.array(gains(project), dtype=np.float64).reshape(len(lanes), 4)
    positions = np.array(
        [
            [(side.x, side.y, side.z) for side in positioned(project, channel)]
            for channel in project.channels
        ],
        dtype=np.float64,
    ).reshape(len(lanes), 2, 3)
    sources: list[int] = []
    sides: list[int] = []
    spectra: list[Weighed] = []
    bins = bank.nfft // 2 + 1 if bank is not None else 0
    slot_of: dict[int, int] = {}
    for index in spatial:
        slot_of[index] = len(sources)
        if pairs[index]:
            sources += [index, index]
            sides += [0, 1]
            spectra.append(heard_as(project.channels[index], audio, bins))
        else:
            sources.append(index)
            sides.append(POINT)
    return Snapshot(
        generation=previous.generation + 1 if previous is not None else 1,
        lanes=tuple(lanes),
        targets=targets,
        levels=targets.copy(),
        peaks=np.zeros((len(lanes), 2), dtype=np.float64),
        positions=positions,
        slots=tuple(slot_of.get(index, -1) for index in range(len(lanes))),
        paired=pairs,
        space=(
            Space.build(
                bank,
                tuple(sources),
                positions,
                project.distance,
                tuple(sides),
                spectra,
            )
            if bank is not None and spatial
            else None
        ),
        carry=tuple(before.get(channel.id, -1) for channel in project.channels),
        based_on=previous.generation if previous is not None else 0,
        master=np.array(master(project), dtype=np.float64),
        clips=clips,
        clip_gains=clip_gains,
        lane_first=lane_first,
    )


def row(clip: Placed) -> list[int]:
    """A clip's row of the table (D-140): its arrays by address, which the
    `Placed` it came from keeps alive."""
    audio, head, tail = clip.audio, clip.head, clip.tail
    return [
        clip.start,
        clip.end,
        clip.offset,
        audio.ctypes.data if audio is not None else 0,
        audio.shape[0] if audio is not None else 0,
        audio.shape[1] if audio is not None else 0,
        head.ctypes.data if head is not None else 0,
        head.shape[0] if head is not None else 0,
        tail.ctypes.data if tail is not None else 0,
        tail.shape[0] if tail is not None else 0,
    ]


def heard_as(
    channel: Channel, audio: Callable[[str], Decoded | None], bins: int
) -> Weighed:
    """A pair's left, right and shared spectra at the bank's `bins`, divided
    by the stem as mixed (D-133): its clips' files' own, each weighted by
    how much of its file the clip plays. A mono clip's three are its one."""
    left = right = None
    shared = None
    for clip in channel.clips:
        decoded = audio(clip.media_id)
        if decoded is None or decoded.frames == 0:
            continue
        own = decoded.spectra if decoded.spectra is not None else measure(decoded.audio)
        share = clip.length / decoded.frames
        if left is None or right is None or shared is None:
            left, right, shared = (
                own.left * share,
                own.right * share,
                own.shared * share,
            )
        else:
            left = left + own.left * share
            right = right + own.right * share
            shared = shared + own.shared * share
    if left is None or right is None or shared is None:
        return StemSpectra(np.ones(1), np.ones(1), np.zeros(1, dtype=np.complex128)).at(
            bins
        )
    return StemSpectra(left, right, shared).at(bins)


def empty() -> Snapshot:
    """Nothing to play: what an engine starts with."""
    none = np.zeros((0, 4), dtype=np.float64)
    return Snapshot(
        generation=0,
        lanes=(),
        targets=none,
        levels=none.copy(),
        peaks=np.zeros((0, 2), dtype=np.float64),
        positions=np.zeros((0, 2, 3), dtype=np.float64),
    )


def fill(lane: Lane, t: int, left: Samples, right: Samples, mono: Samples) -> int:
    """Write `lane`'s share of the block starting at sample `t`: a stereo
    clip's sides into `left` and `right`, a mono clip into `mono`, silence
    where no clip of that kind plays. Which rows were written, as `STEREO`
    and `MONO` bits, so a silent channel can be passed over and a row no
    clip wrote is not read. A clip whose sample is not here plays silence,
    and the rest of the lane plays. `_fill`, compiled, on the lane's rows
    of its snapshot's table."""
    return int(_fill(lane.table, lane.gains, t, left, right, mono))


@kernel
def _fill(
    table: Table,
    gains: npt.NDArray[np.float64],
    t: int,
    left: Samples,
    right: Samples,
    mono: Samples,
) -> int:
    """`fill` for the clips in `table`, in order of their ends, reading each
    sample through its address (D-140)."""
    size = left.shape[0]
    stop = t + size
    clips = table.shape[0]
    # The first clip ending after `t`: a binary search on the ends.
    low, high = 0, clips
    while low < high:
        middle = (low + high) // 2
        if t < table[middle, END]:
            high = middle
        else:
            low = middle + 1
    wrote = 0
    for row in range(low, clips):
        start = table[row, START]
        if start >= stop:
            break
        if table[row, ADDRESS] == 0:
            continue  # not here: silence, and the rest of the lane plays
        first = max(t, start)
        count = min(stop, table[row, END]) - first
        at = first - t
        channels = table[row, CHANNELS]
        if channels == 1:
            if not wrote & MONO:
                mono[:] = 0.0
                wrote |= MONO
            _place(table, gains, row, mono, at, count, 0, first)
        else:
            if not wrote & STEREO:
                left[:] = 0.0
                right[:] = 0.0
                wrote |= STEREO
            _place(table, gains, row, left, at, count, 0, first)
            _place(table, gains, row, right, at, count, channels - 1, first)
    return wrote


@kernel
def _place(
    table: Table,
    gains: npt.NDArray[np.float64],
    row: int,
    into: Samples,
    at: int,
    count: int,
    channel: int,
    first: int,
) -> None:
    """One side of clip `row` into `into[at : at + count]`, from timeline
    sample `first`: its samples, at its gain, through its fades. Reads stop
    at the sample's own end, and anything past it is silence: an address is
    not bounds-checked (D-140)."""
    start, end = table[row, START], table[row, END]
    frames, channels = table[row, FRAMES], table[row, CHANNELS]
    address = table[row, ADDRESS]
    begin = table[row, OFFSET] + (first - start)
    heard = max(min(count, frames - begin), 0)
    for i in range(heard):
        into[at + i] = read(address, (begin + i) * channels + channel)
    for i in range(heard, count):
        into[at + i] = 0.0
    gain = gains[row]
    if gain != 1.0:
        scale = np.float32(gain)
        for i in range(count):
            into[at + i] = into[at + i] * scale
    head = table[row, HEAD_LENGTH]
    if head > 0:
        _envelope(into, at, count, table[row, HEAD], head, first - start)
    tail = table[row, TAIL_LENGTH]
    if tail > 0:
        _envelope(into, at, count, table[row, TAIL], tail, first - (end - tail))


@kernel
def _envelope(
    into: Samples, at: int, count: int, address: int, length: int, offset: int
) -> None:
    """Multiply the part of `into[at : at + count]` that lies over the fade
    table at `address` by it. `offset` is how far into the table the row's
    first sample is: negative when the row begins before it."""
    for k in range(max(offset, 0), min(offset + count, length)):
        into[at + k - offset] = into[at + k - offset] * read(address, k)
