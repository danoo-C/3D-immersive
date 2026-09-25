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
    MoveChannel,
    MoveClip,
    RemoveChannel,
    RemoveClip,
    SetAttribute,
)
from immersive.core.model import (
    Channel,
    Clip,
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
