"""Writing a `.3dim`, and the properties the format promises.

Phase 5 step 1 is the writer only. What is asserted here is everything that
can be settled without a reader: that two saves of one project produce the
same bytes, that the file says which build wrote it and carries no clock, and
that the four places the schema diverges from the dataclasses are actually
handled rather than accidentally right.

Deliberately *not* round-trip tests. A writer and a reader that are wrong in
the same direction round-trip perfectly, which is why the assertions here read
the file rather than the model, and why step 6's hand-written fixture exists
at all.
"""

from __future__ import annotations

import copy
import json
import math
import os
from collections.abc import Iterator
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

import immersive
from immersive.core.curves import Curve, Handles, Interp, Keyframe
from immersive.core.io.project_io import (
    SCHEMA_VERSION,
    ProjectFileError,
    _path_for_file,
    save,
)
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
    Project,
    SnapSetting,
    validate,
)
from immersive.core.time import Division

KICK = "m-00000001"
STEM = "m-00000002"

#: Key names that would mean a clock got into the file (D-60). `time_signature`
#: is deliberately absent from this list - it is a fact about the music, not
#: about when someone pressed save.
CLOCK_KEYS = frozenset(
    {
        "created",
        "created_at",
        "date",
        "last_saved",
        "modified",
        "modified_at",
        "mtime",
        "saved",
        "saved_at",
        "timestamp",
        "written",
    }
)


def a_project(media_root: Path) -> Project:
    """A project reaching into every corner of the schema.

    Two media files, mono and stereo. One spatialised channel with its own
    snap override, automation on three parameters covering all three
    interpolations, handles facing both ways, and clips using both fade
    shapes. One bypassed channel with no automation, no override and a pan -
    which is the second channel in `03`'s own example, and the case that
    exists because a finished stereo stem must reach the output untouched.

    `media_root` is the directory the project file will be saved into, so the
    paths here are absolute (D-71) and land under it.
    """
    samples = media_root / "samples"
    project = Project(
        bpm=124.0,
        time_signature=(7, 8),
        snap=SnapSetting(enabled=True, division=Division.EIGHTH, triplet=True),
        hrtf=HrtfRef(kind="builtin", id="sadie-d1"),
        distance=Distance(rolloff=1.5, min_distance=0.25, ref_distance=2.0),
        master=Master(gain_db=-1.5, limiter_on=True),
        media_pool=[
            MediaFile(KICK, str(samples / "kick.wav"), "kick.wav", 44_100, 1, 12_480),
            MediaFile(
                STEM,
                str(samples / "backing.wav"),
                "backing.wav",
                48_000,
                2,
                5_760_000,
                hash="sha256:9c1d",
            ),
        ],
        channels=[
            Channel(
                "c-00000001",
                "Kick",
                "#A855F7",
                gain_db=-3.0,
                mute=False,
                solo=True,
                hrtf_bypass=False,
                pan=0.0,
                snap_override=SnapSetting(
                    enabled=False, division=Division.THIRTY_SECOND, triplet=False
                ),
                position=Position(0.0, 1.5, 0.25),
                automation={
                    "pos.x": Curve(
                        [
                            # ease, with an outgoing handle and no incoming one
                            Keyframe(
                                0,
                                -2.0,
                                Interp.EASE,
                                Handles(outgoing=(24_000.0, 0.0)),
                            ),
                            # linear, with the incoming handle that shapes the
                            # segment behind it
                            Keyframe(
                                192_000,
                                2.0,
                                Interp.LINEAR,
                                Handles(incoming=(-24_000.0, 0.5)),
                            ),
                            Keyframe(240_000, 2.0, Interp.HOLD),
                        ]
                    ),
                    # an ease keyframe whose handles are present and both zero
                    "gain": Curve([Keyframe(0, 0.0, Interp.EASE, Handles())]),
                    "pos.z": Curve([]),
                },
                clips=[
                    Clip(
                        "k-00000001",
                        KICK,
                        start=0,
                        offset=120,
                        length=11_000,
                        gain_db=0.0,
                        fade_in=Fade(64, FadeShape.LINEAR),
                        fade_out=Fade(512, FadeShape.EQUAL_POWER),
                    ),
                    Clip("k-00000002", KICK, start=48_000, offset=0, length=12_480),
                ],
            ),
            Channel(
                "c-00000002",
                "Backing mix",
                "#22D3EE",
                hrtf_bypass=True,
                pan=-0.25,
                snap_override=None,
                clips=[Clip("k-00000003", STEM, start=0, offset=0, length=5_760_000)],
            ),
        ],
    )
    # A fixture that quietly goes invalid makes every test below fail for the
    # wrong reason, and `save` refuses it before any of them get a chance.
    assert validate(project) == []
    return project


def written(project: Project, path: Path) -> str:
    save(project, path)
    return path.read_text(encoding="utf-8")


def walk(node: Any, where: str = "") -> Iterator[tuple[str, Any]]:
    """Every value in a parsed document, with its location."""
    yield where or ".", node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{where}.{key}" if where else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{where}[{index}]")


def keys_of(node: Any) -> Iterator[tuple[str, list[str]]]:
    """Every object in a parsed document, as (location, its key order)."""
    for where, value in walk(node):
        if isinstance(value, dict):
            yield where, list(value.keys())


# --------------------------------------------------------------------------- #
# the file is stable
# --------------------------------------------------------------------------- #


def test_two_saves_of_one_project_are_byte_identical(tmp_path: Path) -> None:
    """D-13: a project that rewrites itself every save is unusable in git."""
    project = a_project(tmp_path)
    first = written(project, tmp_path / "a.3dim")
    second = written(project, tmp_path / "a.3dim")
    assert first == second


def test_two_equal_projects_write_the_same_bytes(tmp_path: Path) -> None:
    """The same assertion against a separate object.

    Saving one project twice would still pass if the writer cached the text it
    produced, or if some part of the document were built once at import. A
    deep copy shares nothing with the original but its values.
    """
    project = a_project(tmp_path)
    twin = copy.deepcopy(project)
    assert written(project, tmp_path / "a.3dim") == written(twin, tmp_path / "b.3dim")


def test_every_object_in_the_file_has_its_keys_sorted(tmp_path: Path) -> None:
    """`sort_keys`, asserted on the file rather than on the call that made it.

    Dropping it is the mutation that makes two saves differ, and the test
    above would catch it only while dictionaries happened to be built in a
    stable order - which they are, which is exactly why it needs its own
    assertion.
    """
    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))
    unsorted = {
        where: order for where, order in keys_of(document) if order != sorted(order)
    }
    assert not unsorted, f"keys out of order: {unsorted}"


def test_the_file_is_utf8_json_ending_in_one_newline(tmp_path: Path) -> None:
    path = tmp_path / "a.3dim"
    project = a_project(tmp_path)
    project.channels[0].name = "Bläser — 低音"
    raw = written(project, path).encode("utf-8")

    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert b"\r\n" not in raw
    # ensure_ascii is off, so the name is in the file as itself rather than as
    # a row of escapes nobody can read in a diff.
    assert "Bläser — 低音" in path.read_text(encoding="utf-8")
    assert json.loads(raw.decode("utf-8"))["channels"][0]["name"] == "Bläser — 低音"


# --------------------------------------------------------------------------- #
# what the file says about itself
# --------------------------------------------------------------------------- #


def test_app_version_is_the_build_and_is_not_the_schema(tmp_path: Path) -> None:
    """D-60. Two builds can write schema 1 and disagree about a default."""
    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))

    assert document["app_version"] == immersive.__version__
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["app_version"] != document["schema_version"]
    # One is a build, the other drives migration. Collapsing them is the
    # mistake D-60 exists to prevent, and they do not even share a type.
    assert isinstance(document["app_version"], str)
    assert isinstance(document["schema_version"], int)


def test_nothing_in_the_file_is_a_timestamp(tmp_path: Path) -> None:
    """D-60: no clock anywhere, under any name.

    The byte-identity tests above are what actually bite - a timestamp cannot
    survive them. This one names the failure, so that a `modified` field
    added later reads as the decision it broke rather than as two saves
    mysteriously differing.
    """
    text = written(a_project(tmp_path), tmp_path / "a.3dim")
    document = json.loads(text)

    named = {
        where
        for where, value in walk(document)
        if isinstance(value, dict)
        for key in value
        if key.lower() in CLOCK_KEYS
    }
    assert not named, f"clock-shaped keys in the file: {named}"
    assert "time_signature" in document, "the guard above must not be vacuous"


# --------------------------------------------------------------------------- #
# the four places the file diverges from the dataclasses
# --------------------------------------------------------------------------- #


def test_enums_are_written_as_their_values(tmp_path: Path) -> None:
    """Written by `.value`, never by `repr`.

    A `StrEnum` is a `str`, so `json` happens to write the value even if the
    writer is careless - which makes this a test that the carelessness has not
    been replaced by something worse, like an f-string.
    """
    text = written(a_project(tmp_path), tmp_path / "a.3dim")
    document = json.loads(text)

    for leaked in ("Interp.", "FadeShape.", "Division.", "Interpolatable."):
        assert leaked not in text

    channel = document["channels"][0]
    assert channel["snap_override"]["division"] == "1/32"
    assert document["snap"]["division"] == "1/8"
    assert channel["clips"][0]["fade_out"]["shape"] == "equal_power"
    assert channel["automation"]["pos.x"]["keyframes"][0]["interp"] == "ease"
    assert channel["automation"]["pos.x"]["keyframes"][2]["interp"] == "hold"


def test_time_signature_is_a_json_array_of_two_ints(tmp_path: Path) -> None:
    """JSON has no tuple, and a list read back as a list breaks equality."""
    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))
    assert document["time_signature"] == [7, 8]
    assert isinstance(document["time_signature"], list)
    assert all(isinstance(part, int) for part in document["time_signature"])


def test_handles_are_out_and_in_and_a_zero_handle_is_absent(tmp_path: Path) -> None:
    """`in` is a Python keyword, so the model spells them out and this maps back.

    Swapping the two is the mutation that survives every structural test and
    changes what a curve sounds like after a reload, so the directions are
    asserted by sign: an outgoing handle leads forward in time and an incoming
    one reaches backwards.
    """
    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))
    keyframes = document["channels"][0]["automation"]["pos.x"]["keyframes"]

    assert keyframes[0]["handles"] == {"out": [24_000.0, 0.0]}
    assert keyframes[1]["handles"] == {"in": [-24_000.0, 0.5]}
    assert keyframes[0]["handles"]["out"][0] > 0
    assert keyframes[1]["handles"]["in"][0] < 0

    # Present but empty when both handles are zero, absent when the keyframe
    # has none at all: the file distinguishes the two exactly as the model does.
    zeroed = document["channels"][0]["automation"]["gain"]["keyframes"][0]
    assert zeroed["handles"] == {}
    assert "handles" not in keyframes[2]


def test_missing_is_never_written(tmp_path: Path) -> None:
    """D-72: it is derived from the filesystem, so writing it would make the
    file depend on which machine saved it."""
    project = a_project(tmp_path)
    plugged_in = written(project, tmp_path / "a.3dim")

    project.media_pool[0].missing = True
    unplugged = written(project, tmp_path / "b.3dim")

    assert plugged_in == unplugged
    assert "missing" not in plugged_in
    carrying = [
        where for where, order in keys_of(json.loads(plugged_in)) if "missing" in order
    ]
    assert not carrying


def test_missing_is_outside_equality(tmp_path: Path) -> None:
    """The other half of D-72, and the reason M1's acceptance can be trusted.

    Two projects differing only in whether their audio is currently plugged in
    are the same project. If they were not, "saved and reloaded and compared
    equal" would depend on what happens to be on disk when the test runs.
    """
    project = a_project(tmp_path)
    twin = copy.deepcopy(project)
    twin.media_pool[0].missing = True
    assert project == twin


# --------------------------------------------------------------------------- #
# numbers
# --------------------------------------------------------------------------- #


def test_float_fields_are_written_as_floats(tmp_path: Path) -> None:
    """An int in a float field writes as `0`, not `0.0`.

    It round-trips and it compares equal, so only the file shows it - and a
    file that has drifted from the schema in `03` is one a person editing it
    by hand gets wrong.
    """
    project = a_project(tmp_path)
    project.bpm = 120
    project.channels[0].gain_db = -3
    project.master.gain_db = 0
    document = json.loads(written(project, tmp_path / "a.3dim"))

    assert isinstance(document["bpm"], float)
    assert isinstance(document["channels"][0]["gain_db"], float)
    assert isinstance(document["master"]["gain_db"], float)
    # Sample counts stay integers - they are counts, not measurements.
    assert isinstance(document["sample_rate"], int)
    assert isinstance(document["channels"][0]["clips"][0]["start"], int)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_number_is_refused_and_located(tmp_path: Path, bad: float) -> None:
    """`json` writes `NaN` and `Infinity` by default and they are not JSON.

    A file Python can read and nothing else can is worse than a save that
    refuses, so the value is reported - with enough of a location to find it,
    which the bare `ValueError` from `allow_nan=False` does not give.
    """
    project = a_project(tmp_path)
    project.channels[0].automation["pos.x"].keyframes[1].value = bad
    path = tmp_path / "a.3dim"

    with pytest.raises(ProjectFileError) as raised:
        save(project, path)

    assert not path.exists()
    where = [problem.where for problem in raised.value.problems]
    assert where == ["channels[0].automation.pos.x.keyframes[1].value"]


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #


def test_media_paths_are_relative_to_the_project_file(tmp_path: Path) -> None:
    """D-71, the ordinary case. Step 3 owns the fallbacks and the reader."""
    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))
    paths = [media["path"] for media in document["media_pool"]]

    assert paths == ["samples/kick.wav", "samples/backing.wav"]
    assert all("\\" not in path for path in paths)


def test_a_windows_separator_is_normalised_on_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N-6: a project saved on Windows has to open on Linux.

    The one assertion in this file that reaches for a private name, and the
    reason is the same one that makes the different-drive fallback a simulated
    test: the behaviour is real, and the platform that exercises it is not the
    one this runs on. Turning `\\` into `/` is a no-op wherever `os.sep` is
    already `/`, so deleting the conversion outright leaves every other test
    here green while writing a file that opens on exactly one platform.
    """
    monkeypatch.setattr(os.path, "relpath", lambda *_: r"samples\kick.wav")
    written_path = _path_for_file("ignored", Path("ignored"), PureWindowsPath)
    assert written_path == "samples/kick.wav"


def test_the_path_is_relative_to_the_project_not_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutation that makes a project open only from where it was saved.

    Computing against the working directory passes every test run from the
    project's own folder, which is where anyone would run one by hand.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    document = json.loads(written(a_project(tmp_path), tmp_path / "a.3dim"))
    assert [media["path"] for media in document["media_pool"]] == [
        "samples/kick.wav",
        "samples/backing.wav",
    ]


# --------------------------------------------------------------------------- #
# failing without damage
# --------------------------------------------------------------------------- #


def test_an_invalid_project_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    """`validate()` is the gate, so a file on disk can be trusted by `load`."""
    project = a_project(tmp_path)
    project.channels[0].clips[1].start = 0  # now overlapping the first clip
    path = tmp_path / "a.3dim"

    with pytest.raises(ProjectFileError) as raised:
        save(project, path)

    assert not path.exists()
    assert raised.value.problems == validate(project)
    assert "overlap" in str(raised.value)


def test_a_refused_save_leaves_the_previous_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "a.3dim"
    good = written(a_project(tmp_path), path)

    broken = a_project(tmp_path)
    broken.channels[0].pan = 4.0
    with pytest.raises(ProjectFileError):
        save(broken, path)

    assert path.read_text(encoding="utf-8") == good


def test_a_save_that_fails_at_the_last_step_does_not_truncate_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutation: writing in place rather than through `os.replace`.

    A plain `open(path, "w")` empties the file before the new bytes arrive, so
    an interruption anywhere in the write destroys the project that was
    already there. Failing the replace is the closest a test can get to being
    interrupted, and it distinguishes the two implementations exactly: the
    atomic one leaves the old file whole.
    """
    path = tmp_path / "a.3dim"
    project = a_project(tmp_path)
    good = written(project, path)

    def refuse(self: Path, target: Any) -> Path:
        raise OSError("interrupted")

    monkeypatch.setattr(Path, "replace", refuse)
    project.bpm = 130.0
    with pytest.raises(OSError, match="interrupted"):
        save(project, path)

    assert path.read_text(encoding="utf-8") == good
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["a.3dim"]


def test_a_successful_save_leaves_no_temporary_behind(tmp_path: Path) -> None:
    save(a_project(tmp_path), tmp_path / "a.3dim")
    save(a_project(tmp_path), tmp_path / "a.3dim")
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["a.3dim"]
