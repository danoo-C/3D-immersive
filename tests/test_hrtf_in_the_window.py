"""Preparing the HRTF set in the application (D-116, D-120). Marked gui.

A small synthetic set stands in for SADIE II D1, whose cold preparation
takes 6 s, and it waits at a gate so a test can look while it runs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.audio.device import Output
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank
from immersive.audio.player import Player
from immersive.core.io.media import Refused
from immersive.ui import hrtf
from immersive.ui.main_window import MainWindow, Unsaved
from immersive.ui.notices import Severity
from standin import Backend
from test_bank import synthetic

pytestmark = pytest.mark.gui

GATE_TIMEOUT = 10.0


@pytest.fixture(autouse=True)
def _application(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    build_application([])
    monkeypatch.setattr(lookup, "CELLS", 16)  # the index at test size
    monkeypatch.setattr(lookup, "SAMPLES", 2)
    yield


@pytest.fixture
def window() -> Iterator[MainWindow]:
    made = MainWindow(player=Player(Backend(), Output(None, 256)))
    made._ask_about_unsaved = lambda: Unsaved.DISCARD  # type: ignore[method-assign]
    yield made
    made.stop_work()
    assert made._hrtf._pool.waitForDone(int(GATE_TIMEOUT * 1000))
    made.deleteLater()


def standing_in(
    monkeypatch: pytest.MonkeyPatch, gate: threading.Event | None = None
) -> list[str]:
    """The synthetic set in SADIE's place, held at `gate` if given."""
    asked: list[str] = []

    def builtin(set_id: str) -> Any:
        asked.append(set_id)
        if gate is not None:
            gate.wait(GATE_TIMEOUT)
        return synthetic()

    monkeypatch.setattr(hrtf, "builtin", builtin)
    return asked


def until(condition: Any, timeout: float = GATE_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        assert time.monotonic() < deadline, "never happened"


def test_a_window_built_directly_prepares_nothing(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dozens of tests build windows with players; none may start SADIE."""
    asked = standing_in(monkeypatch)
    QApplication.processEvents()
    assert asked == [] and not window._hrtf.busy and window.bank() is None
    assert window.activities().running() == []


def test_preparing_shows_as_an_activity_and_lands_as_a_bank(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    asked = standing_in(monkeypatch, gate)

    assert window.prepare_hrtf()

    [work] = window.activities().running()
    assert work.label == "Preparing the HRTF set" and work.cancel is None
    gate.set()
    until(lambda: window.bank() is not None)
    bank = window.bank()
    assert isinstance(bank, Bank) and bank.block == 256
    assert asked == ["sadie-d1"], "the set the project names"
    assert window.activities().running() == []


def test_the_same_set_is_not_prepared_twice(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = standing_in(monkeypatch)
    window.prepare_hrtf()
    until(lambda: window.bank() is not None)
    assert not window.prepare_hrtf()
    assert asked == ["sadie-d1"]


def test_a_set_not_fetched_is_one_warning_naming_the_fetch(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = Refused(
        "SADIE II D1", "is not installed - `python3 launch.py --install` fetches it"
    )
    monkeypatch.setattr(hrtf, "builtin", lambda set_id: missing)

    window.prepare_hrtf()
    until(lambda: bool(window.notices().newest_first()))

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert "launch.py --install" in notice.message
    assert window.bank() is None and window.activities().running() == []


def test_a_close_stops_it(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    standing_in(monkeypatch, gate)
    window.prepare_hrtf()
    running = window._hrtf._progress
    assert running is not None

    window.close()

    assert running.cancelled and not window._hrtf.busy
    assert window.activities().running() == []
    gate.set()
    assert window._hrtf._pool.waitForDone(int(GATE_TIMEOUT * 1000))
    QApplication.processEvents()
    assert window.bank() is None, "nothing handed over after the close"


def test_without_an_output_nothing_is_prepared(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = standing_in(monkeypatch)
    bare = MainWindow()
    assert not bare.prepare_hrtf()
    assert asked == []
    bare.deleteLater()


def test_opening_a_project_that_names_another_set_prepares_that(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    asked = standing_in(monkeypatch)
    window.document().project.hrtf.id = "another"
    window.document().save_as(tmp_path / "other.3dim")
    window.new_project()
    window.prepare_hrtf()
    until(lambda: window.bank() is not None)

    window.open_project(tmp_path / "other.3dim")
    until(lambda: len(asked) == 2 and not window._hrtf.busy)

    assert asked == ["sadie-d1", "another"]


def test_an_open_before_anything_asked_prepares_nothing(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    asked = standing_in(monkeypatch)
    window.document().save_as(tmp_path / "plain.3dim")
    window.open_project(tmp_path / "plain.3dim")
    QApplication.processEvents()
    assert asked == []


def test_a_request_replaced_is_never_handed_over_late(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first asks, is held, and then refuses - a result no cancel can
    stop. It arrives after the second has landed, and must be ignored."""
    gate = threading.Event()
    calls: list[str] = []

    def builtin(set_id: str) -> Any:
        calls.append(set_id)
        if len(calls) == 1:
            gate.wait(GATE_TIMEOUT)
            return Refused("the first set", "arrived too late to matter")
        return synthetic()

    monkeypatch.setattr(hrtf, "builtin", builtin)
    # Two at once, so the second runs while the first is held.
    window._hrtf._pool.setMaxThreadCount(2)
    window.prepare_hrtf()
    window._hrtf_wanted = None  # ask again, as an open of another set would
    window.prepare_hrtf()
    until(lambda: window.bank() is not None)

    gate.set()
    assert window._hrtf._pool.waitForDone(int(GATE_TIMEOUT * 1000))
    QApplication.processEvents()
    assert window.notices().newest_first() == [], "the first's refusal, ignored"
