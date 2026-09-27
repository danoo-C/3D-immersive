"""Gains, fade tables and ramps: the arithmetic the engine multiplies by.
No device, no window."""

from __future__ import annotations

import numpy as np
import pytest

from immersive.audio.dsp import db_to_gain, fade_curve, fade_in, fade_out, ramp_steps
from immersive.core.model import FadeShape


def test_zero_decibels_is_exactly_one() -> None:
    """Bit-transparency depends on it (D-42)."""
    assert db_to_gain(0.0) == 1.0


@pytest.mark.parametrize(
    ("db", "gain"), [(-6.0, 0.5012), (6.0, 1.9953), (-60.0, 0.001)]
)
def test_decibels_are_a_factor_of_amplitude(db: float, gain: float) -> None:
    assert db_to_gain(db) == pytest.approx(gain, abs=1e-4)


@pytest.mark.parametrize("shape", list(FadeShape))
@pytest.mark.parametrize("length", [1, 2, 32, 1_000])
def test_a_fade_table_is_its_shapes_gain_sample_by_sample(
    shape: FadeShape, length: int
) -> None:
    """One definition of a shape: the table is `FadeShape.gain`, which the
    clip draws its curve from."""
    table = fade_in(shape, length)
    expected = [shape.gain(k / length) for k in range(length)]
    assert table.dtype == np.float32 and table.shape == (length,)
    assert np.allclose(table, expected, atol=1e-7)
    assert table[0] == 0.0, "a fade-in starts silent"


@pytest.mark.parametrize("shape", list(FadeShape))
def test_a_fade_out_is_the_fade_in_backwards(shape: FadeShape) -> None:
    table = fade_out(shape, 64)
    assert np.array_equal(table, fade_in(shape, 64)[::-1])
    assert table[-1] == 0.0 and table.flags.c_contiguous


def test_fade_tables_are_shared_and_cannot_be_written() -> None:
    assert fade_in(FadeShape.LINEAR, 32) is fade_in(FadeShape.LINEAR, 32)
    with pytest.raises(ValueError):
        fade_in(FadeShape.LINEAR, 32)[0] = 1.0
    with pytest.raises(ValueError):
        fade_out(FadeShape.LINEAR, 32)[0] = 1.0


def test_a_curve_is_clipped_to_its_ends() -> None:
    curve = fade_curve(FadeShape.EQUAL_POWER, np.array([-1.0, 0.5, 2.0]))
    assert curve[0] == 0.0 and curve[2] == 1.0
    assert curve[1] == pytest.approx(np.sin(np.pi / 4))


def test_a_ramp_ends_on_the_new_value_and_moves_from_the_first_sample() -> None:
    steps = ramp_steps(4)
    assert steps.tolist() == [0.25, 0.5, 0.75, 1.0]
    assert steps.dtype == np.float32
