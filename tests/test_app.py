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
        self.windows: list[Any] = []

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
            self.settle: Any = None
            windows.append(self)

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

    def settle_memory() -> None:
        record.step("settle")

    windows: list[Any] = []
    record.windows = windows

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
    monkeypatch.setattr(app, "settle_memory", settle_memory)
    return record


def test_the_switch_interval_is_1_ms_before_the_output_is_looked_for(
    recorded: Recorded,
) -> None:
    assert app.run([]) == 0

    names = [name for name, _ in recorded.steps]
    assert names == ["switch interval", "backend", "player", "window", "settle", "exec"]
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


def test_a_launch_settles_memory_once_the_window_is_up_and_after_each_load(
    recorded: Recorded,
) -> None:
    """D-142: the window is given the launch's `settle_memory`, which it
    calls after New and Open, and the launch calls it once the window is
    shown."""
    app.run([])

    [window] = recorded.windows
    assert window.settle is app.settle_memory
    assert [name for name, _ in recorded.steps].count("settle") == 1


def test_settling_memory_collects_then_freezes() -> None:
    """What was frozen by one load and has since become garbage in a cycle
    - a project replaced - is freed by the next, which unfreezes before it
    collects; and what is left is frozen, so a later collection passes it
    by. Unfrozen after, for the tests that follow in this process."""
    import gc
    import weakref

    class Node:
        other: object = None

    first, second = Node(), Node()
    first.other, second.other = second, first
    gone = weakref.ref(first)
    try:
        app.settle_memory()  # alive, so frozen
        assert gone() is not None and gc.get_freeze_count() > 0
        del first, second  # now garbage, in a cycle, and frozen
        gc.collect()
        assert gone() is not None, "a frozen cycle outlives a collection"
        app.settle_memory()
        assert gone() is None, "the next load's settle freed it"
        assert gc.get_freeze_count() > 0
    finally:
        gc.unfreeze()
