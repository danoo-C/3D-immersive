"""An opened project's samples load into the session too. Marked gui.

Imports fill the store; this is what fills it for a project opened from disk,
which imports never touched - otherwise its thumbnails are blank and, from
phase 7, it plays nothing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.io.media import Refused
from immersive.core.media_store import Prepared
from immersive.core.time import SAMPLE_RATE
from immersive.ui import importer, theme
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity

pytestmark = pytest.mark.gui

#: As in test_import.py: never reached when the code is right, and a bound on
#: how long a broken build takes to fail.
GATE_TIMEOUT = 10.0


@pytest.fixture
def window() -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow()
    made.resize(1200, 800)
    yield made
    finish(made)
    made.deleteLater()


def finish(window: MainWindow, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while window.importing():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError("the workers did not finish")
    QApplication.processEvents()


def sample(path: Path, seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.8, 0.8, SAMPLE_RATE // 4).astype(np.float32)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


def saved_with_samples(window: MainWindow, tmp_path: Path, count: int = 3) -> Path:
    """Import `count` samples, save, and start a fresh project - so the next
    open starts from an empty store, as a new session would."""
    paths = [sample(tmp_path / "kit" / f"{n}.wav", n) for n in range(count)]
    window.import_paths(paths)
    finish(window)
    project = tmp_path / "song.3dim"
    window.document().save_as(project)
    window.new_project()
    return project


def counting(
    monkeypatch: pytest.MonkeyPatch, gate: threading.Event | None = None
) -> list[Path]:
    """Count what the workers prepare, and optionally hold each file at
    `gate` until the test opens it - so a load is still running for exactly
    as long as the test needs."""
    calls: list[Path] = []
    real: Callable[[Path], Prepared | Refused] = importer.prepare

    def prepare(path: Path) -> Prepared | Refused:
        calls.append(path)
        if gate is not None:
            gate.wait(GATE_TIMEOUT)
        return real(path)

    monkeypatch.setattr(importer, "prepare", prepare)
    return calls


def test_a_reopened_project_has_its_samples_again(
    window: MainWindow, tmp_path: Path
) -> None:
    project = saved_with_samples(window, tmp_path)

    assert window.open_project(project)
    finish(window)

    for media in window.document().project.media_pool:
        assert window.store().audio(media.id) is not None, media.name
        assert window.store().peaks(media.id) is not None


def test_its_thumbnails_are_drawn(window: MainWindow, tmp_path: Path) -> None:
    project = saved_with_samples(window, tmp_path)
    window.open_project(project)
    finish(window)
    window.show()
    QApplication.processEvents()

    image = window.pool().tree.viewport().grab().toImage()
    fill = theme.group_color("waveform", "fill").upper()
    assert fill in {
        image.pixelColor(x, y).name().upper()
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    }


def test_loading_is_not_an_edit(window: MainWindow, tmp_path: Path) -> None:
    project = saved_with_samples(window, tmp_path)

    window.open_project(project)
    finish(window)

    assert not window.document().is_dirty
    assert not window.document().can_undo


def test_a_sample_that_will_not_load_is_reported_once(
    window: MainWindow, tmp_path: Path
) -> None:
    project = saved_with_samples(window, tmp_path)
    (tmp_path / "kit" / "1.wav").write_bytes(b"no longer audio")

    window.open_project(project)
    finish(window)

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert notice.message == "1 sample did not load as saved"
    assert notice.detail[0].startswith("1.wav:")


def test_a_sample_changed_since_the_save_says_so(
    window: MainWindow, tmp_path: Path
) -> None:
    project = saved_with_samples(window, tmp_path)
    sample(tmp_path / "kit" / "2.wav", seed=99)  # same name, different audio

    window.open_project(project)
    finish(window)

    [notice] = window.notices().newest_first()
    assert list(notice.detail) == ["2.wav: has changed since the project was saved"]


def test_missing_samples_are_not_tried(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = saved_with_samples(window, tmp_path)
    (tmp_path / "kit" / "0.wav").unlink()
    calls = counting(monkeypatch)

    window.open_project(project)
    finish(window)

    assert sorted(path.name for path in calls) == ["1.wav", "2.wav"]


def test_a_new_project_forgets_the_old_samples(
    window: MainWindow, tmp_path: Path
) -> None:
    window.import_paths([sample(tmp_path / "a.wav", 1)])
    finish(window)
    media_id = window.document().project.media_pool[0].id

    window.document().save_as(tmp_path / "x.3dim")
    window.new_project()

    assert media_id not in window.store()


def test_a_load_does_not_land_in_a_project_opened_meanwhile(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = saved_with_samples(window, tmp_path)
    gate = threading.Event()
    counting(monkeypatch, gate)
    window.open_project(project)
    ids = [media.id for media in window.document().project.media_pool]

    window.new_project()
    gate.set()
    finish(window)

    assert not any(media_id in window.store() for media_id in ids)
