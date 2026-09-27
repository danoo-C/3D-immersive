"""The concrete edits, one shape at a time.

The round-trip is checked for *every* edit rather than for a representative
one, because the thing that breaks is never the shape you thought to check.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable

import numpy as np
import pytest

from immersive.core.clipboard import Clipboard
from immersive.core.commands import Command, Compound, UndoStack
from immersive.core.edits import (
    AddChannel,
    AddClip,
    DropClips,
    DuplicateClips,
    Edge,
    FadeClips,
    MoveChannel,
    MoveClip,
    MoveClips,
    PasteClips,
    RemoveChannel,
    RemoveClip,
    RemoveClips,
    SetAttribute,
    SetLengths,
    SlipClips,
    SplitClips,
    TrimClips,
    fade_room,
)
from immersive.core.model import (
    MIN_CLIP_LENGTH,
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
PALETTE = ("#A855F7", "#22D3EE", "#F59E0B")


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


def pasting(project: Project, clips: list[Clip], lane: int, at_: int) -> PasteClips:
    board = Clipboard()
    board.hold(project, clips)
    return PasteClips(project, board.held(), lane, at_, PALETTE)


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
    "move clips along their lane": lambda p: MoveClips(p, p.channels[0].clips, 1_000),
    "move a clip onto its neighbour": lambda p: MoveClips(
        p, [p.channels[0].clips[0]], 80_000
    ),
    "move a clip to another lane": lambda p: MoveClips(
        p, [p.channels[0].clips[1]], 0, 1
    ),
    "trim a clip's end": lambda p: TrimClips(
        p, [p.channels[0].clips[0]], Edge.END, -4_000
    ),
    "trim a clip's start": lambda p: TrimClips(
        p, [p.channels[0].clips[1]], Edge.START, 4_000
    ),
    "split a clip": lambda p: SplitClips(p, [p.channels[0].clips[0]], 12_000),
    "duplicate clips": lambda p: DuplicateClips(p, p.channels[0].clips),
    "remove clips": lambda p: RemoveClips(p, p.channels[0].clips),
    "set clips' length": lambda p: SetLengths(p, p.channels[0].clips, 30_000),
    "slip clips": lambda p: SlipClips(p, p.channels[0].clips, 5_000),
    "lengthen clips' fades": lambda p: FadeClips(p.channels[0].clips, Edge.START, 900),
    "paste clips onto an empty lane": lambda p: pasting(
        p, p.channels[0].clips, 1, 10_000
    ),
    "paste clips over their originals": lambda p: pasting(
        p, p.channels[0].clips, 0, 12_000
    ),
    "paste clips past the last lane": lambda p: pasting(p, p.channels[0].clips, 2, 0),
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


# --------------------------------------------------------------------------- #
# moving clips (D-97)
# --------------------------------------------------------------------------- #


def lanes(*rows: list[Clip]) -> Project:
    """A channel per row, over a sample long enough for anything."""
    long = MediaFile(LONG, "long.wav", "long.wav", SAMPLE_RATE, 1, 10_000_000)
    return Project(
        media_pool=[long],
        channels=[
            Channel(f"c-0000000{n + 1}", f"C{n}", "#A855F7", clips=list(row))
            for n, row in enumerate(rows)
        ],
    )


def at(start: int, length: int, identifier: str, offset: int = 0) -> Clip:
    return Clip(identifier, LONG, start, offset, length)


def test_a_moved_clip_keeps_playing_its_own_samples() -> None:
    clip = at(10_000, 5_000, "k-00000001", offset=700)
    project = lanes([clip])
    MoveClips(project, [clip], 3_000).do()
    assert (clip.start, clip.offset, clip.length) == (13_000, 700, 5_000)


def test_a_move_onto_a_neighbour_overwrites_it_as_a_drop_would() -> None:
    mover, other = at(0, 10_000, "k-00000001"), at(20_000, 10_000, "k-00000002")
    project = lanes([mover, other])

    MoveClips(project, [mover], 15_000).do()

    assert spans(project.channels[0]) == [(15_000, 25_000), (25_000, 30_000)]
    assert project.channels[0].clips[1] is other
    assert other.offset == 5_000, "what is left still plays what it played"
    assert validate(project) == []


def test_moved_clips_are_lifted_first_so_none_trims_another() -> None:
    first, second = at(0, 10_000, "k-00000001"), at(10_000, 10_000, "k-00000002")
    project = lanes([first, second])

    MoveClips(project, [first, second], 4_000).do()

    assert spans(project.channels[0]) == [(4_000, 14_000), (14_000, 24_000)]
    assert (first.length, second.length, second.offset) == (10_000, 10_000, 0)


def test_a_clip_moved_past_its_neighbour_leaves_the_lane_sorted() -> None:
    mover, other = at(0, 10_000, "k-00000001"), at(20_000, 5_000, "k-00000002")
    project = lanes([mover, other])
    MoveClips(project, [mover], 40_000).do()
    assert project.channels[0].clips == [other, mover]
    assert validate(project) == []


def test_a_move_across_lanes_takes_every_clip_the_same_number_of_lanes() -> None:
    a, b = at(0, 5_000, "k-00000001"), at(8_000, 5_000, "k-00000002")
    project = lanes([a], [b], [], [])

    command = MoveClips(project, [a, b], 1_000, 2)
    command.do()

    assert [c.clips for c in project.channels] == [[], [], [a], [b]]
    assert command.placed() == [(a, 2, 1_000), (b, 3, 9_000)]


def test_the_lanes_stop_together_at_the_first_and_the_last() -> None:
    a, b = at(0, 5_000, "k-00000001"), at(0, 5_000, "k-00000002")
    project = lanes([], [a], [b])

    up = MoveClips(project, [a, b], 0, -5)
    assert (up.lanes, [lane for _, lane, _ in up.placed()]) == (-1, [0, 1])
    down = MoveClips(project, [a, b], 0, 5)
    assert (down.lanes, [lane for _, lane, _ in down.placed()]) == (0, [1, 2])


def test_the_time_stops_together_at_the_start_of_the_timeline() -> None:
    a, b = at(3_000, 1_000, "k-00000001"), at(10_000, 1_000, "k-00000002")
    project = lanes([a, b])
    command = MoveClips(project, [a, b], -8_000)
    assert command.delta == -3_000
    command.do()
    assert spans(project.channels[0]) == [(0, 1_000), (7_000, 8_000)]


def test_a_move_by_nothing_changes_nothing() -> None:
    a = at(0, 1_000, "k-00000001")
    project = lanes([a], [])
    assert not MoveClips(project, [a], 0).changes
    assert not MoveClips(project, [a], -5_000, -1).changes, "stopped at both"
    assert MoveClips(project, [a], 1).changes
    assert MoveClips(project, [a], 0, 1).changes


# --------------------------------------------------------------------------- #
# trimming clips (D-98)
# --------------------------------------------------------------------------- #


def trimmed_to(project: Project, clip: Clip, edge: Edge, delta: int) -> tuple[int, int]:
    TrimClips(project, [clip], edge, delta).do()
    return clip.start, clip.end


def short_sample(frames: int) -> Project:
    short = MediaFile("m-00000003", "s.wav", "s.wav", SAMPLE_RATE, 1, frames)
    return Project(media_pool=[short], channels=[Channel("c-00000001", "A", "#A855F7")])


def test_an_end_grows_as_far_as_its_sample_reaches_and_no_further() -> None:
    project = short_sample(50_000)
    clip = Clip("k-00000001", "m-00000003", 1_000, 10_000, 20_000)
    project.channels[0].clips.append(clip)
    assert trimmed_to(project, clip, Edge.END, 99_000) == (1_000, 41_000)


def test_a_start_grows_back_to_its_sample_start_and_plays_what_it_played() -> None:
    clip = at(50_000, 10_000, "k-00000001", offset=4_000)
    project = lanes([clip])
    before = {t: frame_at(clip, t) for t in (55_000, 59_999)}

    assert trimmed_to(project, clip, Edge.START, -99_000) == (46_000, 60_000)
    assert clip.offset == 0
    assert {t: frame_at(clip, t) for t in before} == before


def test_a_start_stops_at_the_start_of_the_timeline() -> None:
    clip = at(2_000, 10_000, "k-00000001", offset=9_000)
    project = lanes([clip])
    assert trimmed_to(project, clip, Edge.START, -5_000) == (0, 12_000)
    assert clip.offset == 7_000


def test_a_trim_stops_at_the_neighbour_on_either_side() -> None:
    left = at(0, 10_000, "k-00000001")
    middle = at(20_000, 10_000, "k-00000002", offset=50_000)
    right = at(40_000, 10_000, "k-00000003")
    project = lanes([left, middle, right])

    assert trimmed_to(project, middle, Edge.END, 50_000) == (20_000, 40_000)
    assert trimmed_to(project, middle, Edge.START, -50_000) == (10_000, 40_000)
    assert validate(project) == []


def test_a_trim_stops_at_the_shortest_a_clip_may_be() -> None:
    clip = at(0, 10_000, "k-00000001")
    project = lanes([clip])
    assert trimmed_to(project, clip, Edge.END, -20_000) == (0, MIN_CLIP_LENGTH)
    other = at(20_000, 10_000, "k-00000002")
    project.channels[0].clips.append(other)
    assert trimmed_to(project, other, Edge.START, 20_000) == (
        30_000 - MIN_CLIP_LENGTH,
        30_000,
    )


def test_a_clip_a_file_made_shorter_than_that_is_not_grown_by_shrinking_it() -> None:
    clip = at(0, 10, "k-00000001")
    project = lanes([clip])
    assert trimmed_to(project, clip, Edge.END, -5) == (0, 10)


def test_several_clips_trim_each_as_far_as_it_can() -> None:
    free = at(0, 10_000, "k-00000001")
    blocked = at(0, 10_000, "k-00000002")
    wall = at(12_000, 1_000, "k-00000003")
    project = lanes([free], [blocked, wall])

    TrimClips(project, [free, blocked], Edge.END, 5_000).do()

    assert (free.end, blocked.end) == (15_000, 12_000)


def test_a_trim_cuts_a_fade_to_fit_and_keeps_it_on_its_edge() -> None:
    clip = Clip("k-00000001", LONG, 0, 0, 10_000, fade_out=Fade(6_000))
    project = lanes([clip])
    TrimClips(project, [clip], Edge.END, -7_000).do()
    assert (clip.fade_in.length, clip.fade_out.length) == (0, 3_000)


# --------------------------------------------------------------------------- #
# fades that fit (D-101)
# --------------------------------------------------------------------------- #


def faded(fade_in: int, fade_out: int, length: int = 10_000) -> Clip:
    return Clip(
        "k-00000001",
        LONG,
        100_000,
        50_000,
        length,
        fade_in=Fade(fade_in, FadeShape.EQUAL_POWER),
        fade_out=Fade(fade_out),
    )


def fades(clip: Clip) -> tuple[int, int]:
    return clip.fade_in.length, clip.fade_out.length


@pytest.mark.parametrize(
    ("edge", "delta", "expected"),
    [
        (Edge.END, -3_000, (4_000, 3_000)),  # the moved edge's gives way
        (Edge.END, -5_000, (4_000, 1_000)),
        (Edge.END, -7_000, (3_000, 0)),  # and the other only when it must
        (Edge.START, 3_000, (1_000, 6_000)),
        (Edge.START, 5_000, (0, 5_000)),
        (Edge.END, -1_000, (4_000, 5_000)),  # meeting is allowed
        (Edge.END, 5_000, (4_000, 6_000)),  # growing changes neither
    ],
)
def test_a_trim_fits_both_fades_the_moved_edges_giving_way_first(
    edge: Edge, delta: int, expected: tuple[int, int]
) -> None:
    clip = faded(4_000, 6_000)
    project = lanes([clip])

    command = TrimClips(project, [clip], edge, delta)
    command.do()

    assert fades(clip) == expected
    assert clip.fade_in.shape is FadeShape.EQUAL_POWER, "the shape stays"
    assert validate(project) == []
    command.undo()
    assert fades(clip) == (4_000, 6_000)


def test_a_split_and_a_drop_leave_fades_that_fit() -> None:
    clip = faded(4_000, 5_000)
    project = lanes([clip])
    SplitClips(project, [clip], 102_000).do()
    DropClips(project, project.channels[0], [at(107_000, 500, "k-000000d1")]).do()
    assert validate(project) == []
    assert [fades(c) for c in project.channels[0].clips] == [
        (2_000, 0),
        (0, 0),
        (0, 0),
        (0, 2_500),
    ]


@pytest.mark.parametrize(("edge", "room"), [(Edge.START, 7_000), (Edge.END, 6_000)])
def test_a_fade_has_the_room_the_other_leaves(edge: Edge, room: int) -> None:
    assert fade_room(faded(4_000, 3_000), edge) == room


# --------------------------------------------------------------------------- #
# lengths and slips (D-102)
# --------------------------------------------------------------------------- #


def test_a_length_is_set_on_each_clip_as_far_as_it_can_go() -> None:
    short = MediaFile("m-00000003", "s.wav", "s.wav", SAMPLE_RATE, 1, 30_000)
    free = at(0, 10_000, "k-00000001")
    blocked = at(0, 10_000, "k-00000002")
    neighbour = at(15_000, 5_000, "k-00000003")
    sampled = Clip("k-00000004", short.id, 0, 25_000, 2_000)
    project = lanes([free], [blocked, neighbour], [sampled])
    project.media_pool.append(short)
    before = copy.deepcopy(project)

    command = SetLengths(project, [free, blocked, sampled], 20_000)
    command.do()

    assert [c.length for c in (free, blocked, sampled)] == [20_000, 15_000, 5_000]
    assert (free.start, free.offset) == (0, 0), "the end moves, not the start"
    assert validate(project) == []
    command.undo()
    assert project == before


def test_a_length_stops_at_the_shortest_a_clip_may_be() -> None:
    clip = at(0, 10_000, "k-00000001")
    project = lanes([clip])
    SetLengths(project, [clip], 3).do()
    assert clip.length == MIN_CLIP_LENGTH


def test_a_slip_plays_other_samples_in_the_same_place() -> None:
    short = MediaFile("m-00000003", "s.wav", "s.wav", SAMPLE_RATE, 1, 30_000)
    a = Clip("k-00000001", short.id, 5_000, 1_000, 10_000, fade_in=Fade(300))
    b = Clip("k-00000002", short.id, 5_000, 0, 25_000)
    project = lanes([a], [b])
    project.media_pool.append(short)
    before = copy.deepcopy(project)

    command = SlipClips(project, [a, b], 12_000)
    command.do()

    assert (a.start, a.offset, a.length) == (5_000, 12_000, 10_000)
    assert (b.start, b.offset, b.length) == (5_000, 5_000, 25_000), "its sample's end"
    assert a.fade_in == Fade(300)
    assert validate(project) == []
    command.undo()
    assert project == before


def test_a_slip_stops_at_the_sample_start() -> None:
    clip = at(5_000, 10_000, "k-00000001", offset=4_000)
    project = lanes([clip])
    SlipClips(project, [clip], -3_000).do()
    assert (clip.start, clip.offset) == (5_000, 0)


# --------------------------------------------------------------------------- #
# splitting, duplicating, removing
# --------------------------------------------------------------------------- #


def played(audio: np.ndarray, clip: Clip) -> np.ndarray:
    """The samples `clip` plays, read from its decoded sample."""
    return audio[clip.offset : clip.offset + clip.length]


def test_a_split_plays_exactly_what_the_clip_played() -> None:
    audio = np.random.default_rng(7).standard_normal(200_000).astype(np.float32)
    clip = Clip(
        "k-00000001", LONG, 30_000, 12_345, 100_000, fade_in=Fade(10), fade_out=Fade(20)
    )
    project = lanes([clip])
    whole = played(audio, clip).copy()

    command = SplitClips(project, [clip], 70_000)
    command.do()

    head, tail = project.channels[0].clips
    assert head is clip and command.tails == [tail]
    assert (head.start, head.end, tail.start, tail.end) == (
        30_000,
        70_000,
        70_000,
        130_000,
    )
    assert np.array_equal(
        np.concatenate([played(audio, head), played(audio, tail)]), whole
    )
    assert tail.id != head.id
    assert (head.fade_in, head.fade_out) == (Fade(10), Fade())
    assert (tail.fade_in, tail.fade_out) == (Fade(), Fade(20))
    assert validate(project) == []


@pytest.mark.parametrize(
    "at_",
    [
        29_999,
        30_000,
        30_000 + MIN_CLIP_LENGTH - 1,
        130_000 - MIN_CLIP_LENGTH + 1,
        130_000,
    ],
)
def test_a_split_too_near_an_edge_or_outside_leaves_the_clip_alone(at_: int) -> None:
    clip = at(30_000, 100_000, "k-00000001")
    other = at(0, 200_000, "k-00000002")
    project = lanes([clip], [other])

    command = SplitClips(project, [clip, other], at_)
    command.do()

    assert project.channels[0].clips == [clip]
    assert len(project.channels[1].clips) == 2, "the other clip still splits"


def test_duplicates_go_just_after_the_selection_each_on_its_own_channel() -> None:
    a, b = at(10_000, 5_000, "k-00000001"), at(12_000, 8_000, "k-00000002")
    project = lanes([a], [b])

    command = DuplicateClips(project, [a, b])
    command.do()

    a2, b2 = command.copies
    assert project.channels[0].clips == [a, a2] and project.channels[1].clips == [b, b2]
    assert (a2.start, b2.start) == (20_000, 22_000), "shifted by the span, 10 000"
    assert {a2.id, b2.id}.isdisjoint({a.id, b.id}) and a2.id != b2.id
    assert (a.start, b.start) == (10_000, 12_000)


def test_duplicates_land_as_a_drop_does_and_own_their_fades() -> None:
    a = Clip("k-00000001", LONG, 0, 0, 10_000, fade_in=Fade(100))
    in_the_way = at(15_000, 10_000, "k-00000002")
    project = lanes([a, in_the_way])

    [copy_] = DuplicateClips(project, [a]).copies
    DuplicateClips(project, [a]).do()

    assert spans(project.channels[0]) == [
        (0, 10_000),
        (10_000, 20_000),
        (20_000, 25_000),
    ]
    landed = project.channels[0].clips[1]
    assert landed.fade_in == a.fade_in and landed.fade_in is not a.fade_in
    assert copy_.fade_in is not a.fade_in


def test_removing_clips_across_channels_is_one_edit() -> None:
    a, b, c = at(0, 5, "k-00000001"), at(10, 5, "k-00000002"), at(0, 5, "k-00000003")
    project = lanes([a, b], [c])
    before = copy.deepcopy(project)
    command = RemoveClips(project, [a, c])
    command.do()
    assert [ch.clips for ch in project.channels] == [[b], []]
    command.undo()
    assert project == before


# --------------------------------------------------------------------------- #
# every edit, many times over
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(8))
def test_any_run_of_edits_stays_valid_and_undoes_to_where_it_began(seed: int) -> None:
    """Two hundred random edits through the stack, which refuses any that
    leaves the project invalid - so a refusal here is an edit that broke a
    rule it was meant to keep. Then every one undone."""
    rng = random.Random(seed)
    project = lanes(
        [at(n * 30_000, 20_000, f"k-0000{n:04x}", offset=n * 1_000) for n in range(6)],
        [at(n * 50_000, 40_000, f"k-0001{n:04x}") for n in range(4)],
        [],
    )
    before = copy.deepcopy(project)
    stack = UndoStack(project)
    for _ in range(200):
        clips = [c for channel in project.channels for c in channel.clips]
        if not clips:
            break
        chosen = rng.sample(clips, rng.randint(1, min(3, len(clips))))
        verb = rng.choice(
            [
                "move",
                "trim",
                "split",
                "duplicate",
                "paste",
                "length",
                "slip",
                "fade",
                "remove",
            ]
        )
        if verb == "move":
            command: Command = MoveClips(
                project, chosen, rng.randint(-60_000, 60_000), rng.randint(-2, 2)
            )
        elif verb == "trim":
            command = TrimClips(
                project, chosen, rng.choice(list(Edge)), rng.randint(-30_000, 30_000)
            )
        elif verb == "split":
            command = SplitClips(project, chosen, rng.randint(0, 400_000))
        elif verb == "duplicate":
            command = DuplicateClips(project, chosen)
        elif verb == "length":
            command = SetLengths(project, chosen, rng.randint(0, 60_000))
        elif verb == "slip":
            command = SlipClips(project, chosen, rng.randint(-1_000, 40_000))
        elif verb == "fade":
            edge = rng.choice(list(Edge))
            name = "fade_in" if edge is Edge.START else "fade_out"
            command = Compound(
                [
                    SetAttribute(
                        clip, name, Fade(rng.randint(0, fade_room(clip, edge)))
                    )
                    for clip in chosen
                ]
            )
        elif verb == "paste":
            if len(project.channels) > 5:
                continue
            command = pasting(
                project,
                chosen,
                rng.randrange(len(project.channels)),
                rng.randint(0, 400_000),
            )
        else:
            if rng.random() < 0.7:
                continue
            command = RemoveClips(project, chosen)
        stack.push(command)
    while stack.undo():
        pass
    assert project == before


# --------------------------------------------------------------------------- #
# fades dragged (D-101)
# --------------------------------------------------------------------------- #


def test_a_fade_is_dragged_as_far_as_its_room_and_no_shorter_than_nothing() -> None:
    a = faded(4_000, 6_000)
    b = Clip("k-00000002", LONG, 0, 0, 10_000, fade_out=Fade(1_000))
    project = lanes([a], [b])
    before = copy.deepcopy(project)

    command = FadeClips([a, b], Edge.START, 3_000)
    command.do()

    assert fades(a) == (4_000, 6_000), "no room left beside a 6 000 fade-out"
    assert fades(b) == (3_000, 1_000)
    assert a.fade_in.shape is FadeShape.EQUAL_POWER
    assert validate(project) == []
    command.undo()
    assert project == before

    FadeClips([a, b], Edge.END, -9_000).do()
    assert fades(a) == (4_000, 0) and fades(b) == (0, 0)
