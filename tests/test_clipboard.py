"""The clipboard and the paste: copies, the project's, landing as a drop
does (D-99, D-100). No window, no Qt."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from immersive.core import model
from immersive.core.clipboard import Clipboard
from immersive.core.commands import UndoStack
from immersive.core.document import Document
from immersive.core.edits import (
    AddChannel,
    AddMedia,
    DropClips,
    Edge,
    MoveClips,
    PasteClips,
    TrimClips,
)
from immersive.core.model import (
    Channel,
    Clip,
    Fade,
    MediaFile,
    Project,
    validate,
)
from immersive.core.time import SAMPLE_RATE

LONG = "m-00000002"
PALETTE = ("#A855F7", "#22D3EE", "#F59E0B", "#34D399")


def lanes(*rows: list[Clip]) -> Project:
    """A channel per row, over a sample long enough for anything."""
    long = MediaFile(LONG, "long.wav", "long.wav", SAMPLE_RATE, 1, 10_000_000)
    return Project(
        media_pool=[long],
        channels=[
            Channel(f"c-0000000{n + 1}", f"C{n}", PALETTE[0], clips=list(row))
            for n, row in enumerate(rows)
        ],
    )


def at(start: int, length: int, identifier: str, offset: int = 0) -> Clip:
    return Clip(identifier, LONG, start, offset, length)


def spans(channel: Channel) -> list[tuple[int, int]]:
    return [(clip.start, clip.end) for clip in channel.clips]


def held(project: Project, *clips: Clip) -> Clipboard:
    board = Clipboard()
    board.hold(project, clips)
    return board


def paste(
    project: Project, board: Clipboard, lane: int, at_: int
) -> tuple[PasteClips, UndoStack]:
    """Pasted through a stack, which refuses anything `validate()` would."""
    stack = UndoStack(project)
    command = PasteClips(project, board.held(), lane, at_, PALETTE)
    stack.push(command)
    return command, stack


# --------------------------------------------------------------------------- #
# what is held
# --------------------------------------------------------------------------- #


def test_starts_count_from_the_earliest_and_lanes_from_the_topmost() -> None:
    a, b = at(25_000, 5_000, "k-00000001"), at(10_000, 5_000, "k-00000002")
    project = lanes([], [a], [], [b])

    board = held(project, a, b)

    assert [(lane, clip.start) for lane, clip in board.held()] == [
        (0, 15_000),
        (2, 0),
    ], "in lane order, then time order; the gap lane kept"


def test_held_in_lane_order_then_time_order_whatever_order_they_were_given() -> None:
    """The topmost is the topmost of all of them, not the first given."""
    low = at(0, 5_000, "k-00000001")
    late, early = at(25_000, 5_000, "k-00000002"), at(12_000, 5_000, "k-00000003")
    project = lanes([], [late, early], [], [low])

    board = held(project, low, late, early)

    assert [(lane, clip.id, clip.start) for lane, clip in board.held()] == [
        (0, early.id, 12_000),
        (0, late.id, 25_000),
        (2, low.id, 0),
    ]


def test_the_clipboard_holds_copies_so_later_edits_change_nothing_it_pastes() -> None:
    a = Clip("k-00000001", LONG, 10_000, 500, 5_000, fade_in=Fade(100))
    project = lanes([a], [])
    board = held(project, a)
    [(_, kept)] = board.held()
    assert kept is not a and kept.fade_in is not a.fade_in

    MoveClips(project, [a], 40_000).do()
    TrimClips(project, [a], Edge.END, -2_000).do()
    a.fade_in.length = 900
    command, _ = paste(project, board, 1, 0)

    [pasted] = command.copies
    assert (pasted.start, pasted.offset, pasted.length) == (0, 500, 5_000)
    assert pasted.fade_in == Fade(100)


def test_holding_nothing_empties_it() -> None:
    a = at(0, 5_000, "k-00000001")
    board = held(lanes([a]), a)
    board.hold(lanes([a]), [])
    assert not board and board.held() == []


# --------------------------------------------------------------------------- #
# where a paste lands (D-100)
# --------------------------------------------------------------------------- #


def test_a_paste_lands_at_the_playhead_keeping_its_spacing_in_time_and_lanes() -> None:
    a, b = at(10_000, 5_000, "k-00000001"), at(22_000, 8_000, "k-00000002")
    project = lanes([a], [], [b], [], [], [])

    command, _ = paste(project, held(project, a, b), 3, 100_000)

    assert spans(project.channels[3]) == [(100_000, 105_000)]
    assert spans(project.channels[4]) == [], "the gap lane stays a gap"
    assert spans(project.channels[5]) == [(112_000, 120_000)]
    assert command.channels == []


def test_pasted_clips_have_fresh_ids_and_fades_of_their_own() -> None:
    a = Clip("k-00000001", LONG, 0, 0, 5_000, fade_in=Fade(100), fade_out=Fade(200))
    b = at(5_000, 5_000, "k-00000002")
    project = lanes([a, b], [])
    board = held(project, a, b)

    first, _ = paste(project, board, 1, 0)
    second, _ = paste(project, board, 1, 20_000)

    ids = [clip.id for clip in first.copies + second.copies]
    assert len(set(ids)) == 4 and set(ids).isdisjoint({a.id, b.id})
    assert first.copies[0].fade_in == a.fade_in
    assert first.copies[0].fade_in is not a.fade_in
    assert first.copies[0].fade_in is not second.copies[0].fade_in
    assert validate(project) == []


def test_the_originals_are_untouched() -> None:
    a, b = at(0, 5_000, "k-00000001"), at(0, 5_000, "k-00000002")
    project = lanes([a], [b], [])
    before = copy.deepcopy(project.channels[:2])

    paste(project, held(project, a, b), 1, 50_000)

    assert project.channels[0] == before[0]
    assert project.channels[1].clips[0] is b and b == before[1].clips[0]


def test_a_paste_overwrites_what_it_lands_on_as_a_drop_does() -> None:
    """Trims one clip, removes another and splits a third (D-95)."""
    phrase = at(0, 30_000, "k-000000a1")
    trimmed, covered = (
        at(90_000, 20_000, "k-00000001"),
        at(110_000, 5_000, "k-00000002"),
    )
    long = at(200_000, 100_000, "k-00000003", offset=7_000)
    project = lanes([phrase], [trimmed, covered], [long])

    paste(project, held(project, phrase), 1, 105_000)
    paste(project, held(project, phrase), 2, 230_000)

    assert spans(project.channels[1]) == [(90_000, 105_000), (105_000, 135_000)]
    head, _, tail = project.channels[2].clips
    assert spans(project.channels[2]) == [
        (200_000, 230_000),
        (230_000, 260_000),
        (260_000, 300_000),
    ]
    assert tail.offset == long.offset + 60_000, "the tail plays what it played"
    assert head is long
    assert validate(project) == []


def test_a_paste_past_the_last_lane_makes_channels_in_turn() -> None:
    a, b, c = (at(0, 5_000, f"k-0000000{n}") for n in (1, 2, 3))
    project = lanes([a], [b], [c])

    board = held(project, a, b, c)
    command, _ = paste(project, board, 1, 0)

    made = command.channels
    assert [channel.name for channel in made] == ["Channel 4"]
    assert project.channels[3] is made[0]

    more, _ = paste(project, board, 3, 0)
    assert [(ch.name, ch.color) for ch in more.channels] == [
        ("Channel 5", PALETTE[2]),
        ("Channel 6", PALETTE[3]),
    ], "named and coloured on from the channel before them, not all alike"
    assert made[0].color == PALETTE[1]
    ids = [channel.id for channel in project.channels]
    assert len(set(ids)) == len(ids)
    assert [spans(ch) for ch in project.channels[3:]] == [[(0, 5_000)]] * 3


def test_a_paste_into_a_project_with_no_channels_makes_them() -> None:
    a, b = at(0, 5_000, "k-00000001"), at(0, 5_000, "k-00000002")
    source = lanes([a], [b])
    board = held(source, a, b)
    empty = lanes()

    command, _ = paste(empty, board, 0, 1_000)

    assert [spans(ch) for ch in empty.channels] == [[(1_000, 6_000)]] * 2
    assert empty.channels == command.channels


def test_one_undo_takes_a_whole_paste_back_and_redo_brings_the_same_one() -> None:
    a, b = at(0, 5_000, "k-00000001"), at(2_000, 5_000, "k-00000002")
    in_the_way = at(40_000, 20_000, "k-00000003")
    project = lanes([a], [b, in_the_way])
    before = copy.deepcopy(project)

    command, stack = paste(project, held(project, a, b), 1, 45_000)
    after = copy.deepcopy(project)
    made = list(project.channels[2:])
    assert made and made == command.channels

    stack.undo()
    assert project == before
    stack.redo()
    assert project == after
    assert all(x is y for x, y in zip(project.channels[2:], made, strict=True))


def test_a_paste_of_nothing_changes_nothing() -> None:
    project = lanes([])
    command = PasteClips(project, [], 0, 0, PALETTE)
    assert not command.changes and command.copies == [] and command.channels == []


class Repeating:
    """A random source that says everything twice, so an id minted without
    looking at the ones minted before it comes out again."""

    def __init__(self) -> None:
        self._next = 0xA0000000

    def getrandbits(self, _bits: int) -> int:
        self._next += 1
        return self._next // 2


def test_a_paste_mints_every_id_against_every_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One set of taken ids for the whole paste: the copies, and the tails
    of what they split on every lane they land on."""
    monkeypatch.setattr(model, "_DEFAULT_RNG", Repeating())
    phrase = [at(10_000, 1_000, "k-00000001"), at(0, 1_000, "k-00000002")]
    long = [at(0, 1_000_000, "k-00000003"), at(0, 1_000_000, "k-00000004")]
    project = lanes([phrase[0]], [phrase[1]], [long[0]], [long[1]])

    command, _ = paste(project, held(project, *phrase), 2, 100_000)

    assert len(command.copies) == 2
    assert [len(channel.clips) for channel in project.channels[2:]] == [3, 3]
    everything = [clip.id for ch in project.channels for clip in ch.clips]
    assert len(everything) == len(set(everything))


def test_a_paste_lands_at_a_lane_and_a_time_that_exist() -> None:
    a = at(0, 5_000, "k-00000001")
    project = lanes([a])
    with pytest.raises(ValueError):
        PasteClips(project, held(project, a).held(), -1, 0, PALETTE)
    with pytest.raises(ValueError):
        PasteClips(project, held(project, a).held(), 0, -1, PALETTE)


# --------------------------------------------------------------------------- #
# which lane (D-100)
# --------------------------------------------------------------------------- #


def test_the_lane_is_the_focused_channel_then_the_source_then_the_first() -> None:
    a = at(0, 5_000, "k-00000001")
    project = lanes([], [], [a], [])
    board = held(project, a)
    focused = project.channels[3]

    assert board.lane(project, focused) == 3
    assert board.lane(project, None) == 2, "where it was copied from"
    assert board.lane(project, Channel("c-000000ff", "Gone", PALETTE[0])) == 2

    source = project.channels.pop(2)
    assert board.lane(project, None) == 0, "its source is gone"
    project.channels.insert(1, source)
    assert board.lane(project, None) == 1, "followed where it went"
    assert board.lane(project, focused) == 3


def test_an_emptied_clipboard_points_at_nothing() -> None:
    """Emptied means emptied: not even the channel it was copied from, which
    a paste with nothing held would otherwise still be aimed at."""
    a = at(0, 5_000, "k-00000001")
    project = lanes([], [], [a])
    board = held(project, a)

    board.clear()

    assert not board and board.lane(project, None) == 0


def test_the_source_is_found_by_identity() -> None:
    a = at(0, 5_000, "k-00000001")
    project = lanes([], [a])
    board = held(project, a)
    project.channels[0] = copy.deepcopy(project.channels[1])
    assert project.channels[0] == project.channels[1]

    assert board.lane(project, None) == 1


# --------------------------------------------------------------------------- #
# the project's clipboard (D-99)
# --------------------------------------------------------------------------- #

SAMPLE = MediaFile("m-00000001", "a.wav", "a.wav", SAMPLE_RATE, 1, 1_000_000)


def a_document() -> tuple[Document, Clip]:
    document = Document()
    document.push(AddMedia(document.project, [SAMPLE]))
    channel = Channel("c-00000001", "A", PALETTE[0])
    document.push(AddChannel(document.project, channel))
    clip = Clip("k-00000001", SAMPLE.id, 0, 0, 10_000)
    document.push(DropClips(document.project, channel, [clip]))
    return document, clip


def test_a_paste_whose_sample_has_left_the_pool_cannot_be_made() -> None:
    document, clip = a_document()
    document.clipboard.hold(document.project, [clip])
    assert document.clipboard.pastable(document.project)

    document.undo()
    assert document.clipboard.pastable(document.project), "the sample is still there"
    document.undo()
    document.undo()

    assert document.clipboard.missing(document.project) == [SAMPLE.id]
    assert not document.clipboard.pastable(document.project)
    with pytest.raises(ValueError, match=SAMPLE.id):
        PasteClips(document.project, document.clipboard.held(), 0, 0, PALETTE)


def test_an_empty_clipboard_is_not_pastable() -> None:
    document, _ = a_document()
    assert not document.clipboard
    assert not document.clipboard.pastable(document.project)


def test_the_clipboard_survives_edits_and_undo() -> None:
    document, clip = a_document()
    document.clipboard.hold(document.project, [clip])

    document.push(MoveClips(document.project, [clip], 50_000))
    document.undo()
    document.undo()

    assert document.clipboard.pastable(document.project)
    assert [c.id for _, c in document.clipboard.held()] == [clip.id]


def test_new_and_open_empty_the_clipboard(tmp_path: Path) -> None:
    document, clip = a_document()
    document.save_as(tmp_path / "a.3dim")
    document.clipboard.hold(document.project, [clip])

    document.new()
    assert not document.clipboard

    document.open(tmp_path / "a.3dim")
    document.clipboard.hold(document.project, document.project.channels[0].clips)
    document.open(tmp_path / "a.3dim")
    assert not document.clipboard, "the same file again is still another project"


def test_copying_is_not_an_edit() -> None:
    document, clip = a_document()
    stacked, dirty = len(document._stack), document.is_dirty
    calls: list[int] = []
    document.observe(lambda: calls.append(1))

    document.clipboard.hold(document.project, [clip])

    assert (len(document._stack), document.is_dirty, calls) == (stacked, dirty, [])
