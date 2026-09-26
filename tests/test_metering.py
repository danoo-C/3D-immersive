"""How a meter moves (D-118): headless, by a clock the test steps."""

from __future__ import annotations

import pytest

from immersive.ui.metering import FALL, FLOOR, HOLD, Ballistics, along, to_db


class Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def fed(clock: Clock, meter: Ballistics, seconds: float, peak: float = 0.0) -> None:
    clock.now += seconds
    meter.feed(peak, peak)


def test_the_scale_is_dbfs_floored_at_60() -> None:
    assert to_db(1.0) == 0.0
    assert to_db(0.5) == pytest.approx(-6.0206, abs=1e-4)
    assert to_db(0.0) == FLOOR and to_db(1e-5) == FLOOR
    assert along(FLOOR) == 0.0 and along(-30.0) == 0.5 and along(0.0) == 1.0
    assert along(3.0) == 1.0, "past full scale is the end of the bar"


def test_a_bar_rises_at_once_and_falls_at_24_db_a_second() -> None:
    clock = Clock()
    meter = Ballistics(clock)
    meter.feed(0.5, 0.25)
    assert meter.levels == [pytest.approx(to_db(0.5)), pytest.approx(to_db(0.25))]

    fed(clock, meter, 0.5)
    assert meter.levels[0] == pytest.approx(to_db(0.5) - FALL * 0.5)
    fed(clock, meter, 10.0)
    assert meter.levels == [FLOOR, FLOOR]


def test_the_hold_keeps_the_highest_for_a_second_and_a_half_then_falls() -> None:
    clock = Clock()
    meter = Ballistics(clock)
    meter.feed(0.5, 0.5)
    top = to_db(0.5)

    fed(clock, meter, 1.0)
    assert meter.holds[0] == pytest.approx(top), "held"
    fed(clock, meter, HOLD - 1.0)
    assert meter.holds[0] == pytest.approx(top), "held for all of HOLD"
    fed(clock, meter, 0.5)
    assert meter.holds[0] == pytest.approx(top - FALL * 0.5), "then falling"
    assert meter.holds[0] >= meter.levels[0]


def test_a_hold_never_sits_below_its_bar() -> None:
    clock = Clock()
    meter = Ballistics(clock)
    meter.feed(0.1, 0.1)
    fed(clock, meter, 2.0, 0.09)
    assert meter.holds[0] >= meter.levels[0]


def latched(meter: Ballistics) -> bool:
    """`clipped`, read afresh: mypy would keep an assert's narrowing."""
    return meter.clipped


def test_the_latch_is_past_full_scale_not_at_it_and_stays() -> None:
    clock = Clock()
    meter = Ballistics(clock)
    meter.feed(1.0, 1.0)
    assert not latched(meter), "full scale itself is not a clip"
    fed(clock, meter, 0.1, 1.0001)
    assert latched(meter)
    fed(clock, meter, 5.0)
    assert latched(meter), "until cleared, whatever follows"
    meter.clear()
    assert not latched(meter)


def test_feed_says_whether_anything_moved() -> None:
    """So a silent channel's meter is never repainted."""
    clock = Clock()
    meter = Ballistics(clock)
    assert not meter.feed(0.0, 0.0)
    assert meter.feed(0.5, 0.0)
    fed(clock, meter, 60.0)
    assert not meter.feed(0.0, 0.0)
