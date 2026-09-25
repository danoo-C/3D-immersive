"""The concrete edits, one shape at a time.

The round-trip is checked for *every* edit rather than for a representative
one, because the thing that breaks is never the shape you thought to check.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

import pytest

from immersive.core.commands import Command, Compound
from immersive.core.edits import (
    AddChannel,
    AddClip,
    DropClips,
    MoveChannel,
    MoveClip,
    RemoveChannel,
    RemoveClip,
    SetAttribute,
)
from immersive.core.model import (
    Channel,
    Clip,
    Fade,
    FadeShape,
    MediaFile,
    Position,
    Project,
    validate,
)
from immersive.core.time import SAMPLE_RATE

MEDIA = "m-00000001"


def a_project() -> Project:
    """Two channels; the first has two clips with a gap between them."""
    media = MediaFile(MEDIA, "a.wav", "a.wav", SAMPLE_RATE, 1, 1_000_000)
    first = Channel(
        "c-00000001",
        "A",
        "#A855F7",
        clips=[
            Clip("k-00000001", MEDIA, 0, 0, 24_000),
            Clip("k-00000002", MEDIA, 96_000, 0, 24_000),
        ],
    )
    second = Channel("c-00000002", "B", "#22D3EE")
    return Project(media_pool=[media], channels=[first, second])


def a_channel(identifier: str = "c-00000009") -> Channel:
    return Channel(identifier, "New", "#F59E0B")


def a_clip(identifier: str = "k-00000009", start: int = 48_000) -> Clip:
    return Clip(identifier, MEDIA, start, 0, 24_000)


# --------------------------------------------------------------------------- #
# the round trip, for each edit
# --------------------------------------------------------------------------- #

Build = Callable[[Project], Command]

EDITS: dict[str, Build] = {
    "add a channel at the end": lambda p: AddChannel(p, a_channel()),
    "add a channel at the front": lambda p: AddChannel(p, a_channel(), index=0),
    "add a channel in the middle": lambda p: AddChannel(p, a_channel(), index=1),
    "remove the first channel": lambda p: RemoveChannel(p, p.channels[0]),
    "remove the last channel": lambda p: RemoveChannel(p, p.channels[-1]),
    "drop a clip on an empty channel": lambda p: DropClips(
        p, p.channels[1], [a_clip()]
    ),
    "drop a clip over another": lambda p: DropClips(
        p, p.channels[0], [a_clip(start=12_000)]
    ),
    "drop a clip inside another": lambda p: DropClips(
        p, p.channels[0], [Clip("k-00000009", MEDIA, 100_000, 0, 4_000)]
    ),
    "move a channel down": lambda p: MoveChannel(p, p.channels[0], 1),
    "move a channel up": lambda p: MoveChannel(p, p.channels[1], 0),
    "add a clip between two others": lambda p: AddClip(p.channels[0], a_clip()),
    "add a clip before the first": lambda p: AddClip(p.channels[0], a_clip(start=0)),
    "add a clip to an empty channel": lambda p: AddClip(p.channels[1], a_clip()),
    "remove a clip": lambda p: RemoveClip(p.channels[0], p.channels[0].clips[0]),
    "rename a channel": lambda p: SetAttribute(p.channels[0], "name", "Renamed"),
    "mute a channel": lambda p: SetAttribute(p.channels[0], "mute", True),
    "move a channel in space": lambda p: SetAttribute(
        p.channels[0], "position", Position(1.0, 2.0, 3.0)
    ),
    "change the project tempo": lambda p: SetAttribute(p, "bpm", 137.3),
    "change a nested value type": lambda p: SetAttribute(
        p.channels[0].clips[0].fade_in, "shape", FadeShape.EQUAL_POWER
    ),
    "move a clip": lambda p: MoveClip(p.channels[0].clips[0], 36_000),
    "a compound of three": lambda p: Compound(
        [
            SetAttribute(p.channels[0], "name", "Renamed"),
            MoveClip(p.channels[0].clips[0], 36_000),
            AddClip(p.channels[0], a_clip()),
        ]
    ),
}


@pytest.mark.parametrize("name", list(EDITS))
def test_every_edit_round_trips(name: str) -> None:
    """`do()` then `undo()` leaves a project equal to the one before, by the
    equality phase 1 established.

    The middle assertion is not decoration: a command that quietly does
    nothing round-trips perfectly, and phase 2 shipped two of those.
    """
    project = a_project()
    before = copy.deepcopy(project)
    command = EDITS[name](project)

    command.do()
    assert project != before, "this edit changed nothing, so it proves nothing"
    command.undo()
    assert project == before


@pytest.mark.parametrize("name", list(EDITS))
def test_every_edit_survives_being_run_twice(name: str) -> None:
    """Redo is `do()` a second time, so every command has to be reusable - and
    an index computed once at construction is the way that goes wrong."""
    project = a_project()
    before = copy.deepcopy(project)
    command = EDITS[name](project)

    command.do()
    after = copy.deepcopy(project)
    command.undo()
    command.do()
    assert project == after
    command.undo()
    assert project == before


# --------------------------------------------------------------------------- #
# lists
# --------------------------------------------------------------------------- #


def test_a_channel_goes_where_it_was_asked_to() -> None:
    project = a_project()
    AddChannel(project, a_channel(), index=1).do()
    assert [channel.id for channel in project.channels] == [
        "c-00000001",
        "c-00000009",
        "c-00000002",
    ]


def test_removing_a_channel_picks_by_identity_not_by_equality() -> None:
    """Two channels that compare equal are still two channels.

    `list.index` compares by value and phase 1's dataclasses compare by value,
    so a value-based search removes the first match - which is the wrong
    object, indistinguishably, until undo puts it back in the wrong place.
    """
    first, second = a_channel(), a_channel()
    assert first == second and first is not second
    project = Project(channels=[first, second])

    RemoveChannel(project, second).do()

    assert len(project.channels) == 1
    assert project.channels[0] is first


def four() -> Project:
    return Project(channels=[a_channel(f"c-0000000{n}") for n in range(1, 5)])


def ids(project: Project) -> list[str]:
    return [channel.id[-1] for channel in project.channels]


@pytest.mark.parametrize(
    ("moving", "to", "order"),
    [
        (0, 3, "2341"),
        (3, 0, "4123"),
        (1, 2, "1324"),
        (2, 1, "1324"),
        (0, 1, "2134"),
    ],
)
def test_a_moved_channel_lands_where_asked_and_undo_puts_it_back(
    moving: int, to: int, order: str
) -> None:
    project = four()
    command = MoveChannel(project, project.channels[moving], to)

    command.do()
    assert "".join(ids(project)) == order
    command.undo()
    assert "".join(ids(project)) == "1234"


def test_moving_a_channel_onto_its_own_place_changes_nothing() -> None:
    project = four()
    command = MoveChannel(project, project.channels[2], 2)
    command.do()
    assert "".join(ids(project)) == "1234"
    command.undo()
    assert "".join(ids(project)) == "1234"


def test_a_move_outside_the_list_is_refused_at_construction() -> None:
    project = four()
    with pytest.raises(IndexError):
        MoveChannel(project, project.channels[0], 4)
    with pytest.raises(IndexError):
        MoveChannel(project, project.channels[0], -1)


def test_removing_something_that_is_not_there_says_so_at_construction() -> None:
    project = a_project()
    with pytest.raises(ValueError, match="not in this list"):
        RemoveChannel(project, a_channel())


@pytest.mark.parametrize("start", [0, 1, 24_000, 48_000, 95_999, 96_000, 200_000])
def test_adding_a_clip_keeps_the_channel_sorted(start: int) -> None:
    """Sorted-and-non-overlapping is a rule `validate()` owns, so the insert
    position is derived rather than passed in."""
    project = a_project()
    channel = project.channels[0]
    AddClip(channel, a_clip(start=start)).do()
    starts = [clip.start for clip in channel.clips]
    assert starts == sorted(starts)
    assert start in starts


def test_two_clips_can_never_share_a_start_on_one_channel() -> None:
    """Why `AddClip`'s choice of bisect edge is unreachable rather than untested.

    A clip must have positive length, and a clip may not begin before its
    predecessor ends. Equal starts break the second rule whenever the first
    holds, so `bisect_left` and `bisect_right` agree on every project that
    `validate()` accepts - and a mutation between them survives the suite. It
    is recorded here rather than papered over with a test that would only be
    asserting the mutation.
    """
    project = a_project()
    project.channels[0].clips.append(Clip("k-0000000a", MEDIA, 0, 0, 24_000))
    assert any("must not overlap" in problem.message for problem in validate(project))


# --------------------------------------------------------------------------- #
# fields
# --------------------------------------------------------------------------- #


def test_set_attribute_rejects_a_field_that_does_not_exist() -> None:
    """A typo fails where it is written, not at undo time - and the message
    says what the target does have, because the usual cause is a near miss."""
    channel = a_channel()
    with pytest.raises(AttributeError, match="has no field 'gian_db'") as caught:
        SetAttribute(channel, "gian_db", -6.0)
    assert "gain_db" in str(caught.value)


def test_set_attribute_rejects_a_target_that_is_not_a_dataclass() -> None:
    with pytest.raises(TypeError, match="needs a dataclass instance"):
        SetAttribute({"name": "A"}, "name", "B")
    with pytest.raises(TypeError, match="needs a dataclass instance"):
        SetAttribute(Channel, "name", "B")


def test_set_attribute_does_not_invent_attributes() -> None:
    """The failure mode the field check exists to prevent: an attribute that
    nothing reads, that undo cannot remove, and that never saves."""
    channel = a_channel()
    with pytest.raises(AttributeError):
        SetAttribute(channel, "colour", "#FFFFFF")
    assert not hasattr(channel, "colour")


# --------------------------------------------------------------------------- #
# merging
# --------------------------------------------------------------------------- #


def test_a_move_merges_with_a_later_move_of_the_same_clip() -> None:
    clip = a_clip(start=0)
    first = MoveClip(clip, 1_000)
    first.do()
    second = MoveClip(clip, 2_000)
    second.do()

    assert first.merge_with(second) is True
    first.undo()
    assert clip.start == 0, "the merge kept the later before-value"


def test_a_move_does_not_merge_with_a_move_of_another_clip() -> None:
    one, other = a_clip("k-00000009"), a_clip("k-0000000a")
    assert MoveClip(one, 1_000).merge_with(MoveClip(other, 1_000)) is False


def test_a_move_does_not_merge_with_another_kind_of_edit() -> None:
    clip = a_clip()
    assert (
        MoveClip(clip, 1_000).merge_with(SetAttribute(clip, "gain_db", -6.0)) is False
    )


def test_nothing_merges_by_default() -> None:
    """`Command.merge_with` returns False unless a command opts in, so an edit
    added in M3 cannot start coalescing by accident."""
    project = a_project()
    channel = project.channels[0]
    assert (
        SetAttribute(channel, "name", "B").merge_with(
            SetAttribute(channel, "name", "C")
        )
        is False
    )
    add_channel = AddChannel(project, a_channel())
    assert add_channel.merge_with(AddClip(channel, a_clip())) is False


# --------------------------------------------------------------------------- #
# dropping clips, and what they land on (D-95)
# --------------------------------------------------------------------------- #

LONG = "m-00000002"


def a_lane(*clips: Clip) -> tuple[Project, Channel]:
    """A channel holding `clips`, over a sample long enough for anything."""
    long = MediaFile(LONG, "long.wav", "long.wav", SAMPLE_RATE, 1, 10_000_000)
    channel = Channel("c-00000001", "A", "#A855F7", clips=list(clips))
    return Project(media_pool=[long], channels=[channel]), channel


def existing(start: int = 96_000, length: int = 96_000, offset: int = 1_000) -> Clip:
    return Clip(
        "k-00000001",
        LONG,
        start,
        offset,
        length,
        fade_in=Fade(2_000),
        fade_out=Fade(3_000),
    )


def dropped(start: int, length: int, identifier: str = "k-000000d1") -> Clip:
    return Clip(identifier, LONG, start, 0, length)


def spans(channel: Channel) -> list[tuple[int, int]]:
    return [(clip.start, clip.end) for clip in channel.clips]


def frame_at(clip: Clip, t: int) -> int:
    """Which frame of its sample `clip` plays at timeline time `t`."""
    return clip.offset + (t - clip.start)


def test_a_drop_on_an_empty_channel_just_lands() -> None:
    project, channel = a_lane()
    DropClips(project, channel, [dropped(48_000, 10_000)]).do()
    assert spans(channel) == [(48_000, 58_000)]


def test_a_clip_the_drop_covers_is_removed() -> None:
    project, channel = a_lane(existing())
    DropClips(project, channel, [dropped(90_000, 200_000)]).do()
    assert spans(channel) == [(90_000, 290_000)]
    assert validate(project) == []


def test_a_clip_overlapped_at_its_head_is_trimmed_and_plays_what_it_played() -> None:
    original = existing()
    project, channel = a_lane(original)
    before = {t: frame_at(original, t) for t in (120_000, 150_000, 191_999)}

    DropClips(project, channel, [dropped(48_000, 72_000)]).do()  # to 120 000

    assert spans(channel) == [(48_000, 120_000), (120_000, 192_000)]
    kept = channel.clips[1]
    assert kept is original
    assert {t: frame_at(kept, t) for t in before} == before
    assert kept.fade_in == Fade(), "its start went, and the fade that was there"
    assert kept.fade_out == Fade(3_000)
    assert validate(project) == []


def test_a_clip_overlapped_at_its_tail_is_trimmed() -> None:
    original = existing()
    project, channel = a_lane(original)

    DropClips(project, channel, [dropped(150_000, 100_000)]).do()

    assert spans(channel) == [(96_000, 150_000), (150_000, 250_000)]
    assert (original.offset, original.fade_in, original.fade_out) == (
        1_000,
        Fade(2_000),
        Fade(),
    )


def test_a_clip_reaching_past_both_ends_is_split_around_the_drop() -> None:
    original = existing()
    project, channel = a_lane(original)

    DropClips(project, channel, [dropped(120_000, 24_000)]).do()

    assert spans(channel) == [(96_000, 120_000), (120_000, 144_000), (144_000, 192_000)]
    head, _, tail = channel.clips
    assert head is original
    assert tail.id not in {original.id, "k-000000d1"}
    assert frame_at(tail, 144_000) == 1_000 + 48_000, "the tail plays its own part"
    assert (head.fade_in, head.fade_out) == (Fade(2_000), Fade())
    assert (tail.fade_in, tail.fade_out) == (Fade(), Fade(3_000))
    assert validate(project) == []


def test_a_fade_longer_than_what_is_left_is_cut_to_fit() -> None:
    original = existing()
    project, channel = a_lane(original)

    DropClips(
        project, channel, [dropped(97_000, 94_000)]
    ).do()  # leaves 1 000 each side

    head, _, tail = channel.clips
    assert head.fade_in.length == 1_000
    assert tail.fade_out.length == 1_000


def test_a_drop_across_several_clips_settles_each() -> None:
    a = Clip("k-00000001", LONG, 0, 0, 50_000)
    b = Clip("k-00000002", LONG, 60_000, 0, 20_000)
    c = Clip("k-00000003", LONG, 90_000, 0, 50_000)
    project, channel = a_lane(a, b, c)

    DropClips(
        project,
        channel,
        [dropped(40_000, 30_000, "k-000000d1"), dropped(70_000, 30_000, "k-000000d2")],
    ).do()

    assert spans(channel) == [
        (0, 40_000),
        (40_000, 70_000),
        (70_000, 100_000),
        (100_000, 140_000),
    ]
    assert [clip.id for clip in channel.clips] == [
        "k-00000001",
        "k-000000d1",
        "k-000000d2",
        "k-00000003",
    ]
    assert validate(project) == []


def test_undo_puts_every_clip_back_as_it_was_and_redo_does_it_again() -> None:
    project, channel = a_lane(
        existing(), Clip("k-00000002", LONG, 300_000, 5, 10_000, fade_in=Fade(7))
    )
    before = copy.deepcopy(project)
    command = DropClips(project, channel, [dropped(120_000, 190_000)])

    command.do()
    once = copy.deepcopy(project)
    command.undo()
    assert project == before
    command.do()
    assert project == once


def test_a_drop_below_the_last_lane_is_one_compound_with_its_new_channel() -> None:
    project, _ = a_lane()
    fresh = Channel("c-00000002", "B", "#22D3EE")
    before = copy.deepcopy(project)
    command = Compound(
        [AddChannel(project, fresh), DropClips(project, fresh, [dropped(0, 5_000)])]
    )

    command.do()
    assert spans(project.channels[1]) == [(0, 5_000)]
    command.undo()
    assert project == before
