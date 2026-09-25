"""What is selected: one kind of thing, as many of that kind as wanted (D-57).

Owned by the `Document` beside the project it points into (D-96): cleared
when the project is replaced, and pruned of anything no longer in the
project after every change, before anyone is told of the change. Every
widget reads it and writes to it, and none keeps a selection of its own.

**Held by identity.** The model's dataclasses compare by value, and two
clips that are equal are still two clips - selecting one must not select
the other, and removing one must not deselect both. The same reasoning as
`edits._index_of`.

**One kind at a time.** Selecting a thing of another kind replaces the
selection rather than joining it: every edit verb belongs to exactly one
kind, and `Delete` with a clip and a channel selected has no answer.
Keyframes join the kinds at M6.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum

from immersive.core.model import Channel, Clip, MediaFile, Project

#: Anything that can be selected.
Selectable = Clip | Channel | MediaFile


class Kind(StrEnum):
    CLIPS = "clips"
    CHANNELS = "channels"
    MEDIA = "media"


class Selection:
    """A kind, and the things of that kind that are selected, in the order
    they were selected."""

    def __init__(self) -> None:
        self._kind: Kind | None = None
        self._things: dict[int, Selectable] = {}
        self._observers: list[Callable[[], None]] = []

    # ------------------------------------------------------------- reading

    @property
    def kind(self) -> Kind | None:
        """What is selected, or `None` when nothing is."""
        return self._kind

    def things(self) -> list[Selectable]:
        return list(self._things.values())

    def clips(self) -> list[Clip]:
        return [thing for thing in self._things.values() if isinstance(thing, Clip)]

    def channels(self) -> list[Channel]:
        return [thing for thing in self._things.values() if isinstance(thing, Channel)]

    def media(self) -> list[MediaFile]:
        return [
            thing for thing in self._things.values() if isinstance(thing, MediaFile)
        ]

    def __contains__(self, thing: object) -> bool:
        return self._things.get(id(thing)) is thing

    def __len__(self) -> int:
        return len(self._things)

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` after the selection changes. A change that
        changes nothing calls nobody."""
        self._observers.append(callback)

    # ------------------------------------------------------------ changing

    def select(self, kind: Kind, things: Iterable[Selectable]) -> None:
        """Exactly `things`, whatever was selected before."""
        self._set(kind, things)

    def add(self, kind: Kind, things: Iterable[Selectable]) -> None:
        """`things` as well - or instead, if what is selected is another kind."""
        before = self.things() if kind is self._kind else []
        self._set(kind, [*before, *things])

    def toggle(self, kind: Kind, thing: Selectable) -> None:
        """`thing` in if it was out and out if it was in; of another kind,
        the selection becomes `thing` alone."""
        if kind is not self._kind:
            self._set(kind, [thing])
        elif thing in self:
            self._set(kind, [t for t in self._things.values() if t is not thing])
        else:
            self._set(kind, [*self._things.values(), thing])

    def clear(self) -> None:
        self._set(None, [])

    def prune(self, project: Project) -> None:
        """Forget anything no longer in `project` - a clip an Undo removed, a
        channel deleted, a sample taken out of the pool."""
        if self._kind is None:
            return
        present = {id(thing) for thing in _all(project, self._kind)}
        self._set(self._kind, [t for t in self._things.values() if id(t) in present])

    # ------------------------------------------------------------ internal

    def _set(self, kind: Kind | None, things: Iterable[Selectable]) -> None:
        chosen = {id(thing): thing for thing in things}
        after_kind = kind if chosen else None
        if after_kind is self._kind and list(chosen) == list(self._things):
            return
        self._kind, self._things = after_kind, chosen
        for callback in list(self._observers):
            callback()


def _all(project: Project, kind: Kind) -> list[Selectable]:
    if kind is Kind.CLIPS:
        return [clip for channel in project.channels for clip in channel.clips]
    if kind is Kind.CHANNELS:
        return list(project.channels)
    return list(project.media_pool)
