"""Loudness as BS.1770 weights it (D-128), and what a stereo file loses
folded to a point (D-129). Headless."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import signal

from immersive.core.io.loudness import (
    CHUNK,
    FOLD_CAP,
    HIGHPASS_A,
    HIGHPASS_B,
    SHELF_A,
    SHELF_B,
    fold,
    pink_power,
    pink_weights,
    weighted_power,
    weighting,
)

SECONDS = np.arange(4 * 48_000) / 48_000


def db(value: float) -> float:
    return 10.0 * math.log10(value)


def test_a_997_hz_sine_at_full_scale_reads_minus_3_01_lkfs() -> None:
    """The standard's own check: -0.691 + 10 log10 of the weighted mean
    square, in one channel."""
    sine = np.sin(2 * np.pi * 997 * SECONDS)
    assert -0.691 + db(weighted_power(sine)) == pytest.approx(-3.01, abs=0.005)


def test_the_shelf_lifts_the_top_and_the_high_pass_takes_the_bottom() -> None:
    response = [db(v) for v in weighting(np.array([20.0, 997.0, 10_000.0]))]
    assert response[0] < -13.0
    assert response[1] == pytest.approx(0.691, abs=0.001)
    assert response[2] == pytest.approx(4.0, abs=0.1)


def test_filtering_in_chunks_is_filtering_all_at_once() -> None:
    noise = np.random.default_rng(1).standard_normal(int(2.5 * CHUNK))
    whole = signal.lfilter(
        HIGHPASS_B, HIGHPASS_A, signal.lfilter(SHELF_B, SHELF_A, noise)
    )
    assert weighted_power(noise) == pytest.approx(float(np.mean(whole**2)), rel=1e-9)


def test_a_flat_response_makes_pink_noise_as_loud_as_its_weights() -> None:
    weights = pink_weights(1024)
    flat = np.ones((2, 513), dtype=np.complex64)
    assert pink_power(flat, weights).tolist() == pytest.approx([weights.sum()] * 2)
    assert weights[0] == 0.0


# --------------------------------------------------------------------------- #
# the fold (D-129)
# --------------------------------------------------------------------------- #


def stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.column_stack([left, right]).astype(np.float32)


def test_two_unrelated_sides_lose_3_db_folded_and_get_it_back() -> None:
    rng = np.random.default_rng(2)
    audio = stereo(rng.standard_normal(10 * 48_000), rng.standard_normal(10 * 48_000))
    assert fold(audio) == pytest.approx(math.sqrt(2), rel=0.01)


def test_the_same_on_both_sides_loses_nothing() -> None:
    same = np.random.default_rng(3).standard_normal(48_000)
    assert fold(stereo(same, same)) == pytest.approx(1.0, rel=1e-9)


def test_one_side_alone_loses_3_db() -> None:
    alone = np.random.default_rng(4).standard_normal(48_000)
    assert fold(stereo(alone, np.zeros_like(alone))) == pytest.approx(math.sqrt(2))


def test_opposite_sides_are_given_back_no_more_than_6_db() -> None:
    """They cancel folded: whatever is left is not the same sound, louder."""
    side = np.random.default_rng(5).standard_normal(48_000)
    assert fold(stereo(side, -side)) == FOLD_CAP == 2.0
    nearly = stereo(side, -0.9 * side)
    assert fold(nearly) == FOLD_CAP


def test_a_mono_file_or_a_silent_one_loses_nothing() -> None:
    mono = np.random.default_rng(6).standard_normal((48_000, 1)).astype(np.float32)
    assert fold(mono) == 1.0
    assert fold(np.zeros((48_000, 2), dtype=np.float32)) == 1.0
    assert fold(np.zeros((0, 2), dtype=np.float32)) == 1.0
