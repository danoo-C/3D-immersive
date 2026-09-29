"""`app.run`: what a real launch does before the window, which no other test
reaches (M4 phase 10). Everything it calls is replaced, so nothing opens,
prepares or makes a directory; what is left is the order it does things in.
Marked gui: `app` imports the window's modules, though nothing here builds
one."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from immersive import app
from immersive.audio.device import Output, Settled

pytestmark = pytest.mark.gui


class Recorded:
    """What `run` did, in order, and the switch interval at each step."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, float]] = []

    def step(self, name: str) -> None:
        self.steps.append((name, sys.getswitchinterval()))


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> Recorded:
    record = Recorded()
    interval = [sys.getswitchinterval()]

    def set_interval(value: float) -> None:
        record.step("switch interval")
        interval[0] = value

    class Application:
        def exec(self) -> int:
            record.step("exec")
            return 0

    class Player:
        def __init__(self, backend: Any, output: Output) -> None:
            record.step("player")

    class Window:
        def __init__(self, player: Any, unavailable: str) -> None:
            record.step("window")

        def notices(self) -> Any:
            raise AssertionError("nothing was said")

        def show(self) -> None:
            pass

        def prepare_hrtf(self) -> None:
            pass

        def stop_work(self) -> None:
            pass

    def backend() -> object:
        record.step("backend")
        return object()

    # The interval is read back through the recorder, not the interpreter's:
    # the test process keeps CPython's default.
    monkeypatch.setattr(sys, "setswitchinterval", set_interval)
    monkeypatch.setattr(sys, "getswitchinterval", lambda: interval[0])
    monkeypatch.setattr(app, "build_application", lambda argv: Application())
    monkeypatch.setattr(app.theme_menu, "user_theme_directory", lambda: None)
    monkeypatch.setattr(app, "load_backend", backend)
    monkeypatch.setattr(
        app, "settle", lambda b, d, k: Settled(Output(None, 512), True, [])
    )
    monkeypatch.setattr(app, "Player", Player)
    monkeypatch.setattr(app, "MainWindow", Window)
    return record


def test_the_switch_interval_is_1_ms_before_the_output_is_looked_for(
    recorded: Recorded,
) -> None:
    assert app.run([]) == 0

    names = [name for name, _ in recorded.steps]
    assert names == ["switch interval", "backend", "player", "window", "exec"]
    assert app.SWITCH_INTERVAL == 0.001
    for name, interval in recorded.steps[1:]:
        assert interval == 0.001, f"{name} ran at {interval}"


def test_building_the_application_leaves_the_interval_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every test builds it; only a launch sets the interval. Asked of the
    calls, not the value, which an earlier test could have left at 1 ms."""
    calls: list[float] = []
    monkeypatch.setattr(sys, "setswitchinterval", calls.append)
    app.build_application([])

    assert calls == []
