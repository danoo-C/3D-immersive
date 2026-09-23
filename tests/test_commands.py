"""The undo stack: what it keeps, what it throws away, and what it refuses.

Nothing here touches Qt or audio. The commands are the real ones from
`core.edits` wherever a real one fits, so these tests fail if the stack and
the edits disagree about anything.
"""

from __future__ import annotations

import copy

import pytest

from immersive.core.commands import Command, Compound, InvalidEdit, UndoStack
from immersive.core.edits import (
    AddChannel,
    AddClip,
    MoveClip,
    SetAttribute,
)
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Project,
    mint_id,
)
from immersive.core.time import SAMPLE_RATE

MEDIA = "m-00000001"


def a_project(*, clips: bool = False) -> Project:
    """One channel, one media file, and optionally two clips with a gap."""
    media = MediaFile(MEDIA, "a.wav", "a.wav", SAMPLE_RATE, 1, 1_000_000)
    channel = Channel("c-00000001", "A", "#A855F7")
    if clips:
        channel.clips = [
            Clip("k-00000001", MEDIA, 0, 0, 24_000),
            Clip("k-00000002", MEDIA, 48_000, 0, 24_000),
        ]
    return Project(media_pool=[media], channels=[channel])


def is_dirty(stack: UndoStack) -> bool:
    """`stack.is_dirty`, read through a call.

    mypy narrows a property to a literal at the first assertion and then
    calls the opposite assertion unreachable - which is precisely wrong for a
    flag whose whole job is to change on the next line. The same goes for
    `can_undo` and `can_redo` below.
    """
    return stack.is_dirty


def can_undo(stack: UndoStack) -> bool:
    return stack.can_undo


def can_redo(stack: UndoStack) -> bool:
    return stack.can_redo


class Records(Command):
    """A command that writes its name into a shared log when it runs.

    The only way to see the *order* a compound undoes in when its members are
    independent enough not to leave a trace in the project.
    """

    def __init__(self, log: list[str], name: str) -> None:
        self.log = log
        self.name = name

    def do(self) -> None:
        self.log.append(f"do {self.name}")

    def undo(self) -> None:
        self.log.append(f"undo {self.name}")


class Explodes(Command):
    def do(self) -> None:
        raise RuntimeError("boom")

    def undo(self) -> None:  # pragma: no cover - reaching this is the bug
        raise AssertionError("undo of a command that never applied")


# --------------------------------------------------------------------------- #
# push, undo, redo
# --------------------------------------------------------------------------- #


def test_pushing_runs_the_command() -> None:
    project = a_project()
    stack = UndoStack(project)
    stack.push(SetAttribute(project.channels[0], "name", "B"))
    assert project.channels[0].name == "B"
    assert len(stack) == 1


def test_undo_and_redo_walk_the_stack() -> None:
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]
    stack.push(SetAttribute(channel, "name", "B"))
    stack.push(SetAttribute(channel, "name", "C"))

    assert stack.undo() and channel.name == "B"
    assert stack.undo() and channel.name == "A"
    assert stack.redo() and channel.name == "B"
    assert stack.redo() and channel.name == "C"


def test_an_exhausted_stack_says_so_rather_than_raising() -> None:
    stack = UndoStack(a_project())
    assert not can_undo(stack) and not can_redo(stack)
    assert stack.undo() is False
    assert stack.redo() is False


def test_a_new_edit_discards_the_redo_branch() -> None:
    """The standard behaviour, asserted because a redo *tree* is a defensible
    alternative that this deliberately is not."""
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]
    stack.push(SetAttribute(channel, "name", "B"))
    stack.undo()
    assert can_redo(stack)

    stack.push(SetAttribute(channel, "gain_db", -6.0))

    assert not can_redo(stack)
    assert stack.redo() is False
    assert channel.name == "A", "the discarded branch came back"


def test_a_thousand_edits_undo_back_to_the_starting_project() -> None:
    """F-4's "unlimited depth within a session", pinned to a number.

    Memory is not a stated constraint and is not pretended to be one here; the
    test says what "unlimited" was taken to mean, which is that nothing
    trims the stack behind your back.
    """
    project = a_project()
    before = copy.deepcopy(project)
    stack = UndoStack(project)

    taken = {MEDIA, "c-00000001"}
    for _ in range(1_000):
        identifier = mint_id("c", taken)
        taken.add(identifier)
        stack.push(AddChannel(project, Channel(identifier, "x", "#111111")))

    assert len(stack) == 1_000
    while stack.undo():
        pass
    assert project == before


# --------------------------------------------------------------------------- #
# refusal
# --------------------------------------------------------------------------- #


def test_an_edit_that_would_break_an_invariant_is_refused() -> None:
    project = a_project(clips=True)
    before = copy.deepcopy(project)
    stack = UndoStack(project)
    second = project.channels[0].clips[1]

    with pytest.raises(InvalidEdit, match="must not overlap"):
        stack.push(MoveClip(second, 12_000))

    assert project == before, "the refused edit left the project changed"
    assert len(stack) == 0, "the refused edit left an entry on the stack"
    assert not can_redo(stack)


def test_a_refusal_carries_every_problem_not_just_the_first() -> None:
    """`validate()` returns the whole list, and the refusal keeps it - because
    a dialogue that reports one problem at a time is five dialogues."""
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]

    with pytest.raises(InvalidEdit) as caught:
        stack.push(
            Compound(
                [
                    SetAttribute(channel, "color", "purple"),
                    SetAttribute(channel, "pan", 5.0),
                ]
            )
        )

    messages = [problem.message for problem in caught.value.problems]
    assert len(messages) == 2
    assert any("purple" in message for message in messages)
    assert any("pan" in message for message in messages)


def test_a_refusal_does_not_disturb_a_redo_branch() -> None:
    """Nothing happened, so nothing should have been thrown away."""
    project = a_project(clips=True)
    stack = UndoStack(project)
    channel = project.channels[0]
    stack.push(SetAttribute(channel, "name", "B"))
    stack.undo()

    with pytest.raises(InvalidEdit):
        stack.push(MoveClip(channel.clips[1], 12_000))

    assert stack.redo() and channel.name == "B"


# --------------------------------------------------------------------------- #
# compound
# --------------------------------------------------------------------------- #


def test_a_compound_is_one_stack_entry() -> None:
    """D-23's magnetic drop: placing a clip also trims its neighbour, and one
    Ctrl+Z must put both back."""
    project = a_project(clips=True)
    before = copy.deepcopy(project)
    stack = UndoStack(project)
    channel = project.channels[0]
    dropped = Clip("k-00000003", MEDIA, 12_000, 0, 24_000)

    stack.push(
        Compound(
            [
                SetAttribute(channel.clips[0], "length", 12_000),
                AddClip(channel, dropped),
            ],
            label="drop clip",
        )
    )

    assert [clip.id for clip in channel.clips] == [
        "k-00000001",
        "k-00000003",
        "k-00000002",
    ]
    assert len(stack) == 1
    stack.undo()
    assert project == before


def test_a_compound_undoes_its_members_in_reverse() -> None:
    """Two edits to the same field, where order is the whole answer.

    Undone forwards, the first member's restore is overwritten by the
    second's and the field ends at the intermediate value.
    """
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]

    stack.push(
        Compound(
            [
                SetAttribute(channel, "gain_db", -6.0),
                SetAttribute(channel, "gain_db", -12.0),
            ]
        )
    )
    assert channel.gain_db == -12.0
    stack.undo()
    assert channel.gain_db == 0.0, "undone forwards, not in reverse"


def test_a_compound_undoes_in_reverse_even_when_the_project_cannot_show_it() -> None:
    log: list[str] = []
    compound = Compound([Records(log, "one"), Records(log, "two")])
    compound.do()
    compound.undo()
    assert log == ["do one", "do two", "undo two", "undo one"]


def test_a_compound_that_fails_halfway_undoes_what_it_applied() -> None:
    """A half-applied compound is worse than a refused one: it leaves the
    project in a state no single undo can reach."""
    project = a_project()
    before = copy.deepcopy(project)
    stack = UndoStack(project)

    with pytest.raises(RuntimeError, match="boom"):
        stack.push(
            Compound([SetAttribute(project.channels[0], "name", "B"), Explodes()])
        )

    assert project == before
    assert len(stack) == 0


# --------------------------------------------------------------------------- #
# gestures
# --------------------------------------------------------------------------- #


def test_a_drag_inside_a_gesture_is_one_entry_ending_where_it_started() -> None:
    """The coalescing rule from 02-architecture.md, *Undo*.

    The second assertion is the one that matters: a merge that kept the
    *latest* before-value would leave one entry whose undo walked back a
    single step.
    """
    project = a_project(clips=True)
    stack = UndoStack(project)
    # The trailing clip, dragged into open timeline - a drag that ran into its
    # neighbour would be refused by validation and prove something else.
    clip = project.channels[0].clips[1]

    with stack.gesture():
        for start in range(48_500, 73_500, 500):
            stack.push(MoveClip(clip, start))

    assert clip.start == 73_000
    assert len(stack) == 1
    stack.undo()
    assert clip.start == 48_000


def test_the_same_moves_outside_a_gesture_are_fifty_entries() -> None:
    project = a_project(clips=True)
    stack = UndoStack(project)
    clip = project.channels[0].clips[1]

    for start in range(48_500, 73_500, 500):
        stack.push(MoveClip(clip, start))

    assert len(stack) == 50
    stack.undo()
    assert clip.start == 72_500


def test_two_gestures_do_not_merge_across_their_boundary() -> None:
    """The most annoying possible undo bug is one that reverses more than the
    user did. Mouse-up ends a gesture, and nothing merges past it."""
    project = a_project(clips=True)
    stack = UndoStack(project)
    clip = project.channels[0].clips[0]

    with stack.gesture():
        stack.push(MoveClip(clip, 1_000))
        stack.push(MoveClip(clip, 2_000))
    with stack.gesture():
        stack.push(MoveClip(clip, 3_000))

    assert len(stack) == 2
    stack.undo()
    assert clip.start == 2_000
    stack.undo()
    assert clip.start == 0


def test_a_gesture_does_not_reach_back_to_the_command_before_it() -> None:
    project = a_project(clips=True)
    stack = UndoStack(project)
    clip = project.channels[0].clips[0]

    stack.push(MoveClip(clip, 1_000))
    with stack.gesture():
        stack.push(MoveClip(clip, 2_000))

    assert len(stack) == 2


def test_nested_gestures_are_still_one_entry() -> None:
    """The UI will nest them the first time a drag handler calls a helper that
    opens its own gesture, and the inner one must not end the outer."""
    project = a_project(clips=True)
    stack = UndoStack(project)
    clip = project.channels[0].clips[0]

    with stack.gesture():
        stack.push(MoveClip(clip, 1_000))
        with stack.gesture():
            stack.push(MoveClip(clip, 2_000))
        stack.push(MoveClip(clip, 3_000))

    assert len(stack) == 1
    stack.undo()
    assert clip.start == 0


def test_a_gesture_closes_even_when_its_body_raises() -> None:
    project = a_project(clips=True)
    stack = UndoStack(project)
    clip = project.channels[0].clips[0]

    with pytest.raises(RuntimeError), stack.gesture():
        stack.push(MoveClip(clip, 1_000))
        raise RuntimeError("the drag handler fell over")

    stack.push(MoveClip(clip, 2_000))
    assert len(stack) == 2, "the gesture outlived the block that opened it"


def test_unmergeable_commands_in_a_gesture_still_stack_up() -> None:
    """A gesture coalesces what *can* coalesce; it is not a way to hide edits."""
    project = a_project(clips=True)
    stack = UndoStack(project)
    channel = project.channels[0]

    with stack.gesture():
        stack.push(MoveClip(channel.clips[0], 1_000))
        stack.push(SetAttribute(channel, "name", "B"))
        stack.push(MoveClip(channel.clips[0], 2_000))

    assert len(stack) == 3


def test_moves_of_different_clips_do_not_merge() -> None:
    project = a_project(clips=True)
    stack = UndoStack(project)
    first, second = project.channels[0].clips

    with stack.gesture():
        stack.push(MoveClip(first, 1_000))
        stack.push(MoveClip(second, 49_000))

    assert len(stack) == 2


# --------------------------------------------------------------------------- #
# dirty
# --------------------------------------------------------------------------- #


def test_a_fresh_stack_is_clean() -> None:
    assert not UndoStack(a_project()).is_dirty


def test_an_edit_dirties_and_undoing_it_cleans() -> None:
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]

    stack.push(SetAttribute(channel, "name", "B"))
    assert is_dirty(stack)
    stack.undo()
    assert not is_dirty(stack)
    stack.redo()
    assert is_dirty(stack)


def test_saving_moves_the_save_point() -> None:
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]

    stack.push(SetAttribute(channel, "name", "B"))
    stack.mark_saved()
    assert not is_dirty(stack)

    stack.push(SetAttribute(channel, "gain_db", -6.0))
    assert is_dirty(stack)
    stack.undo()
    assert not is_dirty(stack)


def test_an_orphaned_save_point_is_dirty_for_ever() -> None:
    """The one failure here that loses work is claiming clean when it cannot
    be proved, so the stack refuses to.

    After the undo the saved state lives only in the redo branch; the new edit
    discards that branch, and the project now differs from what was written
    while the stack is exactly as deep as it was at the save point. Anything
    that answers by depth says "clean" here.
    """
    project = a_project()
    stack = UndoStack(project)
    channel = project.channels[0]

    stack.push(SetAttribute(channel, "name", "B"))
    stack.mark_saved()
    stack.undo()
    assert is_dirty(stack)

    stack.push(SetAttribute(channel, "gain_db", -6.0))
    assert len(stack) == 1, "the premise of this test has moved"
    assert is_dirty(stack)

    stack.undo()
    assert is_dirty(stack)
    stack.redo()
    assert is_dirty(stack)


def test_a_refused_edit_does_not_dirty_the_project() -> None:
    project = a_project(clips=True)
    stack = UndoStack(project)
    with pytest.raises(InvalidEdit):
        stack.push(MoveClip(project.channels[0].clips[1], 12_000))
    assert not is_dirty(stack)
