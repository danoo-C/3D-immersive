"""What an icon says (M5 phase 3, D-146): its radius from its distance and
its opacity from its gain, and a channel not heard. Qt-free."""

from __future__ import annotations

import pytest

from immersive.core.model import Position
from immersive.ui.spatial.look import NOT_HEARD, opacity, radius


def test_the_radius_is_ten_pixels_at_a_metre_and_two_less_each_doubling() -> None:
    assert radius(Position(1.0, 0.0, 0.0)) == pytest.approx(10.0)
    assert radius(Position(0.0, 2.0, 0.0)) == pytest.approx(8.0)
    assert radius(Position(0.0, -4.0, 0.0)) == pytest.approx(6.0)
    assert radius(Position(0.0, 0.5, 0.0)) == pytest.approx(12.0)


def test_the_distance_is_in_three_dimensions() -> None:
    """Above the head is as far as ahead: the top view tells of height."""
    ahead = radius(Position(0.0, 3.0, 0.0))
    assert radius(Position(0.0, 0.0, 3.0)) == pytest.approx(ahead)
    assert radius(Position(1.0, 2.0, 2.0)) == pytest.approx(ahead)
    assert radius(Position(0.0, 1.0, 2.0)) < radius(Position(0.0, 1.0, 0.0))


def test_the_radius_stays_within_its_limits() -> None:
    assert radius(Position()) == 13.0, "at the listener"
    assert radius(Position(0.0, 0.01, 0.0)) == 13.0
    assert radius(Position(0.0, 1000.0, 0.0)) == 5.0


def test_the_opacity_falls_with_gain_like_loudness() -> None:
    assert opacity(0.0, heard=True) == 1.0
    assert opacity(6.0, heard=True) == 1.0, "a boost looks like 0 dB"
    assert opacity(-10.0, heard=True) == pytest.approx(0.7)
    assert opacity(-20.0, heard=True) == pytest.approx(0.55)


def test_the_floor_is_above_a_channel_not_heard() -> None:
    """No gain looks muted, and a channel not heard is at a quarter
    whatever its gain."""
    assert opacity(-60.0, heard=True) > 0.4 > NOT_HEARD
    assert opacity(float("-inf"), heard=True) == pytest.approx(0.4)
    assert NOT_HEARD == 0.25
    assert opacity(0.0, heard=False) == NOT_HEARD
    assert opacity(12.0, heard=False) == NOT_HEARD
