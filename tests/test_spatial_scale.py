"""The ortho views' shared scale (M5 phase 1, D-143): metres to pixels and
back, zoom about a point, pan, and the limits. Qt-free."""

from __future__ import annotations

import pytest

from immersive.ui.spatial.scale import FIRST_SPAN, NARROWEST, WIDEST, Scale

#: A view wider than it is tall, so its shorter side is the height.
W, H = 600.0, 400.0


def test_at_first_the_head_is_centred_and_the_shorter_side_shows_8_m() -> None:
    scale = Scale()

    assert scale.pixel("top", W, H, 0.0, 0.0) == (300.0, 200.0)
    assert FIRST_SPAN == 8.0
    assert scale.per_metre(W, H) == pytest.approx(H / 8.0)


def test_right_is_plus_x_and_up_is_plus_the_views_vertical() -> None:
    """In both views: a source 1 m right is right of the centre, 2 m ahead
    is up-screen in the top view, and 2 m up is up-screen in the front."""
    scale = Scale()
    per = scale.per_metre(W, H)

    for plane in ("top", "front"):
        x, y = scale.pixel(plane, W, H, 1.0, 2.0)
        assert x == pytest.approx(W / 2 + per)
        assert y == pytest.approx(H / 2 - 2 * per), "up-screen"


def test_metres_and_pixels_turn_back_into_each_other() -> None:
    scale = Scale()
    scale.pan("front", W, H, 37.0, -11.0)
    scale.zoom_about("top", W, H, 100.0, 50.0, 1.7)
    for plane in ("top", "front"):
        x, y = scale.pixel(plane, W, H, -1.25, 3.5)
        assert scale.metres(plane, W, H, x, y) == pytest.approx((-1.25, 3.5))


def test_a_zoom_keeps_the_metre_under_the_pointer() -> None:
    scale = Scale()
    before = scale.metres("top", W, H, 450.0, 120.0)
    scale.zoom_about("top", W, H, 450.0, 120.0, 0.5)

    assert scale.span == pytest.approx(4.0)
    assert scale.metres("top", W, H, 450.0, 120.0) == pytest.approx(before)


def test_a_zoom_goes_no_closer_than_2_m_nor_wider_than_200() -> None:
    scale = Scale()
    for _ in range(40):
        scale.zoom_about("top", W, H, 300.0, 200.0, 0.5)
    assert scale.span == NARROWEST == 2.0
    for _ in range(40):
        scale.zoom_about("top", W, H, 300.0, 200.0, 2.0)
    assert scale.span == WIDEST == 200.0


def test_a_pan_moves_the_metre_with_the_pointer() -> None:
    """Dragged right and down by some pixels, what was under the pointer is
    under it still, where the pointer went."""
    scale = Scale()
    before = scale.metres("top", W, H, 200.0, 100.0)
    scale.pan("top", W, H, 30.0, 20.0)

    assert scale.metres("top", W, H, 230.0, 120.0) == pytest.approx(before)


def test_a_pan_moves_both_views_across_and_one_up_and_down() -> None:
    scale = Scale()
    scale.pan("top", W, H, 50.0, 40.0)

    assert scale.x != 0.0, "X is both views'"
    assert scale.centre("top") != 0.0
    assert scale.centre("front") == 0.0, "the front view's Z is its own"


def test_observers_are_told_once_a_change_and_not_for_nothing() -> None:
    scale = Scale()
    told: list[int] = []
    scale.observe(lambda: told.append(1))
    scale.pan("top", W, H, 10.0, 0.0)
    scale.pan("top", W, H, 0.0, 0.0)
    for _ in range(40):
        scale.zoom_about("top", W, H, 300.0, 200.0, 0.5)

    assert len(told) == 1 + 2, "the pan, and two zooms before the limit"
