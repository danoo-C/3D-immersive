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
import shutil
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
    load,
    save,
)
from immersive.core.model import (
    Channel,
    Clip,
    Distance,
    Fade,
    FadeShape,
    HrtfRef,
    Interpolatable,
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


# --------------------------------------------------------------------------- #
# the reader, and the milestone's own acceptance
# --------------------------------------------------------------------------- #


def every_field_project(media_root: Path) -> Project:
    """A project touching every corner of the schema at once.

    Deliberately not `a_project` above, which is shaped like something someone
    might make. This one is shaped like the *format*: every `StrEnum` member,
    every automatable parameter, a curve with no keyframes, an absent snap
    override and a present one, media inside the project's directory and
    media outside it, and a handle in each of the four shapes the file can
    write. `test_the_round_trip_fixture_is_exhaustive` is what stops it
    quietly covering less than it claims.
    """
    samples = media_root / "samples"
    outside = media_root.parent / "shared"
    pool = [
        MediaFile(KICK, str(samples / "kick.wav"), "kick.wav", 44_100, 1, 96_000),
        MediaFile(
            STEM,
            str(samples / "backing.wav"),
            "backing.wav",
            48_000,
            2,
            5_760_000,
            hash="sha256:9c1d",
        ),
        MediaFile("m-00000003", str(outside / "loop.wav"), "loop.wav", 96_000, 2, 480),
    ]

    # The project's own snap takes the first division; one channel takes each
    # of the rest, and the last has none at all.
    divisions = list(Division)
    channels = [
        Channel(
            "c-00000001",
            "Everything",
            "#A855F7",
            gain_db=-3.5,
            mute=True,
            solo=True,
            hrtf_bypass=False,
            pan=0.75,
            snap_override=SnapSetting(True, divisions[1], triplet=True),
            position=Position(-1.25, 1.5, 0.5),
            automation={
                # ease then linear then hold, with an out-only handle, an
                # in-only handle, and a keyframe carrying none
                "pos.x": Curve(
                    [
                        Keyframe(
                            0, -2.0, Interp.EASE, Handles(outgoing=(24_000.0, 1.0))
                        ),
                        Keyframe(
                            96_000,
                            2.0,
                            Interp.LINEAR,
                            Handles(incoming=(-1_000.0, -0.5)),
                        ),
                        Keyframe(192_000, 0.0, Interp.HOLD),
                    ]
                ),
                # both handles on one keyframe
                "pos.y": Curve(
                    [
                        Keyframe(
                            0,
                            1.0,
                            Interp.EASE,
                            Handles(outgoing=(500.0, 0.25), incoming=(-500.0, -0.25)),
                        ),
                        Keyframe(48_000, 3.0, Interp.LINEAR),
                    ]
                ),
                # a curve with nothing in it: legal, and falls back to position
                "pos.z": Curve([]),
                # handles present and both zero, which is not the same as none
                "gain": Curve([Keyframe(0, -6.0, Interp.EASE, Handles())]),
                "pan": Curve([Keyframe(0, -1.0), Keyframe(24_000, 1.0)]),
            },
            clips=[
                Clip(
                    "k-00000001",
                    KICK,
                    start=0,
                    offset=120,
                    length=11_000,
                    gain_db=-1.5,
                    fade_in=Fade(64, FadeShape.LINEAR),
                    fade_out=Fade(512, FadeShape.EQUAL_POWER),
                ),
                Clip("k-00000002", KICK, start=48_000, offset=0, length=96_000),
            ],
        )
    ]
    for index, division in enumerate(divisions[2:], start=2):
        channels.append(
            Channel(
                f"c-0000000{index}",
                f"Channel {index}",
                "#22D3EE",
                snap_override=SnapSetting(False, division, triplet=index % 2 == 0),
            )
        )
    channels.append(
        Channel(
            "c-00000009",
            "Backing mix",
            "#3B82F6",
            hrtf_bypass=True,
            pan=-0.25,
            snap_override=None,  # inherits the project's
            automation={},  # empty, not absent
            clips=[Clip("k-00000003", STEM, start=0, offset=0, length=5_760_000)],
        )
    )

    project = Project(
        bpm=137.5,
        time_signature=(7, 8),
        snap=SnapSetting(True, divisions[0], triplet=False),
        hrtf=HrtfRef(kind="file", id="ari-nh2"),
        distance=Distance(rolloff=1.75, min_distance=0.15, ref_distance=2.5),
        master=Master(gain_db=-2.25, limiter_on=False),
        media_pool=pool,
        channels=channels,
    )
    assert validate(project) == []
    return project


def enums_used(project: Project) -> dict[str, set[Any]]:
    """Which members of each enum the project actually holds."""
    used: dict[str, set[Any]] = {
        "division": {project.snap.division},
        "interp": set(),
        "shape": set(),
        "parameter": set(),
    }
    for channel in project.channels:
        if channel.snap_override is not None:
            used["division"].add(channel.snap_override.division)
        used["parameter"].update(channel.automation)
        for curve in channel.automation.values():
            used["interp"].update(keyframe.interp for keyframe in curve.keyframes)
        for clip in channel.clips:
            used["shape"].update({clip.fade_in.shape, clip.fade_out.shape})
    return used


def test_the_round_trip_fixture_is_exhaustive(tmp_path: Path) -> None:
    """The acceptance below is only worth what this asserts.

    "Every `StrEnum` member" is a claim the fixture makes and this checks. A
    member added later - a new grid division, a new fade shape - arrives with
    no round-trip coverage and nothing to say so, which is the failure this
    exists to make loud.
    """
    project = every_field_project(tmp_path)
    used = enums_used(project)

    assert used["division"] == set(Division)
    assert used["interp"] == set(Interp)
    assert used["shape"] == set(FadeShape)
    assert used["parameter"] == {member.value for member in Interpolatable}

    handles = [
        keyframe.handles
        for channel in project.channels
        for curve in channel.automation.values()
        for keyframe in curve.keyframes
    ]
    assert Handles(outgoing=(24_000.0, 1.0)) in handles, "no out-only handle"
    assert Handles(incoming=(-1_000.0, -0.5)) in handles, "no in-only handle"
    assert Handles() in handles, "no present-but-zero handles"
    assert None in handles, "no keyframe without handles"
    assert any(
        not curve.keyframes for c in project.channels for curve in c.automation.values()
    ), "no empty curve"
    assert any(c.automation == {} for c in project.channels), "no empty automation"
    assert any(c.snap_override is None for c in project.channels), "no absent override"


def test_a_project_saved_and_reloaded_compares_equal(tmp_path: Path) -> None:
    """M1's acceptance, in the words of the roadmap.

    Everything in phase 1 that made equality load-bearing was for this line.
    """
    project = every_field_project(tmp_path)
    path = tmp_path / "everything.3dim"
    save(project, path)

    result = load(path)

    assert result.project == project
    assert result.problems == []


def test_the_other_fixture_also_reloads_equal(tmp_path: Path) -> None:
    """A second shape, because one project is one arrangement of the schema."""
    project = a_project(tmp_path)
    path = tmp_path / "a.3dim"
    save(project, path)
    assert load(path).project == project


def test_save_load_save_is_byte_identical(tmp_path: Path) -> None:
    """The assertion equality cannot make.

    A reader and a writer wrong in the same direction round-trip perfectly -
    swap `out` and `in` in both and every value comes home. Going back out to
    the file is what notices, because the second file has to match the first
    one rather than the model they both agree about.
    """
    project = every_field_project(tmp_path)
    first = tmp_path / "first.3dim"
    second = tmp_path / "second.3dim"

    save(project, first)
    save(load(first).project, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_time_signature_comes_back_a_tuple(tmp_path: Path) -> None:
    """JSON has no tuple, and a list here fails equality on the type alone."""
    path = tmp_path / "a.3dim"
    save(every_field_project(tmp_path), path)
    reloaded = load(path).project

    assert reloaded.time_signature == (7, 8)
    assert isinstance(reloaded.time_signature, tuple)


def test_an_absent_snap_override_comes_back_as_none(tmp_path: Path) -> None:
    """`null` means inherit the project's, which is what `None` means (F-18)."""
    path = tmp_path / "a.3dim"
    save(every_field_project(tmp_path), path)
    reloaded = load(path).project

    assert reloaded.channels[-1].snap_override is None
    assert reloaded.channels[0].snap_override is not None


def test_empty_automation_and_empty_curves_survive(tmp_path: Path) -> None:
    """An empty curve is not the same as no curve, and neither is an error."""
    path = tmp_path / "a.3dim"
    save(every_field_project(tmp_path), path)
    reloaded = load(path).project

    assert reloaded.channels[-1].automation == {}
    assert reloaded.channels[0].automation["pos.z"].keyframes == []
    assert "pos.z" in reloaded.channels[0].automation


def test_handles_survive_in_all_four_shapes(tmp_path: Path) -> None:
    """Out only, in only, present and zero, and absent entirely.

    Asserted by direction rather than by value, because swapping `out` and
    `in` on both sides survives every other test in this file and changes
    what a curve does after a reload.
    """
    path = tmp_path / "a.3dim"
    project = every_field_project(tmp_path)
    save(project, path)
    automation = load(path).project.channels[0].automation

    x = automation["pos.x"].keyframes
    assert x[0].handles == Handles(outgoing=(24_000.0, 1.0))
    assert x[1].handles == Handles(incoming=(-1_000.0, -0.5))
    assert x[2].handles is None
    assert automation["pos.y"].keyframes[0].handles == Handles(
        outgoing=(500.0, 0.25), incoming=(-500.0, -0.25)
    )
    assert automation["gain"].keyframes[0].handles == Handles()

    # The property the swap would break, stated as a property.
    assert x[0].handles is not None and x[0].handles.outgoing[0] > 0
    assert x[1].handles is not None and x[1].handles.incoming[0] < 0


def test_a_reloaded_curve_evaluates_the_same(tmp_path: Path) -> None:
    """Equality compares numbers; this compares what they are for.

    A handle swap that survived equality would still show up here, and so
    would a keyframe order quietly reversed by the reader.
    """
    path = tmp_path / "a.3dim"
    project = every_field_project(tmp_path)
    save(project, path)
    reloaded = load(path).project

    for name in ("pos.x", "pos.y", "gain", "pan"):
        before = project.channels[0].automation[name]
        after = reloaded.channels[0].automation[name]
        assert before.sample(0, 192_000, 97) == after.sample(0, 192_000, 97)


def test_media_paths_come_back_absolute(tmp_path: Path) -> None:
    """D-71's other half. Relative on disk, absolute in memory.

    Including media that lives outside the project's own directory, which is
    written with `../` segments and must normalise back to where it started
    rather than to a path with `..` still in it.
    """
    path = tmp_path / "a.3dim"
    project = every_field_project(tmp_path)
    save(project, path)
    reloaded = load(path).project

    for before, after in zip(project.media_pool, reloaded.media_pool, strict=True):
        assert Path(after.path).is_absolute()
        assert ".." not in Path(after.path).parts
        assert after.path == before.path

    written_paths = [
        media["path"]
        for media in json.loads(path.read_text(encoding="utf-8"))["media_pool"]
    ]
    assert written_paths[2].startswith("../"), "the off-tree case is not covered"


# --------------------------------------------------------------------------- #
# paths: moved projects, off-tree media, and the two fallbacks
# --------------------------------------------------------------------------- #


def a_project_with_its_audio(root: Path) -> Project:
    """A one-clip project whose media really exists under `root`."""
    (root / "samples").mkdir(parents=True, exist_ok=True)
    (root / "samples" / "kick.wav").write_bytes(b"not really audio")
    return Project(
        media_pool=[
            MediaFile(
                KICK, str(root / "samples" / "kick.wav"), "kick.wav", 48_000, 1, 480
            )
        ],
        channels=[
            Channel(
                "c-00000001",
                "Kick",
                "#A855F7",
                clips=[Clip("k-00000001", KICK, start=0, offset=0, length=480)],
            )
        ],
    )


def test_a_project_and_its_audio_survive_being_moved(tmp_path: Path) -> None:
    """D-13's whole point, and the reason paths are relative on disk.

    Not "the path string round-trips" - the project is picked up and put down
    somewhere else, which is what someone does when they move a folder onto a
    different machine or a different drive.
    """
    here = tmp_path / "here"
    here.mkdir()
    save(a_project_with_its_audio(here), here / "mix.3dim")

    there = tmp_path / "there"
    shutil.move(str(here), str(there))

    reloaded = load(there / "mix.3dim").project
    media = reloaded.media_pool[0]

    assert Path(media.path) == there / "samples" / "kick.wav"
    assert Path(media.path).is_file(), "the project cannot find its own audio"


def test_a_moved_project_saves_the_same_relative_paths(tmp_path: Path) -> None:
    """The file after the move says what it said before it.

    A reader that resolved paths against the *old* directory would still find
    the audio on the first load and then write an absolute path back out,
    which is how a project stops being portable one save at a time.
    """
    here = tmp_path / "here"
    here.mkdir()
    save(a_project_with_its_audio(here), here / "mix.3dim")
    before = (here / "mix.3dim").read_text(encoding="utf-8")

    there = tmp_path / "there"
    shutil.move(str(here), str(there))
    save(load(there / "mix.3dim").project, there / "mix.3dim")

    assert (there / "mix.3dim").read_text(encoding="utf-8") == before


def test_a_hand_typed_relative_path_resolves_against_the_project(
    tmp_path: Path,
) -> None:
    """`samples/kick.wav` in the file means "beside this project".

    Written by hand rather than by `save`, because this is the one assertion
    that must not go through the writer: it is what someone reading `03` would
    type, and the whole value of the format being JSON rests on it working.
    """
    (tmp_path / "samples").mkdir()
    path = tmp_path / "mix.3dim"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "app_version": "0.1.0",
                "media_pool": [
                    {
                        "id": KICK,
                        "path": "samples/kick.wav",
                        "name": "kick.wav",
                        "source_rate": 48000,
                        "channels": 1,
                        "frames": 480,
                    }
                ],
                "channels": [],
            }
        ),
        encoding="utf-8",
    )

    media = load(path).project.media_pool[0]
    assert Path(media.path) == tmp_path / "samples" / "kick.wav"
    assert Path(media.path).is_absolute()


def test_media_outside_the_project_directory_round_trips(tmp_path: Path) -> None:
    """`../..` is ordinary, not exotic - a shared sample folder beside the mix.

    `Path.relative_to` cannot express it, which is why the writer uses
    `os.path.relpath`, and the reader has to normalise it back or the same
    file comes home as a different string.
    """
    here = tmp_path / "projects" / "mix"
    here.mkdir(parents=True)
    shared = tmp_path / "shared"
    shared.mkdir()

    project = Project(
        media_pool=[
            MediaFile(KICK, str(shared / "kick.wav"), "kick.wav", 48_000, 1, 480)
        ]
    )
    path = here / "mix.3dim"
    save(project, path)

    written_path = json.loads(path.read_text(encoding="utf-8"))["media_pool"][0]["path"]
    assert written_path == "../../shared/kick.wav"

    reloaded = load(path).project
    assert reloaded == project
    assert ".." not in Path(reloaded.media_pool[0].path).parts


def test_a_path_with_no_relative_form_is_written_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows, two drives. Simulated, because CI is Linux.

    `os.path.relpath` raises there rather than returning anything, and the
    choice is between a save that fails and a project that is merely not
    portable. The project is the one that is true, so the absolute path is
    written and the save succeeds.
    """
    project = a_project_with_its_audio(tmp_path)
    absolute = project.media_pool[0].path
    path = tmp_path / "mix.3dim"

    def no_relative_form(*_: object) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", no_relative_form)
    save(project, path)

    written_path = json.loads(path.read_text(encoding="utf-8"))["media_pool"][0]["path"]
    assert written_path == Path(absolute).as_posix()
    assert Path(written_path).is_absolute()


def test_an_absolute_path_in_the_file_is_read_as_itself(tmp_path: Path) -> None:
    """The other end of the fallback above.

    An absolute path is not joined onto the project directory, because
    rewriting it relative to somewhere it does not live would turn a project
    that merely is not portable into one that is wrong.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    absolute = elsewhere / "kick.wav"
    path = tmp_path / "deep" / "mix.3dim"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "app_version": "0.1.0",
                "media_pool": [
                    {
                        "id": KICK,
                        "path": absolute.as_posix(),
                        "name": "kick.wav",
                        "source_rate": 48000,
                        "channels": 1,
                        "frames": 480,
                    }
                ],
                "channels": [],
            }
        ),
        encoding="utf-8",
    )

    media = load(path).project.media_pool[0]
    assert Path(media.path) == absolute
    assert "deep" not in Path(media.path).parts, "it was joined onto the project"


def test_a_symlinked_project_directory_is_not_resolved_through(
    tmp_path: Path,
) -> None:
    """A project inside a symlink keeps the path the person typed.

    `resolve()` would rewrite every media path to point at wherever the link
    happens to lead, which is somewhere they never typed and may not recognise
    - and on a shared drive mounted at two paths it silently changes which one
    the project refers to.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # Windows without the privilege
        pytest.skip("this platform will not create a directory symlink")

    save(a_project_with_its_audio(link), link / "mix.3dim")
    media = load(link / "mix.3dim").project.media_pool[0]

    assert Path(media.path) == link / "samples" / "kick.wav"
    assert "real" not in Path(media.path).parts
    assert Path(media.path).is_file(), "the link still has to lead to the audio"


def test_a_symlinked_project_writes_the_plain_relative_path(tmp_path: Path) -> None:
    """Not resolving has to hold on the *writing* side too.

    A writer that resolves the project's directory but not the media's
    computes the path between a link and its target, and still round-trips -
    the reader undoes it on the way back. What it leaves behind is a file
    saying `../link/samples/kick.wav` where `samples/kick.wav` was meant,
    which stops being portable the moment the folder moves. The file is the
    only place that shows it, so the file is where this looks.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform will not create a directory symlink")

    path = link / "mix.3dim"
    save(a_project_with_its_audio(link), path)

    written_path = json.loads(path.read_text(encoding="utf-8"))["media_pool"][0]["path"]
    assert written_path == "samples/kick.wav"


def test_a_project_saved_by_a_relative_name_still_loads_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`save(project, "sub/mix.3dim")` is a perfectly ordinary call.

    Its directory is `sub`, which is relative, and D-71 says media paths are
    absolute in memory - so the project file's own location has to be made
    absolute before anything is measured against it. Without that the media
    path comes back relative to the working directory, and the first time
    something opens the project from anywhere else the audio is gone.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    project = a_project_with_its_audio(tmp_path / "sub")

    save(project, "sub/mix.3dim")
    media = load("sub/mix.3dim").project.media_pool[0]

    assert Path(media.path).is_absolute()
    assert Path(media.path) == tmp_path / "sub" / "samples" / "kick.wav"
    assert load("sub/mix.3dim").project == project
