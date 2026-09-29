"""The benchmark's window (M4 phase 10, D-137): the application's window
playing through the stand-in stream, under each load, at each switch
interval. Short runs, through the synthetic head: these test the plumbing,
not the effect, which is measured by hand with
`python -m immersive.benchmark contention`. Marked gui.
"""

from __future__ import annotations

import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from immersive import benchmark
from immersive.app import build_application
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.benchmark import INTERVALS, LOADS, Arrangement
from immersive.ui import hrtf
from test_spatial import head

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _head(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The window prepares the synthetic head, its index at test size."""
    build_application([])
    monkeypatch.setattr(lookup, "CELLS", 16)
    monkeypatch.setattr(lookup, "SAMPLES", 2)
    monkeypatch.setattr(hrtf, "builtin", lambda set_id: head())
    yield


def test_each_load_runs_at_each_interval_in_turn_and_the_interval_is_put_back() -> None:
    """Two rounds: each load at 5 ms then 1 ms, then at 1 ms then 5 ms. The
    interval is the one the audio thread read, not the one asked for."""
    sys.setswitchinterval(0.004)
    try:
        laps = benchmark.contention(0.25, 2, channels=8)
        after = sys.getswitchinterval()
    finally:
        sys.setswitchinterval(0.005)

    assert after == 0.004
    assert [(lap.load, lap.interval) for lap in laps] == [
        (load, interval)
        for turn in range(2)
        for load in LOADS
        for interval in INTERVALS[:: -1 if turn % 2 else 1]
    ]
    assert all(lap.timings.times.size > 0 for lap in laps), "every lap played"
    assert all(0 <= lap.missed <= lap.timings.times.size for lap in laps)


def test_the_ui_thread_moves_every_source() -> None:
    with tempfile.TemporaryDirectory() as cache:
        bank = prepare(head(), 512, Path(cache))
    assert isinstance(bank, Bank)
    playing = Arrangement(bank, 4, False)
    engine = playing.engine
    before = playing.snapshot.positions[:4].copy()

    timer = benchmark._moving(engine, 4)
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    timer.stop()
    engine.process(np.zeros((512, 2), dtype=np.float32))

    moved = np.linalg.norm(playing.snapshot.positions[:4, 0] - before[:, 0], axis=1)
    assert (moved > 0).all()
