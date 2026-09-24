"""The waveform widget, asserted on what it actually draws. Marked gui.

Every picture here is a real offscreen grab, not a record of calls made to a
painter: a painter that was asked for the right line and drew nothing would
pass the second kind of test.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import numpy.typing as npt
import pytest
from PySide6.QtGui import QImage

from immersive.app import build_application
from immersive.core.io.peaks import BUCKET, RATIO, Level, Pyramid, build
from immersive.ui import theme, theme_io
from immersive.ui.widgets.waveform import Waveform, level_for

pytestmark = pytest.mark.gui

WIDTH, HEIGHT = 200, 41  # odd, so a lane has a middle row

#: Multipliers and offsets that give every token a colour unlike any other.
SPREAD = ((37, 11), (53, 7), (71, 3))


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    before = theme.active()
    yield
    theme.use(before)


def colour(group_key: str) -> str:
    return theme.group_color("waveform", group_key).upper()


def drawn(
    pyramid: Pyramid | None, *, missing: bool = False, width: int = WIDTH
) -> QImage:
    widget = Waveform()
    widget.resize(width, HEIGHT)
    widget.set_peaks(pyramid, missing=missing)
    image = widget.grab().toImage()
    widget.deleteLater()
    return image


def row_colours(image: QImage, y: int) -> set[str]:
    return {image.pixelColor(x, y).name().upper() for x in range(image.width())}


def rows_inked(image: QImage) -> set[int]:
    """Rows holding anything other than the background."""
    ground = colour("background")
    return {y for y in range(image.height()) if row_colours(image, y) != {ground}}


def sine(
    frames: int, channels: int = 1, amplitude: float = 1.0
) -> npt.NDArray[np.float32]:
    t = np.arange(frames) / 48_000
    wave = amplitude * np.sin(2 * np.pi * 440 * t)
    return np.repeat(wave[:, None], channels, axis=1).astype(np.float32)


# --------------------------------------------------------------------------- #
# what it draws
# --------------------------------------------------------------------------- #


def test_a_full_scale_sine_inks_its_lane_top_to_bottom() -> None:
    image = drawn(build(sine(48_000)))

    assert colour("fill") in row_colours(image, 0)
    assert colour("fill") in row_colours(image, HEIGHT - 1)


def test_silence_inks_only_the_centre_row() -> None:
    image = drawn(build(np.zeros((48_000, 1), dtype=np.float32)))

    assert rows_inked(image) == {HEIGHT // 2}


def test_the_zero_line_is_drawn_where_the_sound_never_crosses_it() -> None:
    """The centre line is the reference, not a side effect of silence.

    Found by the sweep: silence inks its centre row with or without the line,
    because a stroke of no length is still a point. A sample offset from
    zero never reaches the centre, and without the line nothing shows where
    zero is.
    """
    image = drawn(build(np.full((48_000, 1), 0.5, dtype=np.float32)))

    assert colour("centre") in row_colours(image, HEIGHT // 2)


def test_stereo_draws_a_lane_per_channel() -> None:
    audio = np.zeros((48_000, 2), dtype=np.float32)
    audio[:, 0] = sine(48_000)[:, 0]

    image = drawn(build(audio))

    inked = rows_inked(image)
    top_lane, bottom_lane = set(range(HEIGHT // 2)), set(range(HEIGHT // 2, HEIGHT))
    assert 0 in inked, "the left channel fills its lane"
    assert len(inked & bottom_lane) == 1, "the silent right channel is one centre row"
    assert len(inked & top_lane) > HEIGHT // 3


@pytest.mark.parametrize("pushing", ["down", "up"])
def test_an_over_stays_in_its_own_lane(pushing: str) -> None:
    """A float sample beyond full scale is drawn to its lane's edge and no
    further - it must not paint into the other channel's lane."""
    audio = np.zeros((48_000, 2), dtype=np.float32)
    if pushing == "down":
        audio[:, 0] = -2.0  # the left lane, toward the right one below it
    else:
        audio[:, 1] = 2.0  # the right lane, toward the left one above it

    image = drawn(build(audio))

    boundary = round(HEIGHT / 2)  # the first row of the right lane
    fill = colour("fill")
    if pushing == "down":
        assert fill in row_colours(image, boundary - 1), "reaches its floor"
        others = range(boundary, boundary + (HEIGHT - boundary) // 2)
    else:
        assert fill in row_colours(image, boundary), "reaches its ceiling"
        others = range(boundary // 2 + 1, boundary)
    for y in others:
        assert fill not in row_colours(image, y), f"row {y} is the other lane's"


def test_a_missing_sample_says_so_in_warn_and_in_words() -> None:
    """04: missing media is never shown by colour alone."""
    image = drawn(None, missing=True)

    warn = colour("missing")
    rows_with_warn = {y for y in range(HEIGHT) if warn in row_colours(image, y)}
    assert rows_with_warn, "drawn in warn"
    assert rows_with_warn - {HEIGHT // 2}, "and in text, not only a line"


def test_missing_silence_and_nothing_all_look_different() -> None:
    silence = drawn(build(np.zeros((48_000, 1), dtype=np.float32)))
    missing = drawn(None, missing=True)
    nothing = drawn(None)

    assert silence != missing
    assert nothing != silence, "a sample not loaded is not a quiet one"
    assert rows_inked(nothing) == set()


def test_a_theme_switch_changes_the_pixels() -> None:
    """Under a theme where every token differs, no old colour survives."""
    pyramid = build(sine(48_000))
    before = {
        image.pixelColor(x, y).name().upper()
        for image in [drawn(pyramid)]
        for x in range(WIDTH)
        for y in range(HEIGHT)
    }
    builtin = theme_io.builtin()
    loud = replace(
        builtin,
        tokens={
            name: "#" + "".join(f"{(n * k + c) % 256:02X}" for k, c in SPREAD)
            for n, name in enumerate(sorted(builtin.tokens))
        },
    )
    assert not set(loud.tokens.values()) & set(builtin.tokens.values())
    theme.use(loud)

    after_image = drawn(pyramid)
    after = {
        after_image.pixelColor(x, y).name().upper()
        for x in range(WIDTH)
        for y in range(HEIGHT)
    }

    assert not before & after


# --------------------------------------------------------------------------- #
# how much it reads
# --------------------------------------------------------------------------- #


def shaped(frames: int) -> Pyramid:
    """A pyramid of the right shape and no audio, so hours cost megabytes."""
    levels = []
    bucket = BUCKET
    while True:
        buckets = math.ceil(frames / bucket)
        zeros = np.zeros((buckets, 1), dtype=np.float32)
        levels.append(Level(bucket, zeros, zeros))
        if buckets == 1:
            break
        bucket *= RATIO
    return Pyramid(frames, 1, tuple(levels))


@pytest.mark.parametrize(
    "frames", [256, 257, 1_000, 48_000 * 60, 48_000 * 60 * 60 * 2 + 17]
)
@pytest.mark.parametrize("width", [1, 2, 7, 120, 1_000, 4_000])
def test_a_paint_reads_between_one_and_four_buckets_a_column(
    frames: int, width: int
) -> None:
    """Bounded by the widget's width, never by the sample's length - counted
    at every point of the sweep rather than at one."""
    pyramid = shaped(frames)

    level = level_for(pyramid, width)

    if pyramid.levels[0].bucket <= frames / width:
        assert width <= level.buckets <= RATIO * width
    else:
        assert level is pyramid.levels[0], "a short sample in a wide widget"
