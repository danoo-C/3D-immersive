"""`.3dim` — writing a project to a file, and reading it back.

The schema itself is owned by the *Project file* section of
docs/03-data-model.md. This module implements it, and it is the only thing in
`core` that touches the filesystem at all.

**The mapping is written out by hand, not derived.** `dataclasses.asdict()`
over the type hints would be shorter and is the obvious first idea. It does
not survive contact with that schema, which diverges from the dataclasses in
four places reflection cannot guess: `Handles.outgoing` and `.incoming` are
`out` and `in` in the file, because `in` is a Python keyword; `time_signature`
is a tuple in memory and a JSON array on disk; the `StrEnum`s serialise as
their values and have to be reconstructed deliberately; and `MediaFile.missing`
is derived from the filesystem at load and is never written at all (D-72). A
reflective writer would need all four exceptions anyway, and an exception
buried inside reflection is harder to read than the whole explicit version.
The explicit one also breaks loudly when the model gains a field and nobody
updated the schema, which is the failure you want.

**`validate()` is the gate at both ends.** A project it rejects is not
written, and a file that produces one is not opened. That is the rule
`commands.py` already applies to every edit, and it is what lets each end
trust the other: the undo stack can assume a loaded project is well-formed,
and a reader can assume anything on disk was well-formed when it was written.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

import immersive
from immersive.core.curves import Curve, Handles, Interp, Keyframe
from immersive.core.model import (
    Channel,
    Clip,
    Distance,
    Fade,
    FadeShape,
    HrtfRef,
    Master,
    MediaFile,
    Position,
    Problem,
    Project,
    SnapSetting,
    validate,
)
from immersive.core.time import SAMPLE_RATE, Division

#: The on-disk schema this build writes, and what drives forward migration on
#: load. It is deliberately **not** `app_version` (D-60): two builds can both
#: write schema 1 and still disagree about a default, so the version that
#: wrote a file is recorded separately and drives nothing.
SCHEMA_VERSION = 1

#: What a project file is called. The format's, so it lives with the format.
SUFFIX = ".3dim"

#: How a document written by an older schema is brought up to the current one:
#: `version -> a function returning the *next* version's document`, applied one
#: step at a time.
#:
#: Empty, because `SCHEMA_VERSION` has never been anything but 1 - and present
#: anyway, because the alternative is that the first real migration is also the
#: redesign that introduces migrations, at the moment when there are already
#: projects in the world that need it. A registry with nothing in it costs a
#: dozen lines now; retrofitting one costs a format change later.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ProjectFileError(Exception):
    """There is no project here, and these are all the reasons why.

    Carries `Problem`s rather than a single message, for the reason
    `validate()` returns a list: a bad file usually has more than one thing
    wrong with it, and a report that stops at the first turns fixing it into a
    conversation.
    """

    def __init__(self, summary: str, problems: Sequence[Problem]) -> None:
        self.problems = list(problems)
        detail = "\n".join(f"  {problem}" for problem in self.problems)
        super().__init__(f"{summary}\n{detail}" if detail else summary)


# --------------------------------------------------------------------------- #
# model -> document
# --------------------------------------------------------------------------- #


def _number(value: float) -> float:
    """A JSON number for a field the schema writes as a float.

    An `int` sitting in a float field serialises as `0` rather than `0.0`. It
    round-trips, and it compares equal afterwards, so nothing on this side
    would ever catch it - but it does not match the listing in `03`, and the
    only test that *can* catch it is a fixture someone types by hand. Coercing
    on write is cheaper than remembering.
    """
    return float(value)


def _position(position: Position) -> dict[str, Any]:
    return {
        "x": _number(position.x),
        "y": _number(position.y),
        "z": _number(position.z),
    }


def _fade(fade: Fade) -> dict[str, Any]:
    return {"length": fade.length, "shape": fade.shape.value}


def _snap(snap: SnapSetting) -> dict[str, Any]:
    return {
        "enabled": snap.enabled,
        "division": snap.division.value,
        "triplet": snap.triplet,
    }


def _hrtf(hrtf: HrtfRef) -> dict[str, Any]:
    return {"kind": hrtf.kind, "id": hrtf.id}


def _distance(distance: Distance) -> dict[str, Any]:
    return {
        "rolloff": _number(distance.rolloff),
        "min_distance": _number(distance.min_distance),
        "ref_distance": _number(distance.ref_distance),
    }


def _master(master: Master) -> dict[str, Any]:
    return {"gain_db": _number(master.gain_db), "limiter_on": master.limiter_on}


def _handles(handles: Handles) -> dict[str, Any]:
    """`out` and `in`, each key absent when its handle is zero.

    `03`'s worked example writes only `out` on the keyframe that starts an
    ease segment and only `in` on the one that ends it, and that is the shape
    that falls out of how curves are read: a segment is shaped by the left
    keyframe's `outgoing` and the right one's `incoming`, so the other two are
    zero and never looked at. Writing them anyway would be lossless and would
    make every saved project disagree with the documented example for nothing.
    """
    written: dict[str, Any] = {}
    if handles.outgoing != (0.0, 0.0):
        written["out"] = [_number(part) for part in handles.outgoing]
    if handles.incoming != (0.0, 0.0):
        written["in"] = [_number(part) for part in handles.incoming]
    return written


def _keyframe(keyframe: Keyframe) -> dict[str, Any]:
    written: dict[str, Any] = {
        "t": keyframe.t,
        "value": _number(keyframe.value),
        "interp": keyframe.interp.value,
    }
    # Absent rather than null when there are none: `03` shows `handles` only
    # on an ease keyframe, and an explicit null would have to mean the same
    # thing as the key not being there.
    if keyframe.handles is not None:
        written["handles"] = _handles(keyframe.handles)
    return written


def _curve(curve: Curve) -> dict[str, Any]:
    return {"keyframes": [_keyframe(keyframe) for keyframe in curve.keyframes]}


def _media(media: MediaFile, project_directory: Path) -> dict[str, Any]:
    # No `missing`: it is derived from the filesystem at load (D-72), and
    # writing it would make the file depend on which machine saved it.
    return {
        "id": media.id,
        "path": _path_for_file(media.path, project_directory),
        "name": media.name,
        "source_rate": media.source_rate,
        "channels": media.channels,
        "frames": media.frames,
        "hash": media.hash,
    }


def _clip(clip: Clip) -> dict[str, Any]:
    return {
        "id": clip.id,
        "media_id": clip.media_id,
        "start": clip.start,
        "offset": clip.offset,
        "length": clip.length,
        "gain_db": _number(clip.gain_db),
        "fade_in": _fade(clip.fade_in),
        "fade_out": _fade(clip.fade_out),
    }


def _channel(channel: Channel) -> dict[str, Any]:
    # No `index`: a channel's place in the list is its order (D-61).
    return {
        "id": channel.id,
        "name": channel.name,
        "color": channel.color,
        "gain_db": _number(channel.gain_db),
        "mute": channel.mute,
        "solo": channel.solo,
        "hrtf_bypass": channel.hrtf_bypass,
        "pan": _number(channel.pan),
        "snap_override": (
            None if channel.snap_override is None else _snap(channel.snap_override)
        ),
        "position": _position(channel.position),
        "automation": {
            name: _curve(curve) for name, curve in channel.automation.items()
        },
        "clips": [_clip(clip) for clip in channel.clips],
    }


def _document(project: Project, project_directory: Path) -> dict[str, Any]:
    """The whole project as the plain structures `json` can write.

    Deliberately no timestamp anywhere (D-60). A `modified` field would change
    on every save and produce a diff even when nothing about the music did,
    which costs exactly the git-friendliness D-13 was for. The filesystem
    already knows when the file was written.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": immersive.__version__,
        "sample_rate": project.sample_rate,
        "bpm": _number(project.bpm),
        # A list, not a tuple: JSON has no tuple, so the reader has to rebuild
        # one or round-trip equality fails on the type alone.
        "time_signature": list(project.time_signature),
        "snap": _snap(project.snap),
        "hrtf": _hrtf(project.hrtf),
        "distance": _distance(project.distance),
        "master": _master(project.master),
        "media_pool": [
            _media(media, project_directory) for media in project.media_pool
        ],
        "channels": [_channel(channel) for channel in project.channels],
    }


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #


def _directory_of(project_file: Path) -> Path:
    """The directory a project file sits in: absolute, and not resolved.

    Absolute because a media path made relative to a *relative* directory is
    relative to the working directory instead of to the project, which is the
    mutation that produces a project openable only from where it was saved.
    Not `resolve()`d, because a project inside a symlinked directory should
    keep the path the person typed rather than gain one pointing somewhere
    they have never seen.
    """
    return project_file.absolute().parent


def _path_for_file(
    media_path: str,
    project_directory: Path,
    flavour: type[PurePath] = PurePath,
) -> str:
    """`media_path` as the file carries it: relative to the project, `/`-separated.

    D-71, and each half of it is load-bearing. `os.path.relpath` rather than
    `Path.relative_to`, which cannot express `../..` and so cannot describe
    media living outside the project's own directory - which is ordinary, not
    exotic. Not `resolve()` either: a project inside a symlinked directory
    keeps the path the person typed rather than one pointing somewhere they
    have never seen.

    On Windows, media on a different drive has no relative form at all and
    `relpath` raises. That project is not portable, which is a fact about the
    project rather than a failure of the save, so the absolute path is written
    and the save succeeds.

    `as_posix` last, so a project saved on Windows opens on Linux. `flavour`
    exists only so that can be asserted from anywhere: on a POSIX machine the
    conversion is a no-op, because `os.sep` is already `/` - so removing it
    altogether leaves a Linux test run entirely green while producing a file
    that opens on one platform. Defaulted to the platform's own, and passed
    explicitly only by the test that has to pretend to be the other one.
    """
    try:
        relative = os.path.relpath(media_path, project_directory)
    except ValueError:
        return flavour(media_path).as_posix()
    return flavour(relative).as_posix()


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #


def _non_finite(node: Any, where: str) -> Iterator[Problem]:
    """Every value JSON cannot express, and where in the document it sits.

    `allow_nan=False` already refuses to write these, but it raises a
    `ValueError` naming neither the field nor the value, which is the wrong
    end of a bug report. Walking the built document first costs one pass over
    a structure that is about to be serialised anyway, and turns "out of range
    float" into the name of the curve somebody divided by zero.
    """
    if isinstance(node, float) and not math.isfinite(node):
        yield Problem(where or "project", f"{node} cannot be written as JSON")
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _non_finite(value, f"{where}.{key}" if where else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _non_finite(value, f"{where}[{index}]")


def _write_atomically(destination: Path, text: str) -> None:
    r"""Write `text` to `destination` so an interrupted save cannot truncate it.

    A plain `open(destination, "w")` empties the existing file before the new
    bytes arrive, so a crash mid-save destroys the project that was already
    there - the one case where saving is worse than not saving at all. The
    temporary file sits in the same directory because `os.replace` is atomic
    only within a filesystem, and the system temporary directory is routinely
    a different one.

    `newline="\n"` rather than the platform default: a `.3dim` is meant to
    diff cleanly in git (D-13), and text mode on Windows would rewrite every
    line ending, so the same project would differ by the platform that saved
    it.
    """
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed below, by name
        "w",
        encoding="utf-8",
        newline="\n",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def save(project: Project, path: str | os.PathLike[str]) -> None:
    """Write `project` to `path` as a `.3dim`.

    Refuses a project `validate()` rejects, and writes nothing in that case.
    Refusing is deliberate: being able to save a project the undo stack says
    cannot exist is worth less than `load` being able to trust what it opens.
    """
    problems = validate(project)
    if problems:
        raise ProjectFileError(
            f"this project is not well-formed, so {os.fspath(path)} was not written",
            problems,
        )

    destination = Path(path)
    document = _document(project, _directory_of(destination))

    unwritable = list(_non_finite(document, ""))
    if unwritable:
        raise ProjectFileError(
            f"this project holds values JSON cannot express, so "
            f"{os.fspath(path)} was not written",
            unwritable,
        )

    # `sort_keys` is what makes two saves of one project byte-identical and a
    # change to one field a one-line diff (D-13). `ensure_ascii=False` because
    # the format is UTF-8 and a channel called "Bläser" should read as one in
    # git rather than as six escapes.
    text = json.dumps(
        document,
        sort_keys=True,
        indent=2,
        allow_nan=False,
        ensure_ascii=False,
    )
    _write_atomically(destination, text + "\n")


# --------------------------------------------------------------------------- #
# document -> model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LoadResult:
    """A project, and what was wrong with the file that was not fatal.

    The problems here are the survivable kind - audio that is not where the
    project says it is (F-3), which leaves the project itself perfectly
    usable and is M8's to relink. Anything meaning there is no project at all
    raises `ProjectFileError` instead, so a caller that never looks at
    `problems` still cannot end up holding a half-built project.

    Nothing puts anything in it yet: every problem a `.3dim` can currently
    have is fatal, and missing media is the first that will not be.
    """

    project: Project
    problems: list[Problem]


def _shown(value: Any) -> str:
    """A value as an error message should carry it.

    The type on its own - "color is int, not str" - does not say which field
    somebody typed a number into when a channel has several. The value does,
    and it matters more here than it usually would: a field the reader
    rejects falls back to its default and is then reported a *second* time by
    `validate()`, which describes the default rather than what was typed. Two
    true statements about one mistake is fine; two statements where neither
    names the value is not.
    """
    shown = repr(value)
    return shown if len(shown) <= 40 else f"{shown[:37]}..."


def _type_name(kind: type | tuple[type, ...]) -> str:
    if isinstance(kind, tuple):
        return " or ".join(one.__name__ for one in kind)
    return kind.__name__


class _Reading:
    """One pass over a parsed document, and the problems it found.

    An object rather than a list threaded through twenty functions: every
    reader below needs somewhere to record "this key is the wrong type" and
    the location it was at, and passing both into each of them is the kind of
    noise that gets dropped at one call site and noticed by nobody.

    Reading is deliberately lenient *while it runs* - a bad field is recorded
    and replaced by its default so the pass carries on and finds the rest.
    Whether any of it is fatal is decided once, at the end, by `load`. That is
    `validate()`'s rule again: somebody reporting a bad file wants the list,
    not the first line of it.

    A key that is simply **absent** is not a problem. A file written before a
    field existed loads with that field's default, which is what makes adding
    one a non-breaking change and what the migration hook rests on. A key that
    is present and wrong *is* a problem, because guessing what someone meant
    by a string where a number belongs is how a half-built project is returned
    to a caller who believed it.
    """

    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def note(self, where: str, message: str) -> None:
        self.problems.append(Problem(where, message))

    def _present(
        self,
        node: dict[str, Any],
        key: str,
        where: str,
        kind: type | tuple[type, ...],
        required: bool,
    ) -> Any:
        """`node[key]` when it is there and of the right type, else `None`."""
        if key not in node:
            if required:
                self.note(where, f"{key} is missing")
            return None
        found = node[key]
        # `bool` is an `int` in Python, and it is never what a numeric field
        # in this schema meant - so it is rejected before `isinstance` can
        # quietly accept `true` as 1.
        wrong_bool = isinstance(found, bool) and kind is not bool
        if wrong_bool or not isinstance(found, kind):
            self.note(where, f"{key} is {_shown(found)}, not {_type_name(kind)}")
            return None
        return found

    def text(
        self, node: dict[str, Any], key: str, where: str, default: str = ""
    ) -> str:
        found = self._present(node, key, where, str, required=default is None)
        return default if found is None else str(found)

    def required_text(self, node: dict[str, Any], key: str, where: str) -> str:
        found = self._present(node, key, where, str, required=True)
        return "" if found is None else str(found)

    def flag(self, node: dict[str, Any], key: str, where: str, default: bool) -> bool:
        found = self._present(node, key, where, bool, required=False)
        return default if found is None else bool(found)

    def integer(
        self,
        node: dict[str, Any],
        key: str,
        where: str,
        default: int,
        required: bool = False,
    ) -> int:
        """A sample count or a length.

        A whole-numbered float is accepted and narrowed. The format is meant
        to be hand-editable (F-2), and somebody typing `0.0` into a field
        `03` shows as a count has been unambiguous about what they meant;
        `0.5` has not, and is reported rather than truncated into a number
        nobody chose.
        """
        found = self._present(node, key, where, (int, float), required=required)
        if found is None:
            return default
        if isinstance(found, float):
            if not found.is_integer():
                self.note(where, f"{key} is {found}, which is not a whole number")
                return default
            return int(found)
        return int(found)

    def number(
        self,
        node: dict[str, Any],
        key: str,
        where: str,
        default: float,
        required: bool = False,
    ) -> float:
        found = self._present(node, key, where, (int, float), required=required)
        return default if found is None else float(found)

    def member(
        self,
        node: dict[str, Any],
        key: str,
        where: str,
        kind: type[Division] | type[Interp] | type[FadeShape],
        default: Any,
    ) -> Any:
        """A `StrEnum`, back from the value it was written as."""
        found = self._present(node, key, where, str, required=False)
        if found is None:
            return default
        try:
            return kind(found)
        except ValueError:
            allowed = ", ".join(repr(one.value) for one in kind)
            self.note(where, f"{key} is {found!r}, not one of {allowed}")
            return default

    def mapping(self, node: dict[str, Any], key: str, where: str) -> dict[str, Any]:
        found = self._present(node, key, where, dict, required=False)
        return {} if found is None else dict(found)

    def sequence(self, node: dict[str, Any], key: str, where: str) -> list[Any]:
        found = self._present(node, key, where, list, required=False)
        return [] if found is None else list(found)

    def objects(
        self, node: dict[str, Any], key: str, where: str
    ) -> list[tuple[dict[str, Any], str]]:
        """A list of objects, each with the location to report it at.

        Anything in the list that is not an object is reported and dropped,
        so one malformed clip does not take the rest of the channel with it -
        and `load` still refuses the file, because the problem was recorded.
        """
        found = []
        for index, item in enumerate(self.sequence(node, key, where)):
            at = f"{where}.{key}[{index}]" if where else f"{key}[{index}]"
            if isinstance(item, dict):
                found.append((item, at))
            else:
                self.note(at, f"is {type(item).__name__}, not an object")
        return found


def _read_position(reading: _Reading, node: dict[str, Any], where: str) -> Position:
    return Position(
        x=reading.number(node, "x", where, 0.0),
        y=reading.number(node, "y", where, 0.0),
        z=reading.number(node, "z", where, 0.0),
    )


def _read_fade(reading: _Reading, node: dict[str, Any], where: str) -> Fade:
    return Fade(
        length=reading.integer(node, "length", where, 0),
        shape=reading.member(node, "shape", where, FadeShape, FadeShape.LINEAR),
    )


def _read_snap(reading: _Reading, node: dict[str, Any], where: str) -> SnapSetting:
    return SnapSetting(
        enabled=reading.flag(node, "enabled", where, True),
        division=reading.member(node, "division", where, Division, Division.SIXTEENTH),
        triplet=reading.flag(node, "triplet", where, False),
    )


def _read_hrtf(reading: _Reading, node: dict[str, Any], where: str) -> HrtfRef:
    return HrtfRef(
        kind=reading.text(node, "kind", where, "builtin"),
        id=reading.text(node, "id", where, "sadie-d1"),
    )


def _read_distance(reading: _Reading, node: dict[str, Any], where: str) -> Distance:
    return Distance(
        rolloff=reading.number(node, "rolloff", where, 1.0),
        min_distance=reading.number(node, "min_distance", where, 0.2),
        ref_distance=reading.number(node, "ref_distance", where, 1.0),
    )


def _read_master(reading: _Reading, node: dict[str, Any], where: str) -> Master:
    return Master(
        gain_db=reading.number(node, "gain_db", where, 0.0),
        limiter_on=reading.flag(node, "limiter_on", where, True),
    )


def _read_handle(
    reading: _Reading, node: dict[str, Any], key: str, where: str
) -> tuple[float, float]:
    """One `[dt, dv]` pair, or zero when the key is not there.

    Absent means zero displacement, which is what `curves.py` already does
    with a handle it has not been given - so the file's "either key may be
    absent" and the model's `(0.0, 0.0)` are the same statement.
    """
    if key not in node:
        return (0.0, 0.0)
    pair = node[key]
    numbers = (
        isinstance(pair, list)
        and len(pair) == 2
        and all(
            isinstance(part, int | float) and not isinstance(part, bool)
            for part in pair
        )
    )
    if not numbers:
        reading.note(where, f"handles {key} is {pair!r}, not a pair of numbers")
        return (0.0, 0.0)
    return (float(pair[0]), float(pair[1]))


def _read_keyframe(reading: _Reading, node: dict[str, Any], where: str) -> Keyframe:
    handles = None
    if "handles" in node:
        found = reading.mapping(node, "handles", where)
        handles = Handles(
            outgoing=_read_handle(reading, found, "out", where),
            incoming=_read_handle(reading, found, "in", where),
        )
    return Keyframe(
        t=reading.integer(node, "t", where, 0, required=True),
        value=reading.number(node, "value", where, 0.0, required=True),
        interp=reading.member(node, "interp", where, Interp, Interp.LINEAR),
        handles=handles,
    )


def _read_curve(reading: _Reading, node: dict[str, Any], where: str) -> Curve:
    return Curve(
        keyframes=[
            _read_keyframe(reading, keyframe, at)
            for keyframe, at in reading.objects(node, "keyframes", where)
        ]
    )


def _read_media(
    reading: _Reading, node: dict[str, Any], where: str, project_directory: Path
) -> MediaFile:
    return MediaFile(
        id=reading.required_text(node, "id", where),
        path=_path_in_memory(
            reading.required_text(node, "path", where), project_directory
        ),
        name=reading.required_text(node, "name", where),
        source_rate=reading.integer(node, "source_rate", where, 0, required=True),
        channels=reading.integer(node, "channels", where, 0, required=True),
        frames=reading.integer(node, "frames", where, 0, required=True),
        hash=reading.text(node, "hash", where, ""),
    )


def _read_clip(reading: _Reading, node: dict[str, Any], where: str) -> Clip:
    return Clip(
        id=reading.required_text(node, "id", where),
        media_id=reading.required_text(node, "media_id", where),
        start=reading.integer(node, "start", where, 0, required=True),
        offset=reading.integer(node, "offset", where, 0, required=True),
        length=reading.integer(node, "length", where, 0, required=True),
        gain_db=reading.number(node, "gain_db", where, 0.0),
        fade_in=_read_fade(
            reading, reading.mapping(node, "fade_in", where), f"{where}.fade_in"
        ),
        fade_out=_read_fade(
            reading, reading.mapping(node, "fade_out", where), f"{where}.fade_out"
        ),
    )


def _read_channel(reading: _Reading, node: dict[str, Any], where: str) -> Channel:
    # `snap_override` distinguishes null from absent the way the model
    # distinguishes `None` from a setting: null means "inherit the project's",
    # and so does not being there at all.
    override = None
    if node.get("snap_override") is not None:
        override = _read_snap(
            reading,
            reading.mapping(node, "snap_override", where),
            f"{where}.snap_override",
        )

    automation = {}
    for name, curve in reading.mapping(node, "automation", where).items():
        at = f"{where}.automation[{name!r}]"
        if isinstance(curve, dict):
            automation[name] = _read_curve(reading, curve, at)
        else:
            reading.note(at, f"is {type(curve).__name__}, not an object")

    return Channel(
        id=reading.required_text(node, "id", where),
        name=reading.required_text(node, "name", where),
        color=reading.required_text(node, "color", where),
        gain_db=reading.number(node, "gain_db", where, 0.0),
        mute=reading.flag(node, "mute", where, False),
        solo=reading.flag(node, "solo", where, False),
        hrtf_bypass=reading.flag(node, "hrtf_bypass", where, False),
        pan=reading.number(node, "pan", where, 0.0),
        snap_override=override,
        position=_read_position(
            reading, reading.mapping(node, "position", where), f"{where}.position"
        ),
        automation=automation,
        clips=[
            _read_clip(reading, clip, at)
            for clip, at in reading.objects(node, "clips", where)
        ],
    )


def _read_time_signature(
    reading: _Reading, node: dict[str, Any], where: str
) -> tuple[int, int]:
    """`[num, den]` back into the tuple the model holds.

    A tuple, not the list JSON hands over: `Project.time_signature` is typed
    as one, `time.py` unpacks it as one, and a project reloaded with a list
    there compares unequal to the one that was saved - which would fail M1's
    acceptance for a reason that has nothing to do with the music.
    """
    if "time_signature" not in node:
        return (4, 4)
    pair = reading.sequence(node, "time_signature", where)
    whole = [
        part for part in pair if isinstance(part, int) and not isinstance(part, bool)
    ]
    if len(whole) != 2 or len(pair) != 2:
        reading.note(where, f"time_signature is {pair!r}, not two whole numbers")
        return (4, 4)
    return (whole[0], whole[1])


def _path_in_memory(stored: str, project_directory: Path) -> str:
    """The absolute path `stored` names, given where the project file is (D-71).

    The other half of `_path_for_file`. `normpath` rather than `resolve()` for
    the same reason the writer does not resolve either - a project inside a
    symlinked directory keeps the path the person typed - but normalising is
    not optional: media written as `../audio/kick.wav` would otherwise come
    back as a project directory with `..` still in it, and a reloaded project
    would not compare equal to the one that was saved.

    An absolute path in the file is left alone. That is what the writer
    produces when there is no relative form to write - media on another
    Windows drive - and rewriting it relative to somewhere it does not live
    would turn a project that merely is not portable into one that is wrong.
    """
    return os.path.normpath(Path(project_directory, stored))


def _read_project(
    reading: _Reading, document: dict[str, Any], project_directory: Path
) -> Project:
    """Every key the current schema knows, and **only** those (D-73).

    Anything else in the file is dropped rather than carried: the model has
    nowhere to put untyped data that `validate()` cannot check and the undo
    stack cannot edit. The cost is that opening a newer project in an older
    build and saving it loses what the newer build added, which is why the
    version gate exists.
    """
    return Project(
        sample_rate=reading.integer(document, "sample_rate", "project", SAMPLE_RATE),
        bpm=reading.number(document, "bpm", "project", 120.0),
        time_signature=_read_time_signature(reading, document, "project"),
        snap=_read_snap(
            reading, reading.mapping(document, "snap", "project"), "project.snap"
        ),
        hrtf=_read_hrtf(
            reading, reading.mapping(document, "hrtf", "project"), "project.hrtf"
        ),
        distance=_read_distance(
            reading,
            reading.mapping(document, "distance", "project"),
            "project.distance",
        ),
        master=_read_master(
            reading, reading.mapping(document, "master", "project"), "project.master"
        ),
        media_pool=[
            _read_media(reading, media, at, project_directory)
            for media, at in reading.objects(document, "media_pool", "")
        ],
        channels=[
            _read_channel(reading, channel, at)
            for channel, at in reading.objects(document, "channels", "")
        ],
    )


def _migrated(document: dict[str, Any], where: Path) -> dict[str, Any]:
    """`document`, brought up to `SCHEMA_VERSION` one step at a time.

    The version is read before anything else is parsed, and that ordering is
    the point of the whole mechanism. A schema 4 file opened by a build that
    reads schema 1 would otherwise fail somewhere deep inside a field that
    changed meaning between them, and the report would describe the symptom -
    "channels[2].pan is a string" - rather than the cause. Refusing by version
    says the one true thing: this file is newer than this application.

    The step counter is this function's own, not the document's. A migration
    that forgets to update `schema_version` is a bug in that migration, and
    it should not be able to express itself as an infinite loop here.
    """
    version = document.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProjectFileError(
            f"{where} does not say which schema it was written with",
            [Problem("schema_version", f"is {version!r}, not a whole number")],
        )
    if version > SCHEMA_VERSION:
        raise ProjectFileError(
            f"{where} was written by a newer build of this application",
            [
                Problem(
                    "schema_version",
                    f"is {version}, and this build reads {SCHEMA_VERSION}",
                )
            ],
        )

    while version < SCHEMA_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            raise ProjectFileError(
                f"{where} cannot be brought up to date",
                [
                    Problem(
                        "schema_version",
                        f"there is no migration from schema {version}",
                    )
                ],
            )
        document = migrate(document)
        version += 1
    return document


def _missing_media(project: Project) -> list[Problem]:
    """Media the project points at that is not on this machine (F-3, D-72).

    Marked rather than refused. A clip whose audio has gone must survive -
    the arrangement is still every decision someone made, and losing it
    because a sample moved would be the format destroying work it was meant
    to preserve. Relinking is M8's; being openable without the audio is this
    phase's.

    The mark is set here and never written (D-72), which is what keeps a
    project from depending on which machine last saved it.
    """
    found = []
    for index, media in enumerate(project.media_pool):
        media.missing = not Path(media.path).is_file()
        if media.missing:
            found.append(Problem(f"media_pool[{index}]", f"{media.path} is not there"))
    return found


def load(path: str | os.PathLike[str]) -> LoadResult:
    """Read a `.3dim` back into a project.

    The inverse of `save`, and held to it by test: a project saved and
    reloaded compares equal, and saving what was loaded reproduces the file
    byte for byte. The second is what catches a reader and a writer that are
    wrong in the same direction, which the first cannot.

    Refuses anything `validate()` rejects, for the same reason `save` does -
    a project the undo stack guarantees cannot exist should not arrive
    through the filesystem instead.

    Two kinds of failure, deliberately kept apart. A file that is not a
    project raises `ProjectFileError` with every reason it is not. A file that
    cannot be read at all - absent, a directory, no permission - raises the
    `OSError` the filesystem raised, unwrapped: that is not a fact about the
    format, and M3's open dialog wants the errno rather than a paraphrase.

    Missing *media* is neither (F-3). The project loads, the `MediaFile` is
    marked, and the problem comes back in `LoadResult.problems` for something
    later to show.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as undecodable:
        raise ProjectFileError(
            f"{source} is not UTF-8 text",
            [Problem(f"byte {undecodable.start}", undecodable.reason)],
        ) from undecodable

    try:
        document = json.loads(text)
    except json.JSONDecodeError as broken:
        raise ProjectFileError(
            f"{source} is not valid JSON",
            [Problem(f"line {broken.lineno}, column {broken.colno}", broken.msg)],
        ) from broken

    if not isinstance(document, dict):
        raise ProjectFileError(
            f"{source} does not hold a project",
            [Problem("", f"the file is a JSON {type(document).__name__}")],
        )

    reading = _Reading()
    project = _read_project(reading, _migrated(document, source), _directory_of(source))

    problems = reading.problems + validate(project)
    if problems:
        raise ProjectFileError(
            f"{source} is not a project that can be opened", problems
        )
    # Only once the project itself is known good: media that is not on this
    # machine is a fact about the machine, and reporting it alongside a
    # malformed clip would suggest they are the same kind of trouble.
    return LoadResult(project, _missing_media(project))
