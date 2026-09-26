"""The first concrete edits — one per *shape* of mutation, not per field.

M3 will need dozens of these. This module wants one of each kind — insert into
and remove from an ordered list, change one field, change a field mergeably —
because the shapes, not the count, are what the stack has to handle correctly.

Every command here is constructed against live objects and captures what it
needs to reverse itself at construction, per `commands.Command`.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import fields, is_dataclass, replace
from enum import StrEnum
from typing import Any, TypeVar

from immersive.core.commands import Command
from immersive.core.model import (
    CLIP_PREFIX,
    MIN_CLIP_LENGTH,
    Channel,
    Clip,
    Fade,
    MediaFile,
    Project,
    all_ids,
    mint_id,
    new_channel,
)

_T = TypeVar("_T")


def _index_of(items: Sequence[_T], wanted: _T) -> int:
    """Where `wanted` sits, by identity.

    `list.index` compares by value and phase 1's dataclasses compare by value,
    so two channels a user has not yet told apart are the same channel to
    `index()` — and removing one would remove the other, invisibly, until undo
    put it back in the wrong place.
    """
    for index, item in enumerate(items):
        if item is wanted:
            return index
    raise ValueError(f"{wanted!r} is not in this list")


# --------------------------------------------------------------------------- #
# ordered lists
# --------------------------------------------------------------------------- #


class AddChannel(Command):
    """Insert a channel. `index` defaults to the end.

    A channel's place in `Project.channels` is its order (D-61), so the index
    is the whole of what has to be restored.
    """

    def __init__(
        self, project: Project, channel: Channel, index: int | None = None
    ) -> None:
        self.project = project
        self.channel = channel
        self.index = len(project.channels) if index is None else index

    def do(self) -> None:
        self.project.channels.insert(self.index, self.channel)

    def undo(self) -> None:
        del self.project.channels[self.index]


class RemoveChannel(Command):
    def __init__(self, project: Project, channel: Channel) -> None:
        self.project = project
        self.channel = channel
        self.index = _index_of(project.channels, channel)

    def do(self) -> None:
        del self.project.channels[self.index]

    def undo(self) -> None:
        self.project.channels.insert(self.index, self.channel)


class MoveChannel(Command):
    """Put a channel at `index` in the order, counted as the list will stand
    once it is there.

    A channel's place in the list is its order (D-61), so a reorder is one
    removal and one insertion, and Undo is the same two the other way round.
    The channel is found by identity, for the reason `_index_of` gives.
    """

    def __init__(self, project: Project, channel: Channel, index: int) -> None:
        if not 0 <= index < len(project.channels):
            raise IndexError(f"index {index} is outside 0..{len(project.channels) - 1}")
        self.project = project
        self.channel = channel
        self.origin = _index_of(project.channels, channel)
        self.index = index

    def do(self) -> None:
        del self.project.channels[self.origin]
        self.project.channels.insert(self.index, self.channel)

    def undo(self) -> None:
        del self.project.channels[self.index]
        self.project.channels.insert(self.origin, self.channel)


class AddClip(Command):
    """Place a clip on a channel, keeping `clips` sorted by start.

    The position is derived rather than asked for. Sorted-and-non-overlapping
    is a rule `model.validate()` owns; a caller passing an index would be a
    second place that rule lived, and the two would eventually disagree.
    """

    def __init__(self, channel: Channel, clip: Clip) -> None:
        self.channel = channel
        self.clip = clip
        self.index = bisect.bisect_right(
            channel.clips, clip.start, key=lambda existing: existing.start
        )

    def do(self) -> None:
        self.channel.clips.insert(self.index, self.clip)

    def undo(self) -> None:
        del self.channel.clips[self.index]


#: What a clip's placement is, for putting it back: where it starts, where
#: in its sample, how long, and its two fades.
_Placing = tuple[int, int, int, Fade, Fade]


def _placing(clip: Clip) -> _Placing:
    return (clip.start, clip.offset, clip.length, clip.fade_in, clip.fade_out)


def _place(clip: Clip, placing: _Placing) -> None:
    clip.start, clip.offset, clip.length, clip.fade_in, clip.fade_out = placing


def _remaining(
    start: int, end: int, cuts: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """The parts of `[start, end)` that none of `cuts` covers, in order."""
    pieces = [(start, end)]
    for cut_start, cut_end in cuts:
        kept = []
        for piece_start, piece_end in pieces:
            if cut_end <= piece_start or piece_end <= cut_start:
                kept.append((piece_start, piece_end))
                continue
            if piece_start < cut_start:
                kept.append((piece_start, cut_start))
            if cut_end < piece_end:
                kept.append((cut_end, piece_end))
        pieces = kept
    return pieces


def _settle(
    existing: Sequence[Clip],
    incoming: Sequence[tuple[Clip, _Placing]],
    taken: set[str],
) -> tuple[list[Clip], dict[int, tuple[Clip, _Placing]]]:
    """A channel holding `existing` once `incoming` land at their placings,
    and every overlap they make settled (D-95).

    Each clip already there loses whatever the incoming ones cover: covered
    entirely it is left out, overlapped at one end it is trimmed, and
    reaching past both ends it is split, its head kept and a new clip minted
    for its tail - placed at once, since nothing else holds it yet. A part
    that loses its clip's start or end loses the fade that was there, and
    every part still plays the samples it played before.

    Returns the channel's clips as they will stand, sorted, and the new
    placing of every existing clip that changes.
    """
    cuts = sorted((placing[0], placing[0] + placing[2]) for _, placing in incoming)
    starts = {id(clip): placing[0] for clip, placing in incoming}
    changed: dict[int, tuple[Clip, _Placing]] = {}
    after: list[Clip] = [clip for clip, _ in incoming]
    for clip in existing:
        parts = _remaining(clip.start, clip.end, cuts)
        if parts == [(clip.start, clip.end)]:
            after.append(clip)
            starts[id(clip)] = clip.start
            continue
        for index, (start, end) in enumerate(parts):
            placing = _piece(clip, start, end)
            if index == 0:
                changed[id(clip)] = (clip, placing)
                piece = clip
            else:
                piece = replace(clip, id=mint_id(CLIP_PREFIX, taken))
                taken.add(piece.id)
                _place(piece, placing)
            after.append(piece)
            starts[id(piece)] = start
    return sorted(after, key=lambda clip: starts[id(clip)]), changed


def _piece(of: Clip, start: int, end: int) -> _Placing:
    """The part `[start, end)` of `of`, playing the samples it played there,
    with each fade kept only where its edge is, and cut to fit."""
    length = end - start
    fade_in = (
        replace(of.fade_in, length=min(of.fade_in.length, length))
        if start == of.start
        else Fade()
    )
    fade_out = (
        replace(of.fade_out, length=min(of.fade_out.length, length))
        if end == of.end
        else Fade()
    )
    return (start, of.offset + (start - of.start), length, fade_in, fade_out)


def _home(project: Project, clip: Clip) -> Channel:
    """The channel holding `clip`, found by identity."""
    for channel in project.channels:
        if any(held is clip for held in channel.clips):
            return channel
    raise ValueError(f"{clip.id} is not on any channel of this project")


class _Rearrangement(Command):
    """Channels' clip lists, and clips' placings, as they were and as they
    will be - worked out by a subclass at construction, applied whole.

    So `do()` and `undo()` only apply one set or the other, and Redo applies
    exactly what the first `do()` did.
    """

    def __init__(self) -> None:
        self._lists: list[tuple[Channel, list[Clip], list[Clip]]] = []
        self._placings: list[tuple[Clip, _Placing, _Placing]] = []

    def _list(self, channel: Channel, after: list[Clip]) -> None:
        self._lists.append((channel, list(channel.clips), after))

    def _placing(self, clip: Clip, after: _Placing) -> None:
        self._placings.append((clip, _placing(clip), after))

    @property
    def changes(self) -> bool:
        """Whether doing it would change anything at all."""
        return any(before != after for _, before, after in self._placings) or any(
            [id(c) for c in before] != [id(c) for c in after]
            for _, before, after in self._lists
        )

    def do(self) -> None:
        for clip, _, after in self._placings:
            _place(clip, after)
        for channel, _, clips in self._lists:
            channel.clips[:] = clips

    def undo(self) -> None:
        for clip, before, _ in self._placings:
            _place(clip, before)
        for channel, clips, _ in self._lists:
            channel.clips[:] = clips


class DropClips(_Rearrangement):
    """Put `clips` on `channel`, and settle every overlap they make (D-95).

    Clips on a channel never overlap (03, *Rules*), so a drop makes room for
    itself, as `_settle` says.
    """

    def __init__(
        self, project: Project, channel: Channel, clips: Sequence[Clip]
    ) -> None:
        super().__init__()
        taken = all_ids(project) | {clip.id for clip in clips}
        after, changed = _settle(
            channel.clips, [(clip, _placing(clip)) for clip in clips], taken
        )
        self._list(channel, after)
        for clip, placing in changed.values():
            self._placing(clip, placing)


class MoveClips(_Rearrangement):
    """Move `clips` by `delta` samples and `lanes` channels, together (D-97).

    Every clip goes by the same offset, so the selection keeps its shape;
    the offsets stop, for all of them at once, where the first clip would
    pass the timeline's start or a clip would pass the first or last lane.
    The moved clips are lifted first, so none trims itself or another of
    them, and then land as a drop does, overwriting what they cover.

    `delta` and `lanes` are what is left after that stopping, and
    `placed()` is where each clip lands - what a drag draws while it lasts.
    """

    def __init__(
        self, project: Project, clips: Sequence[Clip], delta: int, lanes: int = 0
    ) -> None:
        super().__init__()
        channels = project.channels
        homes = [_index_of(channels, _home(project, clip)) for clip in clips]
        if clips:
            delta = max(delta, -min(clip.start for clip in clips))
            lanes = max(lanes, -min(homes))
            lanes = min(lanes, len(channels) - 1 - max(homes))
        self.delta, self.lanes = delta, lanes
        self._placed = [
            (clip, home + lanes, clip.start + delta)
            for clip, home in zip(clips, homes, strict=True)
        ]

        moving = {id(clip) for clip in clips}
        arriving: dict[int, list[tuple[Clip, _Placing]]] = {}
        for clip, lane, start in self._placed:
            placing = (start, clip.offset, clip.length, clip.fade_in, clip.fade_out)
            arriving.setdefault(lane, []).append((clip, placing))
            self._placing(clip, placing)
        taken = all_ids(project)
        for lane in sorted(set(homes) | set(arriving)):
            channel = channels[lane]
            staying = [clip for clip in channel.clips if id(clip) not in moving]
            after, changed = _settle(staying, arriving.get(lane, []), taken)
            self._list(channel, after)
            for clip, placing in changed.values():
                self._placing(clip, placing)

    def placed(self) -> list[tuple[Clip, int, int]]:
        """Each clip, the lane it lands in, and the sample it starts at."""
        return list(self._placed)


class Edge(StrEnum):
    """Which end of a clip a trim moves."""

    START = "start"
    END = "end"


def trimmed(project: Project, clip: Clip, edge: Edge, delta: int) -> _Placing:
    """`clip` with its `edge` moved `delta` samples, as far as it can go
    (D-98): no further than its sample reaches, than the next clip on its
    channel, or than the timeline's start, and no shorter than
    `MIN_CLIP_LENGTH` - or than it already is, if a file made it shorter.

    Moving the start moves the offset with it, so what is left plays the
    samples it played. A fade stays with its edge, cut to fit.
    """
    channel = _home(project, clip)
    index = _index_of(channel.clips, clip)
    shortest = min(MIN_CLIP_LENGTH, clip.length)
    frames = next(
        (m.frames for m in project.media_pool if m.id == clip.media_id),
        clip.offset + clip.length,
    )
    if edge is Edge.END:
        following = channel.clips[index + 1 :]
        limit = following[0].start if following else None
        longest = frames - clip.offset
        if limit is not None:
            longest = min(longest, limit - clip.start)
        length = min(max(clip.length + delta, shortest), longest)
        return _piece_to(clip, clip.start, length)
    floor = max(-clip.offset, -clip.start)
    if index > 0:
        floor = max(floor, channel.clips[index - 1].end - clip.start)
    delta = min(max(delta, floor), clip.length - shortest)
    return _piece_to(clip, clip.start + delta, clip.length - delta)


def _piece_to(of: Clip, start: int, length: int) -> _Placing:
    """`of` running from `start` for `length`, its offset following its start
    and its fades kept on their edges, cut to fit."""
    return (
        start,
        of.offset + (start - of.start),
        length,
        replace(of.fade_in, length=min(of.fade_in.length, length)),
        replace(of.fade_out, length=min(of.fade_out.length, length)),
    )


class TrimClips(_Rearrangement):
    """Move the same edge of every one of `clips` by `delta`, each as far as
    it can go (D-98). One command however many clips."""

    def __init__(
        self, project: Project, clips: Sequence[Clip], edge: Edge, delta: int
    ) -> None:
        super().__init__()
        for clip in clips:
            self._placing(clip, trimmed(project, clip, edge, delta))

    def trims(self) -> list[tuple[Clip, int, int, int]]:
        """Each clip, and the start, offset and length it will have."""
        return [
            (clip, after[0], after[1], after[2]) for clip, _, after in self._placings
        ]


class SplitClips(_Rearrangement):
    """Split every one of `clips` that `at` is inside into two, where both
    parts are at least `MIN_CLIP_LENGTH`; the rest are left alone.

    The head keeps the clip and its fade in, the tail is a new clip with the
    fade out, and together they play exactly the samples the clip played.
    """

    def __init__(self, project: Project, clips: Sequence[Clip], at: int) -> None:
        super().__init__()
        taken = all_ids(project)
        self.tails: list[Clip] = []
        by_channel: dict[int, tuple[Channel, list[tuple[Clip, Clip]]]] = {}
        for clip in clips:
            if not (clip.start + MIN_CLIP_LENGTH <= at <= clip.end - MIN_CLIP_LENGTH):
                continue
            tail = replace(clip, id=mint_id(CLIP_PREFIX, taken))
            taken.add(tail.id)
            _place(tail, _piece(clip, at, clip.end))
            self._placing(clip, _piece(clip, clip.start, at))
            self.tails.append(tail)
            channel = _home(project, clip)
            by_channel.setdefault(id(channel), (channel, []))[1].append((clip, tail))
        for channel, pairs in by_channel.values():
            tails = {id(head): tail for head, tail in pairs}
            after: list[Clip] = []
            for clip in channel.clips:
                after.append(clip)
                if id(clip) in tails:
                    after.append(tails[id(clip)])
            self._list(channel, after)


class DuplicateClips(_Rearrangement):
    """A copy of every one of `clips`, just after them all: each copy on its
    own clip's channel, shifted by the length of the stretch they span, so
    the copies sit end to end with the originals as they sat together.
    They land as a drop does, and `copies` is them, in the order given."""

    def __init__(self, project: Project, clips: Sequence[Clip]) -> None:
        super().__init__()
        self.copies: list[Clip] = []
        if not clips:
            return
        shift = max(clip.end for clip in clips) - min(clip.start for clip in clips)
        taken = all_ids(project)
        arriving: dict[int, tuple[Channel, list[tuple[Clip, _Placing]]]] = {}
        for clip in clips:
            copy = replace(
                clip,
                id=mint_id(CLIP_PREFIX, taken),
                start=clip.start + shift,
                fade_in=replace(clip.fade_in),
                fade_out=replace(clip.fade_out),
            )
            taken.add(copy.id)
            self.copies.append(copy)
            channel = _home(project, clip)
            arriving.setdefault(id(channel), (channel, []))[1].append(
                (copy, _placing(copy))
            )
        for channel, incoming in arriving.values():
            after, changed = _settle(channel.clips, incoming, taken)
            self._list(channel, after)
            for clip, placing in changed.values():
                self._placing(clip, placing)


class PasteClips(_Rearrangement):
    """Copies of `held` landed with the topmost on lane `lane` and the
    earliest starting at `at` (D-100).

    `held` is what a `Clipboard` holds: each clip with its lane counted from
    the topmost and its start from the earliest. Every copy gets a fresh id
    and fades of its own, and lands as a drop does, overwriting what it
    covers. Lanes past the last become new channels, named and coloured in
    turn from `palette`, and are part of this one edit.

    `copies` is the clips it lands, in the order given, and `channels` the
    channels it adds. A clip whose sample is not in the pool is refused here,
    at construction: a paste never names nothing (D-99).
    """

    def __init__(
        self,
        project: Project,
        held: Sequence[tuple[int, Clip]],
        lane: int,
        at: int,
        palette: Sequence[str],
    ) -> None:
        super().__init__()
        if lane < 0 or at < 0:
            raise ValueError(f"a paste lands at a lane and a time, not {lane}, {at}")
        pool = {media.id for media in project.media_pool}
        if gone := sorted({clip.media_id for _, clip in held} - pool):
            raise ValueError(f"{', '.join(gone)} is not in the pool")
        self.project = project
        self.copies: list[Clip] = []
        self.channels: list[Channel] = []
        if not held:
            return

        # Each new channel is made against the project as it will stand with
        # the ones before it, so the names and the colours carry on in turn.
        needed = lane + max(offset for offset, _ in held) + 1
        will_be = project
        while len(will_be.channels) < needed:
            channel = new_channel(will_be, palette)
            self.channels.append(channel)
            will_be = replace(will_be, channels=[*will_be.channels, channel])

        taken = all_ids(will_be)
        arriving: dict[int, list[tuple[Clip, _Placing]]] = {}
        for offset, clip in held:
            copy = replace(
                clip,
                id=mint_id(CLIP_PREFIX, taken),
                start=at + clip.start,
                fade_in=replace(clip.fade_in),
                fade_out=replace(clip.fade_out),
            )
            taken.add(copy.id)
            self.copies.append(copy)
            arriving.setdefault(lane + offset, []).append((copy, _placing(copy)))
        for index in sorted(arriving):
            channel = will_be.channels[index]
            after, changed = _settle(channel.clips, arriving[index], taken)
            self._list(channel, after)
            for clip, placing in changed.values():
                self._placing(clip, placing)

    def do(self) -> None:
        self.project.channels.extend(self.channels)
        super().do()

    def undo(self) -> None:
        super().undo()
        if self.channels:
            del self.project.channels[-len(self.channels) :]


class RemoveClips(_Rearrangement):
    """Take every one of `clips` off its channel, as one edit."""

    def __init__(self, project: Project, clips: Sequence[Clip]) -> None:
        super().__init__()
        going = {id(clip) for clip in clips}
        for channel in project.channels:
            if any(id(clip) in going for clip in channel.clips):
                self._list(
                    channel, [clip for clip in channel.clips if id(clip) not in going]
                )


class RemoveClip(Command):
    def __init__(self, channel: Channel, clip: Clip) -> None:
        self.channel = channel
        self.clip = clip
        self.index = _index_of(channel.clips, clip)

    def do(self) -> None:
        del self.channel.clips[self.index]

    def undo(self) -> None:
        self.channel.clips.insert(self.index, self.clip)


# --------------------------------------------------------------------------- #
# fields
# --------------------------------------------------------------------------- #


class SetAttribute(Command):
    """Change one field on one dataclass.

    Deliberately generic, and deliberately the only stringly-typed thing here.
    The alternative is a class per field — `RenameChannel`, `SetChannelGain`,
    `SetChannelMute` — which is twenty classes differing by one attribute name
    that give nothing back.

    The name is checked against the target's real fields at construction, so a
    typo fails where it is written rather than silently inventing an attribute
    that nothing reads and that undo cannot remove.
    """

    def __init__(self, target: Any, name: str, value: Any) -> None:
        if not is_dataclass(target) or isinstance(target, type):
            raise TypeError(f"SetAttribute needs a dataclass instance, got {target!r}")
        known = {declared.name for declared in fields(target)}
        if name not in known:
            raise AttributeError(
                f"{type(target).__name__} has no field {name!r}; "
                f"it has {', '.join(sorted(known))}"
            )
        self.target = target
        self.name = name
        self.value = value
        self.previous = getattr(target, name)

    def do(self) -> None:
        setattr(self.target, self.name, self.value)

    def undo(self) -> None:
        setattr(self.target, self.name, self.previous)


class AddMedia(Command):
    """Add several samples to the pool as one edit: one import, one Undo.

    Redo puts back the same objects rather than new ones, so anything that
    already refers to them by id - the session's decoded audio above all -
    still finds them.
    """

    def __init__(self, project: Project, entries: Sequence[MediaFile]) -> None:
        self.project = project
        self.entries = list(entries)
        self.at = len(project.media_pool)

    def do(self) -> None:
        self.project.media_pool[self.at : self.at] = self.entries

    def undo(self) -> None:
        del self.project.media_pool[self.at : self.at + len(self.entries)]


class Relink(Command):
    """Point a pool entry at another file, and take that file's facts (D-90).

    Every field the file determines changes with the path, together, because
    keeping the old frame count would be the pool lying about what plays. The
    id stays: it is what every clip holds.

    `missing` is part of it. Undoing a relink has to say the file is gone
    again, or Undo claims the audio is back when it is not.
    """

    FIELDS = ("path", "name", "hash", "source_rate", "channels", "frames", "missing")

    def __init__(self, media: MediaFile, replacement: MediaFile) -> None:
        self.media = media
        self.before = {name: getattr(media, name) for name in self.FIELDS}
        self.after = {name: getattr(replacement, name) for name in self.FIELDS}
        self.after["missing"] = False

    def do(self) -> None:
        for name, value in self.after.items():
            setattr(self.media, name, value)

    def undo(self) -> None:
        for name, value in self.before.items():
            setattr(self.media, name, value)


class MoveClip(Command):
    """Slide a clip along its channel.

    Does not reorder `channel.clips`, and does not check where it lands: a
    move that would overlap a neighbour is refused by the stack's validation,
    which is the one place that rule lives.
    """

    def __init__(self, clip: Clip, start: int) -> None:
        self.clip = clip
        self.start = start
        self.previous = clip.start

    def do(self) -> None:
        self.clip.start = self.start

    def undo(self) -> None:
        self.clip.start = self.previous

    def merge_with(self, other: Command) -> bool:
        if not isinstance(other, MoveClip) or other.clip is not self.clip:
            return False
        # Take the later destination and keep our own `previous`, which is
        # where the drag began rather than where its last step began.
        self.start = other.start
        return True
