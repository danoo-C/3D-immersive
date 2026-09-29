"""The benchmark (M4 phase 10, D-136): its arithmetic, its arrangement, and
the suite's short form of N-1.

The short form plays 32 moving sources through `test_spatial`'s synthetic
head, not SADIE. The head costs what SADIE costs a block - the same `nfft`
of 1024, and the same time within noise - and prepares in a fraction of a
second, where SADIE takes 6.4 s from a cold cache, which every test's is.
It is marked `timing`, so a parallel run leaves it to `pytest -m timing`
(conftest.py says why).
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from immersive import benchmark
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.benchmark import Arrangement, Timings, budget
from test_spatial import head

BLOCK = 512

#: The short form's line (phase 10): loose enough for a loaded machine,
#: tight enough to catch a regression of kind rather than degree.
SHORT_FORM = 0.6


@pytest.fixture(scope="module")
def bank() -> Iterator[Bank]:
    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    with tempfile.TemporaryDirectory() as cache:
        made = prepare(head(), BLOCK, Path(cache))
    patch.undo()
    assert isinstance(made, Bank)
    assert made.nfft == 1024, "SADIE's at 512 frames, so it costs what SADIE does"
    yield made


# -------------------------------------------------------------- N-1, short


@pytest.mark.timing
def test_32_moving_sources_take_under_60_percent_of_the_budget(bank: Bank) -> None:
    timings = benchmark.blocks(bank, 32, False, 500)

    assert len(timings.times) == 500, "the warm-up is not timed"
    assert timings.within(SHORT_FORM), (
        f"32 sources took a p99 of {timings.p99 * 1000:.2f} ms, "
        f"{timings.p99 / timings.budget:.0%} of a {BLOCK}-frame block"
    )


# ------------------------------------------------------------ arithmetic


def test_a_budget_is_a_block_at_48_khz() -> None:
    assert budget(512) == pytest.approx(0.010_666_67, abs=1e-8)
    assert budget(1024) == pytest.approx(2 * budget(512))


def test_timings_read_known_times() -> None:
    """1 to 100 ms, against a 50 ms budget: the one at 50 ms is on time."""
    timings = Timings(np.arange(1, 101) / 1000.0, 0.050)

    assert timings.p50 == pytest.approx(0.0505)
    assert timings.p99 == pytest.approx(0.09901)
    assert timings.worst == pytest.approx(0.100)
    assert timings.over == 50


def test_the_check_is_at_the_fraction_asked() -> None:
    limit = budget(512)
    under = Timings(np.full(200, 0.599 * limit), limit)
    over = Timings(np.full(200, 0.601 * limit), limit)

    assert under.within(SHORT_FORM) and not over.within(SHORT_FORM)
    assert under.within(1.0) and over.within(1.0)


# ------------------------------------------------------------ arrangement


def test_a_pair_is_two_sources_and_the_bypassed_channel_none(bank: Bank) -> None:
    points = Arrangement(bank, 32, False)
    pairs = Arrangement(bank, 32, True)

    assert points.sources == 32
    assert pairs.sources == 64
    for each in (points, pairs):
        *placed, bypassed = each.project.channels
        assert len(placed) == 32
        assert bypassed.hrtf_bypass and not any(c.hrtf_bypass for c in placed)
        assert bypassed.clips, "it plays"


def test_the_graph_is_finished(bank: Bank) -> None:
    """Level as mixed and the limiter on, the master at unity: what a new
    project has."""
    project = Arrangement(bank, 8, False).project

    assert project.distance.keep_level
    assert project.master.limiter_on
    assert project.master.gain_db == 0.0


def test_every_source_moves_every_block(bank: Bank) -> None:
    playing = Arrangement(bank, 16, True)
    positions = playing.snapshot.positions
    playing.play(1)
    before = positions.copy()
    playing.play(1)

    moved = np.linalg.norm(positions[:16] - before[:16], axis=2)
    assert (moved > 0).all(), "both sides of every pair, every block"
    np.testing.assert_allclose(positions[:16, 1, 0], -positions[:16, 0, 0])


def test_one_source_in_eight_orbits_inside_the_centre(bank: Bank) -> None:
    playing = Arrangement(bank, 32, False)
    playing.play(3)

    reach = np.linalg.norm(playing.snapshot.positions[:32, 0], axis=1)
    inside = reach < playing.project.distance.min_distance
    assert inside.tolist() == [n % 8 == 0 for n in range(32)]
    assert np.ptp(playing.snapshot.positions[:32, 0, 2]) > 0, "at their own heights"
