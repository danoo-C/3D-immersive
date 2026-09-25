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
from typing import Any, TypeVar

from immersive.core.commands import Command
from immersive.core.model import (
    CLIP_PREFIX,
    Channel,
    Clip,
    Fade,
    MediaFile,
    Project,
    all_ids,
    mint_id,
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


class DropClips(Command):
    """Put `clips` on `channel`, and settle every overlap they make (D-95).

    Clips on a channel never overlap (03, *Rules*), so a drop makes room for
    itself. Each clip already there loses whatever the drop covers: covered
    entirely it is removed, overlapped at one end it is trimmed, and reaching
    past both ends of the drop it is split, its head kept and a new clip
    minted for its tail. A part that loses its clip's start or end loses the
    fade that was there. Every part still plays the samples it played before
    - its offset moves with its start.

    All of it is worked out here, against the channel as it stands, so `do()`
    and `undo()` only apply one list of placements or the other, and Redo
    applies exactly what the first `do()` did.
    """

    def __init__(
        self, project: Project, channel: Channel, clips: Sequence[Clip]
    ) -> None:
        self.channel = channel
        self.before = list(channel.clips)
        self.placed_before = {id(clip): _placing(clip) for clip in channel.clips}

        cuts = sorted((clip.start, clip.end) for clip in clips)
        taken = all_ids(project) | {clip.id for clip in clips}
        self.placed_after: dict[int, _Placing] = {}
        after: list[Clip] = list(clips)
        for existing in channel.clips:
            parts = _remaining(existing.start, existing.end, cuts)
            if parts == [(existing.start, existing.end)]:
                after.append(existing)
                continue
            for index, (start, end) in enumerate(parts):
                piece = (
                    existing
                    if index == 0
                    else replace(existing, id=mint_id(CLIP_PREFIX, taken))
                )
                taken.add(piece.id)
                placing = self._piece(existing, start, end)
                if piece is existing:
                    self.placed_after[id(existing)] = placing
                else:
                    _place(piece, placing)
                after.append(piece)
        self.after = sorted(after, key=lambda clip: clip.start)

    @staticmethod
    def _piece(of: Clip, start: int, end: int) -> _Placing:
        """The part `[start, end)` of `of`, playing the samples it played."""
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

    def do(self) -> None:
        for clip in self.before:
            if id(clip) in self.placed_after:
                _place(clip, self.placed_after[id(clip)])
        self.channel.clips[:] = self.after

    def undo(self) -> None:
        for clip in self.before:
            _place(clip, self.placed_before[id(clip)])
        self.channel.clips[:] = self.before


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
