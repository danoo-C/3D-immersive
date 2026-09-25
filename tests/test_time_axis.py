"""The time axis: scroll and zoom as numbers, with no window (D-94)."""

from __future__ import annotations

import math

import pytest

from immersive.core.time import SAMPLE_RATE
from immersive.ui.time_axis import DEFAULT_SCALE, MAX_SCALE, MIN_SCALE, TimeAxis

HOUR = SAMPLE_RATE * 3600

#: Every zoom from the closest to the widest, a factor of three apart.
SCALES = [
    MIN_SCALE * 3**n for n in range(int(math.log(MAX_SCALE / MIN_SCALE, 3)) + 1)
] + [MAX_SCALE]


def scrolled(scale: float, *, width: int = 1000, extent: float = 10 * HOUR) -> TimeAxis:
    """An axis at `scale`, scrolled well away from both ends."""
    axis = TimeAxis(scale, width=width, extent=extent)
    axis.scroll_to(axis.span() // 3)
    return axis


def told(axis: TimeAxis) -> list[int]:
    """A list that grows by one each time `axis` tells its observers."""
    calls: list[int] = []
    axis.observe(lambda: calls.append(1))
    return calls


# --------------------------------------------------------------------------- #
# converting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("scale", SCALES)
def test_a_sample_and_its_x_convert_back_at_every_zoom(scale: float) -> None:
    axis = scrolled(scale)
    first, last = axis.visible()
    for sample in (first, (first + last) / 2, last, first + 0.5, 12_345.0):
        assert axis.sample_at(axis.x_of(sample)) == pytest.approx(sample, abs=1e-6)
    for x in (0.0, 0.5, 333.0, 1000.0):
        assert axis.x_of(axis.sample_at(x)) == pytest.approx(x, abs=1e-9)


def test_the_view_starts_at_the_offset_and_spans_the_width() -> None:
    axis = TimeAxis(480.0, width=800, extent=HOUR)
    axis.scroll_to(250)

    assert axis.visible() == (250 * 480.0, 1050 * 480.0)
    assert axis.x_of(250 * 480) == 0


def test_the_span_is_the_extent_at_the_scale_rounded_up() -> None:
    axis = TimeAxis(1000.0, extent=48_001)
    assert axis.span() == 49


# --------------------------------------------------------------------------- #
# zooming
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("factor", [1.25, 0.8, 2.0, 0.5, 10.0, 0.1])
@pytest.mark.parametrize("x", [0, 1, 250, 499.5, 999, 1000])
def test_zooming_keeps_the_point_under_it_within_half_a_pixel(
    x: float, factor: float
) -> None:
    axis = scrolled(DEFAULT_SCALE)
    before = axis.sample_at(x)

    axis.zoom_about(x, factor)

    assert axis.scale == pytest.approx(DEFAULT_SCALE * factor)
    assert abs(axis.sample_at(x) - before) <= 0.5 * axis.scale


def test_zooming_about_the_right_edge_does_not_anchor_the_left() -> None:
    """The mutation this is for: zooming about x = 0 whatever x was asked."""
    axis = scrolled(DEFAULT_SCALE)
    left, right = axis.visible()

    axis.zoom_about(axis.width, 2.0)

    assert axis.visible()[1] == pytest.approx(right, abs=axis.scale)
    assert axis.visible()[0] < left


def test_the_scale_stops_at_both_ends() -> None:
    axis = scrolled(DEFAULT_SCALE)
    for _ in range(200):
        axis.zoom_about(500, 0.5)
    assert axis.scale == MIN_SCALE
    for _ in range(200):
        axis.zoom_about(500, 2.0)
    assert axis.scale == MAX_SCALE

    assert TimeAxis(0.001).scale == MIN_SCALE
    assert TimeAxis(1e12).scale == MAX_SCALE


# --------------------------------------------------------------------------- #
# scrolling
# --------------------------------------------------------------------------- #


def test_scrolling_stops_at_the_start() -> None:
    axis = scrolled(DEFAULT_SCALE)

    axis.scroll_by(-(10**9))

    assert axis.offset == 0
    assert axis.visible()[0] == 0


def test_scrolling_stops_where_the_extent_is_on_show() -> None:
    axis = scrolled(DEFAULT_SCALE, extent=HOUR)

    axis.scroll_by(10**9)

    assert axis.offset == axis.span() - axis.width
    assert axis.visible()[1] >= HOUR


def test_an_extent_narrower_than_the_view_does_not_scroll() -> None:
    axis = TimeAxis(DEFAULT_SCALE, width=1000, extent=SAMPLE_RATE)

    axis.scroll_by(50)

    assert axis.offset == 0


def test_shrinking_the_extent_scrolls_back_rather_than_past_the_end() -> None:
    axis = scrolled(DEFAULT_SCALE)
    calls = told(axis)

    axis.set_extent(SAMPLE_RATE * 60)

    assert axis.offset == axis.span() - axis.width
    assert calls == [1]


def test_widening_the_view_at_the_end_scrolls_back() -> None:
    axis = TimeAxis(DEFAULT_SCALE, width=1000, extent=HOUR)
    axis.scroll_by(10**9)

    axis.set_width(1500)

    assert axis.offset == axis.span() - 1500


# --------------------------------------------------------------------------- #
# telling observers
# --------------------------------------------------------------------------- #


def test_every_change_is_told_once() -> None:
    axis = scrolled(DEFAULT_SCALE)
    calls = told(axis)

    axis.scroll_by(10)
    axis.scroll_to(0)
    axis.zoom_about(100, 2.0)
    axis.set_width(1200)
    axis.set_extent(2 * HOUR)

    assert calls == [1] * 5


def test_a_change_that_changes_nothing_tells_nobody() -> None:
    """A view repaints on every call, and mouse-moves arrive by the hundred."""
    axis = scrolled(DEFAULT_SCALE)
    calls = told(axis)

    axis.scroll_by(0)
    axis.scroll_to(axis.offset)
    axis.zoom_about(321, 1.0)
    axis.set_width(axis.width)
    axis.set_extent(axis.extent)
    axis.scroll_to(0)
    calls.clear()
    axis.scroll_by(-5)  # already at the start

    assert calls == []
