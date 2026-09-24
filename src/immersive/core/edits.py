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
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

from immersive.core.commands import Command
from immersive.core.model import Channel, Clip, MediaFile, Project

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
