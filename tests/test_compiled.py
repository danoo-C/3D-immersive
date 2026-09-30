"""How the audio thread's work is compiled (M4 phase 11, D-138, D-139):
without the GIL, with no array made, and never from a stale cache."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from numba.core.errors import NumbaError

from immersive.audio.compiled import STAMP, fresh_cache, kernel


@kernel
def _spin(out: npt.NDArray[np.float64], turns: int) -> None:
    total = 0.0
    for turn in range(turns):
        total += np.sqrt(turn + out[0])
    out[1] = total


@kernel
def _makes_an_array(size: int) -> float:
    return float(np.zeros(size).sum())


def test_a_kernel_runs_without_the_gil() -> None:
    """A Python thread counts while a kernel spins for a quarter of a
    second, and keeps at least a third of the pace it keeps alone. Holding
    the GIL, the kernel would leave it only the switch interval's slices
    just before and after, a few milliseconds' worth: the sweep found a
    bare "it counted" passed that way.

    Three tries, and one is enough. A kernel holding the GIL starves the
    counter every time, but the full suite's other workers can starve it
    for one try, which failed it once at M5 phase 2."""
    out = np.zeros(2)
    _spin(out, 1_000_000)  # compiled, or loaded, first
    began = time.perf_counter()
    _spin(out, 1_000_000)
    turns = max(int(1_000_000 * 0.25 / (time.perf_counter() - began)), 1_000_000)
    tries = [_counted_during(out, turns) for _ in range(3)]
    assert all(took > 0.1 for _, _, took in tries), (
        "long enough that the slices around it do not count"
    )
    assert any(during > pace * took / 3 for during, pace, took in tries), [
        f"{during} counts in {took * 1000:.0f} ms, at {pace:.0f} a second alone"
        for during, pace, took in tries
    ]


def _counted_during(
    out: npt.NDArray[np.float64], turns: int
) -> tuple[int, float, float]:
    """How far a Python thread counts while `_spin` runs `turns`, its pace
    alone just before, and how long the spin took."""
    counted = [0]
    stop = threading.Event()

    def count() -> None:
        while not stop.is_set():
            counted[0] += 1

    counter = threading.Thread(target=count)
    counter.start()
    try:
        time.sleep(0.02)
        before, began = counted[0], time.perf_counter()
        time.sleep(0.1)  # alone: the GIL is free while this thread sleeps
        pace = (counted[0] - before) / (time.perf_counter() - began)
        before, began = counted[0], time.perf_counter()
        _spin(out, turns)
        took = time.perf_counter() - began
        during = counted[0] - before
    finally:
        stop.set()
        counter.join()
    return during, pace, took


def test_a_kernel_cannot_make_an_array() -> None:
    """No runtime, so no array (D-106): it fails to compile, not to play."""
    with pytest.raises(NumbaError):
        _makes_an_array(4)


def package(root: Path) -> Path:
    (root / "hrtf").mkdir(parents=True)
    (root / "spatial.py").write_text("x = 1\n")
    (root / "hrtf" / "lookup.py").write_text("y = 1\n")
    return root


def cached(root: Path) -> list[Path]:
    """Two compiled kernels, as numba leaves them beside their modules."""
    made = []
    for where in (root / "__pycache__", root / "hrtf" / "__pycache__"):
        where.mkdir(exist_ok=True)
        for suffix in (".nbi", ".nbc"):
            path = where / f"kernel{suffix}"
            path.write_bytes(b"compiled")
            made.append(path)
    return made


def test_the_cache_is_cleared_when_any_module_changes(tmp_path: Path) -> None:
    """Including a module in a subpackage, which is where the lookup's walk
    lives: the spatial kernel calls it, and numba would not have noticed."""
    root = package(tmp_path / "audio")
    first = cached(root)
    assert fresh_cache(root), "never seen: cleared"
    assert not any(path.exists() for path in first)
    assert (root / "__pycache__" / STAMP).exists()

    second = cached(root)
    assert not fresh_cache(root), "unchanged: kept"
    assert all(path.exists() for path in second)

    (root / "hrtf" / "lookup.py").write_text("y = 2\n")
    assert fresh_cache(root), "a called module changed: cleared"
    assert not any(path.exists() for path in second)


def test_a_cache_that_cannot_be_cleared_is_left_to_numba(tmp_path: Path) -> None:
    """A directory that cannot be written is not an error at import."""
    root = package(tmp_path / "audio")
    (root / "__pycache__").write_text("not a directory")

    assert fresh_cache(root)
