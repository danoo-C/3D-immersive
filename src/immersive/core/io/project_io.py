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
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePath
from typing import Any

import immersive
from immersive.core.curves import Curve, Handles, Keyframe
from immersive.core.model import (
    Channel,
    Clip,
    Distance,
    Fade,
    HrtfRef,
    Master,
    MediaFile,
    Position,
    Problem,
    Project,
    SnapSetting,
    validate,
)

#: The on-disk schema this build writes, and what drives forward migration on
#: load. It is deliberately **not** `app_version` (D-60): two builds can both
#: write schema 1 and still disagree about a default, so the version that
#: wrote a file is recorded separately and drives nothing.
SCHEMA_VERSION = 1


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
    document = _document(project, destination.parent)

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
