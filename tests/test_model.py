"""The project model matches docs/03-data-model.md, and says when it does not.

No Qt, no audio device — this is N-5 in practice, and tests/test_layering.py
is what keeps it that way.
"""

from __future__ import annotations

import random
import re
from dataclasses import fields
from pathlib import Path

import pytest

from immersive.core.curves import Curve, Handles, Interp, Keyframe
from immersive.core.model import (
    CHANNEL_PREFIX,
    CLIP_PREFIX,
    MEDIA_PREFIX,
    SAMPLE_RATE,
    Channel,
    Clip,
    Division,
    Fade,
    FadeShape,
    HrtfRef,
    Interpolatable,
    MediaFile,
    Position,
    Project,
    SnapSetting,
    all_ids,
    audible,
    mint_id,
    new_channel,
    new_channel_id,
    new_clip_id,
    new_media_id,
    validate,
)

DATA_MODEL = Path(__file__).resolve().parent.parent / "docs" / "03-data-model.md"


# --------------------------------------------------------------------------- #
# the documentation and the code agree
# --------------------------------------------------------------------------- #


def documented_fields() -> dict[str, list[str]]:
    """Parse the Entities block of 03-data-model.md into {entity: [field, …]}.

    Deliberately forgiving about everything except the field names: the block
    is a human-readable diagram first, and a parser that breaks when someone
    realigns a comment would be worse than no parser at all. If this ever does
    become fragile, replace it with an explicit list *in this file* — a
    duplicated list that fails loudly beats a clever parser that fails
    confusingly.
    """
    text = DATA_MODEL.read_text(encoding="utf-8")
    block = re.search(r"## Entities\n\n```\n(.*?)\n```", text, re.S)
    assert block, "no Entities block in 03-data-model.md"

    entities: dict[str, list[str]] = {}
    current = None
    for line in block.group(1).splitlines():
        if not line.strip():
            continue
        if re.match(r"^\w", line):
            current = line.strip()
            entities[current] = []
        elif found := re.match(r"^[├└]── (\w+)", line):
            assert current is not None
            entities[current].append(found.group(1))
    return entities


ENTITIES = {
    "Project": Project,
    "MediaFile": MediaFile,
    "Channel": Channel,
    "Clip": Clip,
    "Curve": Curve,
    "Keyframe": Keyframe,
}


def test_the_entities_block_lists_what_the_code_has() -> None:
    """Every entity in 03 exists here with exactly the fields it lists.

    This is the test that stops the document and the model drifting. It has
    caught one already: 03 said MediaFile.id was a uuid while its example used
    hand-written mnemonics, and neither was implementable.
    """
    documented = documented_fields()
    assert set(documented) == set(ENTITIES), "03 and this test disagree on entities"

    for name, cls in ENTITIES.items():
        actual = [f.name for f in fields(cls)]
        assert actual == documented[name], (
            f"{name}: 03 lists {documented[name]}, the dataclass has {actual}"
        )


def test_channel_has_no_index() -> None:
    """D-61: list order is the order, and there is no second home for it."""
    assert "index" not in {f.name for f in fields(Channel)}


# --------------------------------------------------------------------------- #
# ids
# --------------------------------------------------------------------------- #


def test_minted_ids_are_unique_in_bulk() -> None:
    rng = random.Random(0)
    minted = {mint_id(CLIP_PREFIX, set(), rng) for _ in range(10_000)}
    # Collisions are possible in a 32-bit space at this count — the point is
    # that mint_id is asked to avoid what it has already produced.
    taken: set[str] = set()
    for _ in range(10_000):
        taken.add(mint_id(CLIP_PREFIX, taken, rng))
    assert len(taken) == 10_000
    assert all(re.match(rf"^{CLIP_PREFIX}-[0-9a-f]{{8}}$", i) for i in minted)


def test_minting_avoids_what_the_project_already_holds() -> None:
    """A retry, not more digits — the retry is what makes eight safe."""

    class Stubborn(random.Random):
        """Returns the same value twice, then a different one."""

        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def getrandbits(self, k: int) -> int:
            self.calls += 1
            return 0xDEADBEEF if self.calls < 3 else 0x0000002A

    project = Project(
        media_pool=[MediaFile("m-deadbeef", "a.wav", "a.wav", 48_000, 1, 10)]
    )
    assert new_media_id(project, Stubborn()) == "m-0000002a"


def test_ids_are_unique_across_kinds_not_just_within_them() -> None:
    project = _project()
    assert len(all_ids(project)) == 1 + 1 + 1  # media, channel, clip


def test_each_kind_gets_its_own_prefix() -> None:
    project = Project()
    rng = random.Random(1)
    assert new_media_id(project, rng).startswith(f"{MEDIA_PREFIX}-")
    assert new_channel_id(project, rng).startswith(f"{CHANNEL_PREFIX}-")
    assert new_clip_id(project, rng).startswith(f"{CLIP_PREFIX}-")


# --------------------------------------------------------------------------- #
# derived facts
# --------------------------------------------------------------------------- #


def _media(frames: int = 1_000) -> MediaFile:
    return MediaFile("m-00000001", "a.wav", "a.wav", 48_000, 1, frames)


def _clip(start: int, length: int, identifier: str = "k-00000001") -> Clip:
    return Clip(identifier, "m-00000001", start, 0, length)


def _project() -> Project:
    return Project(
        media_pool=[_media()],
        channels=[Channel("c-00000001", "Kick", "#A855F7", clips=[_clip(0, 100)])],
    )


def test_length_is_the_last_clip_end() -> None:
    project = Project(
        media_pool=[_media()],
        channels=[
            Channel("c-00000001", "A", "#A855F7", clips=[_clip(0, 100, "k-00000001")]),
            Channel(
                "c-00000002", "B", "#22D3EE", clips=[_clip(500, 250, "k-00000002")]
            ),
        ],
    )
    assert project.length == 750


def test_length_is_zero_when_empty() -> None:
    assert Project().length == 0
    assert Project(channels=[Channel("c-00000001", "A", "#A855F7")]).length == 0


def test_automation_past_the_last_clip_does_not_extend_the_length() -> None:
    """D-53: a curve with nothing to move is not content."""
    project = _project()
    project.channels[0].automation[Interpolatable.POS_X] = Curve(
        [Keyframe(0, 0.0), Keyframe(10_000_000, 1.0)]
    )
    assert project.length == 100


def test_length_is_derived_not_stored() -> None:
    assert "length" not in {f.name for f in fields(Project)}


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        # (mute, solo) per channel -> audible per channel
        ([(False, False), (False, False)], [True, True]),
        ([(True, False), (False, False)], [False, True]),
        ([(False, True), (False, False)], [True, False]),
        # additive: two solos both sound
        ([(False, True), (False, True)], [True, True]),
        # mute wins on its own channel, even when soloed
        ([(True, True), (False, False)], [False, False]),
    ],
)
def test_solo_is_additive_and_mute_wins(
    states: list[tuple[bool, bool]], expected: list[bool]
) -> None:
    """D-62, as a table rather than as prose nobody re-reads."""
    channels = [
        Channel(f"c-0000000{i}", str(i), "#A855F7", mute=mute, solo=solo)
        for i, (mute, solo) in enumerate(states)
    ]
    assert audible(channels) == expected


def test_bypassed_channels_obey_solo() -> None:
    """Bypass is about spatialisation, not the mix bus (D-33)."""
    channels = [
        Channel("c-00000001", "A", "#A855F7", hrtf_bypass=True),
        Channel("c-00000002", "B", "#22D3EE", solo=True),
    ]
    assert audible(channels) == [False, True]


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def test_a_well_formed_project_has_no_problems() -> None:
    assert validate(_project()) == []


def _first_problem(project: Project) -> str:
    problems = validate(project)
    assert problems, "expected a problem and found none"
    return str(problems[0])


def test_overlapping_clips_are_reported_with_their_position() -> None:
    project = _project()
    project.channels[0].clips.append(_clip(50, 100, "k-00000002"))
    message = _first_problem(project)
    assert "clips[1]" in message and "overlap" in message


def test_a_clip_past_the_end_of_its_media_is_reported() -> None:
    project = _project()
    project.channels[0].clips[0].length = 5_000
    assert "past the media's 1000 frames" in _first_problem(project)


def test_a_dangling_media_id_is_reported() -> None:
    project = _project()
    project.channels[0].clips[0].media_id = "m-ffffffff"
    assert "not in the pool" in _first_problem(project)


def test_a_duplicate_id_is_reported_with_both_locations() -> None:
    """A hand-editable format means a human can introduce one."""
    project = _project()
    project.channels[0].id = "m-00000001"
    message = _first_problem(project)
    assert "also used by" in message and "media_pool[0]" in message


def test_a_malformed_id_is_reported() -> None:
    project = _project()
    project.channels[0].id = "channel-one"
    assert "malformed id" in _first_problem(project)


def test_a_curve_with_repeated_times_is_reported() -> None:
    project = _project()
    project.channels[0].automation[Interpolatable.GAIN] = Curve(
        [Keyframe(0, 0.0), Keyframe(0, 1.0)]
    )
    assert "duplicate keyframe times" in _first_problem(project)


def test_an_unknown_automation_key_is_reported() -> None:
    project = _project()
    project.channels[0].automation["pos.w"] = Curve()
    assert "unknown automation key" in _first_problem(project)


def test_fades_that_overlap_are_reported() -> None:
    """D-101: they may meet, and may not cross."""
    project = _project()
    clip = project.channels[0].clips[0]
    clip.fade_in, clip.fade_out = Fade(60), Fade(40)
    assert validate(project) == []

    clip.fade_out = Fade(41)
    message = _first_problem(project)
    assert "clips[0]" in message and "overlap" in message


def test_a_fade_longer_than_its_clip_is_reported() -> None:
    project = _project()
    project.channels[0].clips[0].fade_in = Fade(101)
    assert "overlap" in _first_problem(project)


def test_a_negative_fade_is_reported() -> None:
    project = _project()
    project.channels[0].clips[0].fade_out = Fade(-1)
    assert "fade lengths" in _first_problem(project)


def test_pan_outside_its_range_is_reported() -> None:
    project = _project()
    project.channels[0].pan = 1.5
    assert "outside -1..+1" in _first_problem(project)


def test_a_wrong_sample_rate_is_reported() -> None:
    """D-11: one rate everywhere, and it is not negotiable per project."""
    assert f"not {SAMPLE_RATE}" in _first_problem(Project(sample_rate=44_100))


def test_validate_reports_every_problem_not_only_the_first() -> None:
    """A caller reporting a bad file wants the list."""
    project = _project()
    project.channels[0].pan = 9.0
    project.channels[0].color = "purple"
    project.bpm = -1
    assert len(validate(project)) >= 3


# --------------------------------------------------------------------------- #
# equality — phase 5's round trip leans on this entirely
# --------------------------------------------------------------------------- #


def _rich_project() -> Project:
    """One of everything, so equality has something to be wrong about."""
    return Project(
        bpm=124.0,
        time_signature=(3, 4),
        snap=SnapSetting(enabled=False, division=Division.EIGHTH, triplet=True),
        hrtf=HrtfRef(kind="file", id="custom"),
        media_pool=[_media(), MediaFile("m-00000002", "b.wav", "b", 44_100, 2, 900)],
        channels=[
            Channel(
                "c-00000001",
                "Kick",
                "#A855F7",
                gain_db=-3.0,
                mute=True,
                hrtf_bypass=True,
                pan=0.25,
                snap_override=SnapSetting(enabled=False),
                position=Position(1.0, 2.0, 3.0),
                automation={
                    Interpolatable.POS_X: Curve(
                        [
                            Keyframe(0, -2.0, Interp.EASE, Handles((2400.0, 0.0))),
                            Keyframe(9600, 2.0),
                        ]
                    )
                },
                clips=[
                    Clip(
                        "k-00000001",
                        "m-00000001",
                        0,
                        120,
                        800,
                        gain_db=-1.5,
                        fade_in=Fade(64, FadeShape.EQUAL_POWER),
                        fade_out=Fade(512),
                    )
                ],
            )
        ],
    )


def test_identically_built_projects_compare_equal() -> None:
    assert _rich_project() == _rich_project()


MUTATIONS = {
    "bpm": lambda p: setattr(p, "bpm", 125.0),
    "time_signature": lambda p: setattr(p, "time_signature", (4, 4)),
    "snap.triplet": lambda p: setattr(p.snap, "triplet", False),
    "hrtf.id": lambda p: setattr(p.hrtf, "id", "other"),
    "distance.rolloff": lambda p: setattr(p.distance, "rolloff", 0.5),
    "master.limiter_on": lambda p: setattr(p.master, "limiter_on", False),
    "media.frames": lambda p: setattr(p.media_pool[0], "frames", 999),
    "media order": lambda p: p.media_pool.reverse(),
    "channel.gain_db": lambda p: setattr(p.channels[0], "gain_db", 0.0),
    "channel.mute": lambda p: setattr(p.channels[0], "mute", False),
    "channel.pan": lambda p: setattr(p.channels[0], "pan", 0.0),
    "channel.position": lambda p: setattr(p.channels[0].position, "z", 9.0),
    "channel.snap_override": lambda p: setattr(p.channels[0], "snap_override", None),
    "clip.offset": lambda p: setattr(p.channels[0].clips[0], "offset", 0),
    "clip.fade_in.shape": lambda p: setattr(
        p.channels[0].clips[0].fade_in, "shape", FadeShape.LINEAR
    ),
    "keyframe.value": lambda p: setattr(
        p.channels[0].automation[Interpolatable.POS_X].keyframes[0], "value", 0.0
    ),
    "keyframe.interp": lambda p: setattr(
        p.channels[0].automation[Interpolatable.POS_X].keyframes[1],
        "interp",
        Interp.HOLD,
    ),
    "keyframe.handles": lambda p: setattr(
        p.channels[0].automation[Interpolatable.POS_X].keyframes[0],
        "handles",
        Handles((1.0, 1.0)),
    ),
}


@pytest.mark.parametrize("what", list(MUTATIONS))
def test_changing_any_single_field_breaks_equality(what: str) -> None:
    """Equality that quietly ignores a field makes phase 5's round trip a lie.

    Testing equality once and trusting it is exactly how that happens, so
    every field that carries data gets changed in turn.
    """
    changed = _rich_project()
    MUTATIONS[what](changed)
    assert changed != _rich_project(), f"changing {what} did not break equality"


# --------------------------------------------------------------------------- #
# the next channel
# --------------------------------------------------------------------------- #

PALETTE = ["#A855F7", "#22D3EE", "#F59E0B", "#34D399",
           "#F472B6", "#60A5FA", "#FB923C", "#A3E635"]  # fmt: skip


def with_colours(*colours: str) -> Project:
    return Project(
        channels=[
            Channel(f"c-0000000{n}", f"Channel {n}", colour)
            for n, colour in enumerate(colours, start=1)
        ]
    )


def test_the_first_channel_takes_the_first_colour_and_is_channel_1() -> None:
    channel = new_channel(Project(), PALETTE)
    assert (channel.name, channel.color) == ("Channel 1", "#A855F7")


def test_a_new_channel_takes_the_colour_after_the_last_channels() -> None:
    project = with_colours("#A855F7", "#22D3EE")
    assert new_channel(project, PALETTE).color == "#F59E0B"


def test_the_colours_wrap_after_the_eighth() -> None:
    project = with_colours(*PALETTE)
    assert new_channel(project, PALETTE).color == "#A855F7"


def test_deleting_a_channel_does_not_repeat_its_neighbours_colour() -> None:
    """The mutation this is for: the colour counted from the number of
    channels. Three channels with the third deleted would hand out the third
    colour again, beside the second - two neighbours of one colour."""
    project = with_colours("#A855F7", "#22D3EE", "#F59E0B", "#34D399")
    del project.channels[1]  # purple, amber, green are left
    assert new_channel(project, PALETTE).color == "#F472B6"


def test_a_last_colour_from_outside_the_palette_starts_at_the_count() -> None:
    project = with_colours("#A855F7", "#123456")
    assert new_channel(project, PALETTE).color == "#F59E0B"


def test_the_palette_is_matched_whatever_the_case() -> None:
    project = with_colours("#a855f7")
    assert new_channel(project, PALETTE).color == "#22D3EE"


def test_a_taken_name_is_skipped() -> None:
    project = with_colours("#A855F7", "#22D3EE")
    project.channels[0].name = "Channel 3"
    assert new_channel(project, PALETTE).name == "Channel 4"


def test_a_new_channel_has_an_id_the_project_does_not() -> None:
    project = with_colours("#A855F7")
    channel = new_channel(project, PALETTE)
    assert channel.id not in all_ids(project)
    project.channels.append(channel)
    assert validate(project) == []


def test_an_empty_palette_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one colour"):
        new_channel(Project(), [])
