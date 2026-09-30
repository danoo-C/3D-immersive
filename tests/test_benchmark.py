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

import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from immersive import benchmark
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.benchmark import Arrangement, Backend, Clock, Timings, budget
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

    assert timings.within(SHORT_FORM), (
        f"32 sources took a p99 of {timings.p99 * 1000:.2f} ms, "
        f"{timings.p99 / timings.budget:.0%} of a {BLOCK}-frame block"
    )


def test_only_the_blocks_asked_for_are_timed(bank: Bank) -> None:
    """Not the warm-up. Apart from the short form, because a parallel run
    skips that, and a sweep is a parallel run: this check survived the
    phase's sweep while it lived there."""
    timings = benchmark.blocks(bank, 1, False, 20)

    assert len(timings.times) == 20
    assert timings.budget == budget(BLOCK)


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


# ------------------------------------------------------ the stand-in stream


def test_a_block_done_within_its_block_is_not_missed() -> None:
    clock = Clock(0.010, 100.0)

    assert not clock.done(100.000, 100.009)
    assert clock.due() == pytest.approx(100.010)
    assert clock.missed == 0
    assert clock.times == [pytest.approx(0.009)]


def test_a_block_that_starts_late_is_missed_by_when_it_was_due() -> None:
    """It took 5 ms, but began 8 ms late: the device wanted it at 10."""
    clock = Clock(0.010, 100.0)

    assert clock.done(100.008, 100.013)
    assert clock.missed == 1
    assert clock.woken == [pytest.approx(0.008)]
    assert clock.times == [pytest.approx(0.013)]


def test_one_long_block_is_one_miss() -> None:
    """3.5 blocks long, then five quick ones: the clock is set again from
    when the long one finished, as a device plays on after an underrun."""
    clock = Clock(0.010, 100.0)
    clock.done(100.0, 100.035)

    assert clock.due() == pytest.approx(100.035)
    for _ in range(5):
        began = clock.due()
        clock.done(began, began + 0.002)
    assert clock.missed == 1
    assert clock.blocks == 6


def test_the_stand_in_stream_calls_back_a_block_at_a_time_on_its_clock() -> None:
    calls: list[tuple[Any, ...]] = []

    def callback(
        out: npt.NDArray[np.float32], frames: int, when: Any, status: Any
    ) -> None:
        calls.append((out.shape, out.dtype, frames, status))

    backend = Backend()
    stream = backend.OutputStream(
        samplerate=48_000,
        blocksize=BLOCK,
        device=None,
        channels=2,
        dtype="float32",
        callback=callback,
        finished_callback=lambda: None,
    )
    stream.start()
    time.sleep(0.2)
    stream.close()
    count = len(calls)
    time.sleep(0.05)

    assert len(calls) == count, "nothing after close"
    assert 5 <= count <= 25, "0.2 s is 19 blocks of 512 frames"
    assert set(calls) == {((BLOCK, 2), np.dtype(np.float32), BLOCK, None)}
    assert stream.clock.blocks == count
    assert stream.clock.interval == sys.getswitchinterval()
    assert backend.streams == [stream]


def test_live_says_why_there_is_no_output_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from immersive.audio import device

    monkeypatch.setattr(device, "load_backend", lambda: "PortAudio is missing")
    assert benchmark.run_live(None, None, 1.0, "playing") == 2
    assert capsys.readouterr().out == "PortAudio is missing\n"

    unusable = device.Settled(device.Output(None, 512), False, ["no device"])
    monkeypatch.setattr(device, "load_backend", lambda: object())
    monkeypatch.setattr(device, "settle", lambda backend, name, block: unusable)
    assert benchmark.run_live(None, None, 1.0, "playing") == 2
    assert capsys.readouterr().out == "no device\n"


# ------------------------------------------------------ the views (M5 phase 5)


@pytest.mark.gui
def test_the_dragging_load_drags_the_second_source_and_makes_one_edit() -> None:
    """Pressed on the second source (the first is inside the centre), moved
    while it runs - the icon, not the model - and released at the end, as
    one edit. Nothing else moves."""
    from PySide6.QtCore import QEventLoop, QTimer

    from immersive.app import build_application
    from immersive.ui.main_window import MainWindow

    build_application([])
    window = MainWindow()
    window.show()
    try:
        benchmark._arrange(window, 8, benchmark.sample(1.0))
        document = window.document()
        project = document.project
        second = project.channels[1]
        before = [channel.position for channel in project.channels]
        top, _ = window.spatial_views()

        drag = benchmark._drag(window)
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
        [icon] = [icon for icon in top.icons() if icon.channel is second]
        assert icon.centre != top.point_of(second.position), "moving"
        assert second.position == before[1], "no edit while it drags"
        assert document.selection.channels() == [second]
        drag.stop()

        assert second.position != before[1]
        assert [c.position for c in project.channels if c is not second] == [
            where for n, where in enumerate(before) if n != 1
        ]
        assert document.undo()
        assert second.position == before[1], "one edit"
    finally:
        window.stop_work()
        window.deleteLater()


@pytest.mark.gui
def test_each_view_is_timed_as_often_as_asked_and_painted_each_time() -> None:
    timed = benchmark.views(3, channels=4)

    assert list(timed) == list(benchmark.VIEWS)
    for name, painted in timed.items():
        assert len(painted.times) == 3, name
        assert painted.paints == 3, f"{name} painted {painted.paints} times"
