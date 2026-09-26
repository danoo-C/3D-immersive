"""The project model: plain mutable dataclasses, one per entity in
docs/03-data-model.md.

Reading this module and reading that document should be the same activity, so
the field names are taken from it literally and there is no inheritance, no
base class and no property that hides storage.

Two choices worth knowing before reading further.

**Mutable, not frozen.** Commands mutate the model in place (D-14). Frozen
dataclasses would force every edit to rebuild a tree of objects, at which point
undo would store snapshots rather than inverse operations. Immutability is a
real property of the *engine snapshot* on the audio side (02-architecture.md),
which is a different object built from this one.

**Invariants are validated, not enforced in `__post_init__`.** A constructor
that raises makes an invalid state unrepresentable, which sounds strictly
better and is not: a command mid-edit legitimately passes through states that
do not satisfy the whole rule set. `validate()` instead returns *every*
problem with its location, which is the shape project_io needs to report a bad
file and the undo stack needs to refuse an edit before applying it.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from immersive.core.curves import Curve
from immersive.core.time import SAMPLE_RATE, Division

#: Id prefixes, by entity. Short rather than uuid because a `.3dim` is meant to
#: be diffable and hand-editable (D-13, F-2), and 36 characters in every clip
#: works against both. Uniqueness comes from minting against what the project
#: already holds, plus a validator check - a hand-editable format means a human
#: can introduce a duplicate that no minting strategy would have prevented.
MEDIA_PREFIX = "m"
CHANNEL_PREFIX = "c"
CLIP_PREFIX = "k"

#: The shortest a trim or a split leaves a clip: two of D-42's implicit
#: 32-sample fades end to end, so the two never overlap (D-98).
MIN_CLIP_LENGTH = 64

_ID_PATTERN = re.compile(r"^[mck]-[0-9a-f]{8}$")
_HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DEFAULT_RNG = random.Random()


class Interpolatable(StrEnum):
    """The automatable parameter names (F-28, D-35).

    Named so M4 and M6 cannot typo `"pos.x"` into a curve nobody reads.
    """

    POS_X = "pos.x"
    POS_Y = "pos.y"
    POS_Z = "pos.z"
    GAIN = "gain"
    PAN = "pan"


class FadeShape(StrEnum):
    LINEAR = "linear"
    EQUAL_POWER = "equal_power"

    def gain(self, t: float) -> float:
        """The gain a fade-in of this shape has `t` of the way through it,
        0 to 1; a fade-out is the same curve read backwards, `gain(1 - t)`.

        One function for what the clip draws and what the engine plays, so
        the two cannot disagree. Equal power is a quarter sine: two of them
        crossed have powers summing to one, which is what keeps a crossfade
        from dipping in the middle.
        """
        t = min(max(t, 0.0), 1.0)
        if self is FadeShape.EQUAL_POWER:
            return math.sin(t * math.pi / 2)
        return t


# --------------------------------------------------------------------------- #
# value types
# --------------------------------------------------------------------------- #


@dataclass
class Position:
    """Metres, listener at the origin facing +Y (03-data-model.md)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Fade:
    length: int = 0
    shape: FadeShape = FadeShape.LINEAR


@dataclass
class SnapSetting:
    enabled: bool = True
    division: Division = Division.SIXTEENTH
    triplet: bool = False


@dataclass
class HrtfRef:
    kind: str = "builtin"
    id: str = "sadie-d1"


@dataclass
class Distance:
    """`(ref_distance / max(r, min_distance)) ** rolloff` (D-21)."""

    rolloff: float = 1.0
    min_distance: float = 0.2
    ref_distance: float = 1.0


@dataclass
class Master:
    gain_db: float = 0.0
    limiter_on: bool = True


# --------------------------------------------------------------------------- #
# entities
# --------------------------------------------------------------------------- #


@dataclass
class MediaFile:
    """Metadata only. Nothing in M1 opens an audio file; M2 decodes.

    `path` is **absolute here and relative in the file** (D-71). The Entities
    block in 03-data-model.md describes the file, so it says relative; a
    project that has never been saved has nothing for a path to be relative
    to, which is why memory gets the other half of that pair.
    """

    id: str
    path: str
    name: str
    source_rate: int
    channels: int
    frames: int
    hash: str = ""

    #: Did `path` point at nothing when this project was loaded (F-3)? Derived
    #: from the filesystem, never serialised, and out of equality (D-72): two
    #: projects that differ only in whether their audio is currently plugged
    #: in are the same project, and M1's acceptance is that a saved and
    #: reloaded project compares equal - which must not depend on what happens
    #: to be on disk when the test runs.
    missing: bool = field(default=False, compare=False)


@dataclass
class Clip:
    id: str
    media_id: str
    start: int
    offset: int
    length: int
    gain_db: float = 0.0
    fade_in: Fade = field(default_factory=Fade)
    fade_out: Fade = field(default_factory=Fade)

    @property
    def end(self) -> int:
        """First sample after this clip."""
        return self.start + self.length


@dataclass
class Channel:
    """A track holding many clips, all emitting from one moving point (D-6).

    There is deliberately no `index`: a channel's position in
    `Project.channels` *is* its order (D-61). Two homes for one fact is what
    doc-system.md §2 exists to prevent, and a file where they disagreed would
    have no defined meaning.
    """

    id: str
    name: str
    color: str
    gain_db: float = 0.0
    mute: bool = False
    solo: bool = False
    hrtf_bypass: bool = False
    pan: float = 0.0
    snap_override: SnapSetting | None = None
    position: Position = field(default_factory=Position)
    automation: dict[str, Curve] = field(default_factory=dict)
    clips: list[Clip] = field(default_factory=list)


@dataclass
class Project:
    sample_rate: int = SAMPLE_RATE
    bpm: float = 120.0
    time_signature: tuple[int, int] = (4, 4)
    snap: SnapSetting = field(default_factory=SnapSetting)
    hrtf: HrtfRef = field(default_factory=HrtfRef)
    distance: Distance = field(default_factory=Distance)
    master: Master = field(default_factory=Master)
    media_pool: list[MediaFile] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)

    @property
    def length(self) -> int:
        """The end of the last clip on any channel; zero when there are none.

        Derived, never stored (D-53). Nothing has to be maintained when a clip
        moves, and there is no end marker that can disagree with the material.
        Automation reaching past the last clip does not extend this - a curve
        with nothing to move is not content.
        """
        return max(
            (clip.end for channel in self.channels for clip in channel.clips),
            default=0,
        )


# --------------------------------------------------------------------------- #
# ids
# --------------------------------------------------------------------------- #


def all_ids(project: Project) -> set[str]:
    """Every id the project currently holds."""
    ids = {media.id for media in project.media_pool}
    for channel in project.channels:
        ids.add(channel.id)
        ids.update(clip.id for clip in channel.clips)
    return ids


def mint_id(
    prefix: str, taken: Collection[str], rng: random.Random | None = None
) -> str:
    """A short id not already in `taken`.

    Eight hex digits with a retry, rather than more digits and a prayer: a bare
    32-bit space has roughly a 1% birthday collision at ten thousand clips,
    which is too close, while generate-check-regenerate has no such bound and
    costs nothing at these sizes.
    """
    source = rng if rng is not None else _DEFAULT_RNG
    while True:
        candidate = f"{prefix}-{source.getrandbits(32):08x}"
        if candidate not in taken:
            return candidate


def new_media_id(project: Project, rng: random.Random | None = None) -> str:
    return mint_id(MEDIA_PREFIX, all_ids(project), rng)


def new_channel_id(project: Project, rng: random.Random | None = None) -> str:
    return mint_id(CHANNEL_PREFIX, all_ids(project), rng)


def new_clip_id(project: Project, rng: random.Random | None = None) -> str:
    return mint_id(CLIP_PREFIX, all_ids(project), rng)


def new_channel(
    project: Project, palette: Sequence[str], rng: random.Random | None = None
) -> Channel:
    """The channel Add Channel makes: named and coloured in turn.

    Its colour is the palette colour after the last channel's own, wrapping
    after the end, so the turn follows the project rather than a counter kept
    beside it that Undo would also have to put back. A last colour not in the
    palette - picked by hand, or from another theme's palette - starts the
    turn at the channel count instead. The palette is the active theme's
    (D-75), passed in, so nothing here knows about themes.

    The name is `Channel N`, N one more than the count and raised past any
    name already taken.
    """
    if not palette:
        raise ValueError("a palette needs at least one colour")
    taken = {channel.name for channel in project.channels}
    number = len(project.channels) + 1
    while f"Channel {number}" in taken:
        number += 1

    colours = [colour.upper() for colour in palette]
    last = project.channels[-1].color.upper() if project.channels else None
    turn = (
        colours.index(last) + 1 if last in colours else len(project.channels)
    ) % len(palette)
    return Channel(new_channel_id(project, rng), f"Channel {number}", palette[turn])


# --------------------------------------------------------------------------- #
# derived facts
# --------------------------------------------------------------------------- #


def effective_snap(project: Project, channel: Channel) -> SnapSetting:
    """The snap setting that applies to `channel` (F-18).

    A channel's override wins outright, including when it disables snapping;
    `None` inherits the project's. One function so M3 and the commands cannot
    disagree about which one is in force.
    """
    return channel.snap_override if channel.snap_override is not None else project.snap


def audible(channels: Sequence[Channel]) -> list[bool]:
    """Which channels reach the bus, per D-62.

    Solo is additive, so several can be soloed at once and while any of them
    is, every non-soloed channel is silent. A channel that is both soloed and
    muted stays muted: mute is the more deliberate gesture, and somebody who
    muted a channel and then soloed it was auditioning the rest. Bypassed
    channels obey solo like any other - bypass is about spatialisation, not
    about the mix bus (D-33).

    A function over the whole list rather than a property on a channel,
    because the answer depends on the others.
    """
    soloing = any(channel.solo for channel in channels)
    return [not channel.mute and (channel.solo or not soloing) for channel in channels]


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Problem:
    """One reason a project is not well-formed, and where it is."""

    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def validate(project: Project) -> list[Problem]:
    """Every way `project` breaks the Rules in docs/03-data-model.md.

    Returns all of them rather than raising on the first, because a caller
    reporting a bad file wants the list and a caller refusing an edit wants to
    know it is non-empty. Empty means well-formed.
    """
    found: list[Problem] = []

    if project.sample_rate != SAMPLE_RATE:
        found.append(
            Problem(
                "project", f"sample_rate is {project.sample_rate}, not {SAMPLE_RATE}"
            )
        )
    if project.bpm <= 0:
        found.append(Problem("project", f"bpm is {project.bpm}"))
    if any(part <= 0 for part in project.time_signature):
        found.append(Problem("project", f"time_signature is {project.time_signature}"))

    seen: dict[str, str] = {}

    def claim(identifier: str, where: str) -> None:
        if not _ID_PATTERN.match(identifier):
            found.append(Problem(where, f"malformed id {identifier!r}"))
        if identifier in seen:
            found.append(
                Problem(where, f"id {identifier!r} is also used by {seen[identifier]}")
            )
        else:
            seen[identifier] = where

    media_frames: dict[str, int] = {}
    for index, media in enumerate(project.media_pool):
        where = f"media_pool[{index}]"
        claim(media.id, where)
        media_frames[media.id] = media.frames
        if media.frames < 0:
            found.append(Problem(where, f"frames is {media.frames}"))
        if media.channels not in (1, 2):
            found.append(Problem(where, f"channels is {media.channels}, not 1 or 2"))

    for index, channel in enumerate(project.channels):
        where = f"channels[{index}]"
        claim(channel.id, where)
        if not _HEX_COLOUR.match(channel.color):
            found.append(Problem(where, f"color {channel.color!r} is not #RRGGBB"))
        if not -1.0 <= channel.pan <= 1.0:
            found.append(Problem(where, f"pan is {channel.pan}, outside -1..+1"))

        for name, curve in channel.automation.items():
            if name not in set(Interpolatable):
                found.append(Problem(where, f"unknown automation key {name!r}"))
            found.extend(
                Problem(f"{where}.automation[{name!r}]", reason)
                for reason in curve.problems()
            )

        previous_end: int | None = None
        for position, clip in enumerate(channel.clips):
            clip_where = f"{where}.clips[{position}]"
            claim(clip.id, clip_where)

            if clip.media_id not in media_frames:
                found.append(
                    Problem(
                        clip_where, f"media_id {clip.media_id!r} is not in the pool"
                    )
                )
            elif clip.offset + clip.length > media_frames[clip.media_id]:
                found.append(
                    Problem(
                        clip_where,
                        f"offset + length is {clip.offset + clip.length}, past the "
                        f"media's {media_frames[clip.media_id]} frames",
                    )
                )
            if clip.offset < 0:
                found.append(Problem(clip_where, f"offset is {clip.offset}"))
            if clip.length <= 0:
                found.append(Problem(clip_where, f"length is {clip.length}"))
            if clip.start < 0:
                found.append(Problem(clip_where, f"start is {clip.start}"))
            # D-101: a gain curve rising and falling over the same samples
            # has no one meaning, so the two fades may meet but not cross.
            fades = (clip.fade_in.length, clip.fade_out.length)
            if min(fades) < 0:
                found.append(Problem(clip_where, f"fade lengths are {fades}"))
            elif sum(fades) > clip.length:
                found.append(
                    Problem(
                        clip_where,
                        f"fades of {fades[0]} and {fades[1]} overlap in a clip "
                        f"{clip.length} long",
                    )
                )

            if previous_end is not None and clip.start < previous_end:
                found.append(
                    Problem(
                        clip_where,
                        f"starts at {clip.start}, before the previous clip ends "
                        f"at {previous_end} — clips must be sorted and must not "
                        f"overlap",
                    )
                )
            previous_end = clip.end

    return found
