"""A source being dragged (M5 phase 2, D-144, D-145): the sides as the drag
has them, the one edit it makes, and cancelling. Qt-free."""

from __future__ import annotations

from immersive.core.commands import UndoStack
from immersive.core.model import (
    Channel,
    Pairing,
    Placement,
    Position,
    Project,
    mirror,
    sides,
)
from immersive.ui.spatial.placing import LEFT, POINT, RIGHT, Placing


def channel(mode: Pairing = Pairing.POINT) -> Channel:
    return Channel(
        "c-00000001",
        "C",
        "#A855F7",
        position=Position(-1.0, 1.0, 0.0),
        placement=Placement(
            mode=mode,
            right=Position(2.0, 0.5, 0.0),
            pivot=Position(0.0, 0.5, 0.0),
            mirrored=(True, False, False),
        ),
    )


def dragged(placed: Channel, side: int, to: Position) -> Placing:
    placing = Placing()
    placing.begin(placed, side)
    placing.move(to)
    return placing


def test_a_point_moves_as_dragged() -> None:
    placed = channel()
    placing = dragged(placed, POINT, Position(3.0, 2.0, 1.0))

    assert placing.sides(placed) == (Position(3.0, 2.0, 1.0),) * 2
    assert placing.sides(channel()) is None, "only the channel dragged"


def test_a_linked_pair_grabbed_by_its_left_mirrors_its_right() -> None:
    placed = channel(Pairing.LINKED)
    to = Position(-2.0, 3.0, 0.5)
    placing = dragged(placed, LEFT, to)

    assert placing.sides(placed) == (to, Position(2.0, 3.0, 0.5))


def test_a_linked_pair_grabbed_by_its_right_leads_with_its_right() -> None:
    """The right side under the pointer, and the left in its mirror about
    the pivot, x = 0 here; the edit stores that left (D-145)."""
    placed = channel(Pairing.LINKED)
    to = Position(1.5, -1.0, 0.25)
    placing = dragged(placed, RIGHT, to)

    assert placing.sides(placed) == (Position(-1.5, -1.0, 0.25), to)
    stack = UndoStack(Project(channels=[placed]))
    edit = placing.end()
    assert edit is not None
    stack.push(edit)
    assert sides(placed)[1] == to
    assert placed.position == mirror(to, Position(0.0, 0.5, 0.0), (True, False, False))


def test_a_free_pair_moves_the_side_grabbed_alone() -> None:
    placed = channel(Pairing.FREE)
    left, right = sides(placed)
    to = Position(0.0, -2.0, 1.0)

    assert dragged(placed, LEFT, to).sides(placed) == (to, right)
    placing = dragged(placed, RIGHT, to)
    assert placing.sides(placed) == (left, to)
    stack = UndoStack(Project(channels=[placed]))
    edit = placing.end()
    assert edit is not None
    stack.push(edit)
    assert placed.placement.right == to and placed.position == left


def test_the_release_is_one_edit_undone_in_one_step() -> None:
    placed = channel()
    stack = UndoStack(Project(channels=[placed]))
    placing = Placing()
    placing.begin(placed, POINT)
    for step in range(1, 30):
        placing.move(Position(step / 10, 1.0, 0.0))
    assert placed.position == Position(-1.0, 1.0, 0.0), "no edit until the release"

    edit = placing.end()
    assert edit is not None
    stack.push(edit)
    assert placed.position == Position(2.9, 1.0, 0.0)
    assert len(stack) == 1
    stack.undo()
    assert placed.position == Position(-1.0, 1.0, 0.0)
    assert placing.channel is None


def test_a_drag_that_moved_nothing_makes_no_edit_and_esc_none() -> None:
    placed = channel()
    placing = Placing()
    placing.begin(placed, POINT)
    assert placing.end() is None

    placing = dragged(placed, POINT, Position(5.0, 5.0, 5.0))
    placing.cancel()
    assert placing.channel is None and placing.sides(placed) is None
    assert placing.end() is None
    assert placed.position == Position(-1.0, 1.0, 0.0)


def test_observers_are_told_of_the_start_each_move_and_the_end() -> None:
    placed = channel()
    placing = Placing()
    told: list[int] = []
    placing.observe(lambda: told.append(1))
    placing.begin(placed, POINT)
    placing.move(Position(1.0, 1.0, 0.0))
    placing.move(Position(1.0, 1.0, 0.0))  # the same: nothing moved
    placing.move(Position(2.0, 1.0, 0.0))
    placing.cancel()

    assert len(told) == 4
