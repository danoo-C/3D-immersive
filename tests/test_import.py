"""Importing on workers: one edit per import, and a window that keeps turning.

Marked gui. Every test waits for its import to finish before it ends, so no
worker outlives the window it reports to.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QCoreApplication, QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.io.media import Refused
from immersive.core.media_store import Prepared
from immersive.core.time import SAMPLE_RATE
from immersive.ui import importer, main_window
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity

pytestmark = pytest.mark.gui

#: How long a gated worker waits before going on regardless. Never reached
#: when the code is right, because each test opens its gate as soon as it has
#: seen what it came for; it bounds how long a broken build takes to fail.
GATE_TIMEOUT = 10.0


@pytest.fixture
def window() -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow()
    yield made
    finish(made)
    made.deleteLater()


def finish(window: MainWindow, timeout: float = 20.0) -> None:
    """Turn the event loop until the import is in, or fail saying so."""
    deadline = time.monotonic() + timeout
    while window.importing():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError("the import did not finish")
    QApplication.processEvents()


def sample(path: Path, seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.5, 0.5, SAMPLE_RATE // 4).astype(np.float32)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


def folder_of(root: Path, count: int, *, seed: int = 0) -> Path:
    for n in range(count):
        sample(root / f"{n:02}.wav", seed + n)
    return root


def counting_prepare(
    monkeypatch: pytest.MonkeyPatch, gate: threading.Event | None = None
) -> list[Path]:
    """Replace the workers' `prepare` with one that counts, and optionally
    holds every file at `gate` until the test opens it.

    A gate rather than a sleep: the import runs for exactly as long as the
    test needs it to, which a sleep can only guess at and a loaded machine
    can outlast. Waiting releases the GIL, as decoding does."""
    calls: list[Path] = []
    real: Callable[[Path], Prepared | Refused] = importer.prepare

    def prepare(path: Path) -> Prepared | Refused:
        calls.append(path)
        if gate is not None:
            gate.wait(GATE_TIMEOUT)
        return real(path)

    monkeypatch.setattr(importer, "prepare", prepare)
    return calls


def pool_names(window: MainWindow) -> list[str]:
    return [media.name for media in window.document().project.media_pool]


# --------------------------------------------------------------------------- #
# one import, one edit
# --------------------------------------------------------------------------- #


def test_a_folder_is_one_undoable_edit(window: MainWindow, tmp_path: Path) -> None:
    folder = folder_of(tmp_path / "kit", 4)

    assert window.import_paths(sorted(folder.glob("*.wav")))
    finish(window)

    assert pool_names(window) == ["00.wav", "01.wav", "02.wav", "03.wav"]
    assert window.document().undo()
    assert pool_names(window) == []
    assert not window.document().can_undo, "one edit, not four"


def test_redo_decodes_nothing(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store keeps the audio across Undo, so Redo puts back what is
    already decoded."""
    calls = counting_prepare(monkeypatch)
    window.import_paths(sorted(folder_of(tmp_path / "kit", 3).glob("*.wav")))
    finish(window)
    window.document().undo()

    assert window.document().redo()

    assert len(calls) == 3
    for media in window.document().project.media_pool:
        assert window.store().audio(media.id) is not None


def test_the_window_keeps_turning_while_an_import_runs(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N-3, asserted as a timer that goes on firing on the UI thread while an
    import is held open, not as an import that merely finishes. Preparing on
    the UI thread would wait at the gate itself, and the timer with it."""
    gate = threading.Event()
    counting_prepare(monkeypatch, gate)
    ticks: list[float] = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(10)

    window.import_paths(sorted(folder_of(tmp_path / "kit", 4).glob("*.wav")))
    deadline = time.monotonic() + GATE_TIMEOUT / 2
    while len(ticks) < 5 and window.importing() and time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    held_open, seen = window.importing(), len(ticks)
    gate.set()
    finish(window)
    timer.stop()

    assert held_open, "the import was over before the window had turned"
    assert seen >= 5, ticks
    assert len(pool_names(window)) == 4


def test_the_model_is_edited_on_the_ui_thread(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """02's threading table: workers never touch the model."""
    threads: list[bool] = []
    real = main_window.admit

    def admit(*args: object) -> object:
        instance = QCoreApplication.instance()
        assert instance is not None
        threads.append(QThread.currentThread() is instance.thread())
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(main_window, "admit", admit)

    window.import_paths([sample(tmp_path / "a.wav", 1)])
    finish(window)

    assert threads == [True]


# --------------------------------------------------------------------------- #
# what does not come in
# --------------------------------------------------------------------------- #


def test_files_that_will_not_decode_are_one_notice(
    window: MainWindow, tmp_path: Path
) -> None:
    good = folder_of(tmp_path / "kit", 2)
    for name in ("broken.wav", "empty.wav"):
        (good / name).write_bytes(b"" if name == "empty.wav" else b"not audio")

    window.import_paths(sorted(good.glob("*.wav")))
    finish(window)

    assert pool_names(window) == ["00.wav", "01.wav"]
    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert notice.message == "Imported 2 of 4 files"
    assert [line.split(":")[0] for line in notice.detail] == ["broken.wav", "empty.wav"]


def test_audio_already_in_the_pool_is_counted_not_added(
    window: MainWindow, tmp_path: Path
) -> None:
    folder = folder_of(tmp_path / "kit", 2)
    window.import_paths(sorted(folder.glob("*.wav")))
    finish(window)

    window.import_paths(sorted(folder.glob("*.wav")))
    finish(window)

    assert pool_names(window) == ["00.wav", "01.wav"]
    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.INFO, "nothing went wrong"
    assert list(notice.detail) == [
        "00.wav: already in the pool",
        "01.wav: already in the pool",
    ]


def test_a_whole_import_that_worked_is_quiet(
    window: MainWindow, tmp_path: Path
) -> None:
    window.import_paths(sorted(folder_of(tmp_path / "kit", 2).glob("*.wav")))
    finish(window)

    assert window.notices().newest_first() == []


def test_a_folder_with_nothing_to_import_says_so(
    window: MainWindow, tmp_path: Path
) -> None:
    empty = tmp_path / "notes"
    empty.mkdir()
    (empty / "readme.txt").write_text("hello", encoding="utf-8")
    window._choose_folder = lambda: empty  # type: ignore[method-assign]

    assert not window.import_folder()

    [notice] = window.notices().newest_first()
    assert notice.message == "No audio found in notes"


def test_import_folder_finds_what_is_beneath(
    window: MainWindow, tmp_path: Path
) -> None:
    folder = folder_of(tmp_path / "kit", 1)
    sample(folder / "deeper" / "snare.wav", 9)
    window._choose_folder = lambda: folder  # type: ignore[method-assign]

    assert window.import_folder()
    finish(window)

    assert pool_names(window) == ["00.wav", "snare.wav"]


def test_import_files_uses_the_dialog_and_a_cancel_imports_nothing(
    window: MainWindow, tmp_path: Path
) -> None:
    window._choose_audio_files = lambda: []  # type: ignore[method-assign]
    assert not window.import_files()

    chosen = [sample(tmp_path / "one.wav", 3)]
    window._choose_audio_files = lambda: chosen  # type: ignore[method-assign]
    assert window.import_files()
    finish(window)
    assert pool_names(window) == ["one.wav"]


def test_one_import_at_a_time(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    counting_prepare(monkeypatch, gate)
    window.import_paths([sample(tmp_path / "a.wav", 4)])

    second = window.import_paths([sample(tmp_path / "b.wav", 5)])
    gate.set()
    finish(window)

    assert not second
    assert pool_names(window) == ["a.wav"]


def test_an_import_does_not_land_in_a_project_opened_meanwhile(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    counting_prepare(monkeypatch, gate)
    window.import_paths([sample(tmp_path / "a.wav", 6)])

    window.new_project()  # nothing unsaved, so nothing is asked
    gate.set()
    finish(window)

    assert pool_names(window) == []
    [notice] = window.notices().newest_first()
    assert notice.message.startswith("Import set aside")
