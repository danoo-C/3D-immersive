"""Activities: anything slow, as the info box shows it (D-116). Headless."""

from __future__ import annotations

from immersive.ui.activity import SHOW_AFTER, Activities, Activity


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def running(work: Activity) -> bool:
    """`running`, read afresh: mypy would keep an assert's narrowing."""
    return work.running


def test_begin_update_finish() -> None:
    board = Activities(Clock())
    work = board.begin("Importing 0 of 3 files", maximum=300)
    assert board.running() == [work] and running(work)
    assert (work.label, work.value, work.maximum) == ("Importing 0 of 3 files", 0, 300)

    work.update(150, label="Importing 1 of 3 files")
    assert (work.label, work.value, work.fraction) == (
        "Importing 1 of 3 files",
        150,
        0.5,
    )

    work.finish()
    assert board.running() == [] and not running(work)
    work.finish()  # a second finish does nothing
    work.update(300)
    assert work.value == 150, "an activity finished is left as it was"


def test_a_value_is_held_within_its_maximum() -> None:
    work = Activities(Clock()).begin("x", maximum=10)
    work.update(25)
    assert work.value == 10
    work.update(-3)
    assert work.value == 0
    work.update(8, maximum=4)
    assert (work.value, work.maximum) == (4, 4)


def test_a_maximum_of_0_is_busy_with_no_measure() -> None:
    work = Activities(Clock()).begin("Loading")
    assert work.maximum == 0 and work.fraction is None
    work.update(5)
    assert work.value == 0


def test_running_is_in_the_order_begun() -> None:
    board = Activities(Clock())
    first, second = board.begin("a"), board.begin("b")
    assert board.running() == [first, second]
    first.finish()
    assert board.running() == [second]


def test_shown_only_once_run_for_show_after() -> None:
    clock = Clock()
    board = Activities(clock)
    work = board.begin("x")
    assert board.shown() == []
    assert board.next_shown_in() == SHOW_AFTER

    clock.now += SHOW_AFTER / 2
    later = board.begin("y")
    assert board.shown() == []
    assert board.next_shown_in() == SHOW_AFTER / 2, "the first due, first"

    clock.now += SHOW_AFTER / 2
    assert board.shown() == [work]
    clock.now += SHOW_AFTER / 2
    assert board.shown() == [work, later]
    assert board.next_shown_in() is None


def test_observers_hear_every_begin_update_and_finish() -> None:
    board = Activities(Clock())
    heard: list[int] = []
    board.observe(lambda: heard.append(len(board.running())))
    work = board.begin("x", maximum=2)
    work.update(1)
    work.finish()
    work.finish()
    assert heard == [1, 1, 0]
