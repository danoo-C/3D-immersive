"""The media pool on screen. Marked gui."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QEventLoop, QModelIndex
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.io import project_io
from immersive.core.media_store import Prepared, prepare
from immersive.core.model import Project
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.explorer.media_pool import ID_ROLE, MIME, NAME, MediaPool, duration
from immersive.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


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
            raise AssertionError("the import did not finish")
    QApplication.processEvents()


def sample(path: Path, seed: int = 0, seconds: float = 0.25) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.8, 0.8, round(SAMPLE_RATE * seconds)).astype(np.float32)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    root = tmp_path / "kit"
    sample(root / "drums" / "kick.wav", 1)
    sample(root / "drums" / "snare.wav", 2)
    sample(root / "pads" / "warm" / "pad.wav", 3, seconds=1.5)
    sample(root / "top.wav", 4)
    return root


def imported(window: MainWindow, folder: Path) -> MediaPool:
    window._choose_folder = lambda: folder  # type: ignore[method-assign]
    assert window.import_folder()
    finish(window)
    return window.pool()


def shape(item: QStandardItem) -> list[object]:
    """The tree beneath `item`, as names: a folder is (name, [children])."""
    found: list[object] = []
    for row in range(item.rowCount()):
        child = item.child(row, NAME)
        assert child is not None
        if child.data(ID_ROLE) is None:
            found.append((child.text(), shape(child)))
        else:
            found.append(child.text())
    return found


def visible(pool: MediaPool, parent: QModelIndex | None = None) -> list[str]:
    """Every name the filter lets through, depth first."""
    parent = parent or QModelIndex()
    names: list[str] = []
    for row in range(pool.proxy.rowCount(parent)):
        index = pool.proxy.index(row, NAME, parent)
        names.append(index.data())
        names.extend(visible(pool, index))
    return names


# --------------------------------------------------------------------------- #
# the tree
# --------------------------------------------------------------------------- #


def test_the_tree_mirrors_the_folders_beneath_what_was_imported(
    window: MainWindow, kit: Path
) -> None:
    pool = imported(window, kit)
    root = pool.model.invisibleRootItem()
    assert root is not None

    assert shape(root) == [
        ("drums", ["kick.wav", "snare.wav"]),
        ("pads", [("warm", ["pad.wav"])]),
        "top.wav",
    ]


def test_a_row_shows_its_name_and_duration(window: MainWindow, kit: Path) -> None:
    pool = imported(window, kit)

    names = visible(pool)
    assert "pad.wav" in names
    pad = next(m for m in window.document().project.media_pool if m.name == "pad.wav")
    assert duration(pad.frames) == "0:01.500"


def test_the_thumbnails_are_drawn(window: MainWindow, kit: Path) -> None:
    """On a real grab of the pool: the waveform's ink is there."""
    pool = imported(window, kit)
    window.show()
    QApplication.processEvents()

    image = pool.tree.viewport().grab().toImage()
    fill = theme.group_color("waveform", "fill").upper()
    colours = {
        image.pixelColor(x, y).name().upper()
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    }
    assert fill in colours


def test_the_pool_follows_undo_and_redo(window: MainWindow, kit: Path) -> None:
    pool = imported(window, kit)

    window.document().undo()
    assert pool.model.rowCount() == 0

    window.document().redo()
    assert "kick.wav" in visible(pool)


# --------------------------------------------------------------------------- #
# the filter
# --------------------------------------------------------------------------- #


def test_the_filter_ignores_case_and_keeps_the_way_to_a_match(
    window: MainWindow, kit: Path
) -> None:
    pool = imported(window, kit)

    pool.filter.setText("KICK")

    assert visible(pool) == ["drums", "kick.wav"]


def test_clearing_the_filter_brings_everything_back(
    window: MainWindow, kit: Path
) -> None:
    pool = imported(window, kit)
    pool.filter.setText("pad")
    assert visible(pool) == ["pads", "warm", "pad.wav"]

    pool.filter.clear()

    assert visible(pool) == [
        "drums",
        "kick.wav",
        "snare.wav",
        "pads",
        "warm",
        "pad.wav",
        "top.wav",
    ]


# --------------------------------------------------------------------------- #
# missing, and dragging
# --------------------------------------------------------------------------- #


def test_a_missing_row_is_warn_and_says_so(window: MainWindow, tmp_path: Path) -> None:
    """Never by colour alone: the mark is in the text as well."""
    gone = sample(tmp_path / "gone.wav")
    kept = sample(tmp_path / "kept.wav", 5)
    entries = []
    for n, path in enumerate((gone, kept), start=1):
        prepared = prepare(path)
        assert isinstance(prepared, Prepared)
        entries.append(prepared.media_file(f"m-0000000{n}"))
    project_io.save(Project(media_pool=entries), tmp_path / "song.3dim")
    gone.unlink()

    assert window.open_project(tmp_path / "song.3dim")
    root = window.pool().model.invisibleRootItem()
    assert root is not None
    names = {}
    for row in range(root.rowCount()):
        item = root.child(row, NAME)
        assert item is not None
        names[item.text()] = item

    assert "⚠ gone.wav" in names
    assert "kept.wav" in names
    missing = names["⚠ gone.wav"]
    assert missing.foreground().color().name().upper() == theme.color("warn").upper()


def test_a_drag_carries_the_named_type_and_the_ids(
    window: MainWindow, kit: Path
) -> None:
    """04's contract for M3's timeline."""
    pool = imported(window, kit)
    pool.filter.setText("wav")
    drums = pool.proxy.index(0, NAME)
    kick, snare = pool.proxy.index(0, NAME, drums), pool.proxy.index(1, NAME, drums)

    data = pool.proxy.mimeData([kick, snare])

    assert data is not None
    assert data.hasFormat(MIME)
    ids = json.loads(bytes(data.data(MIME).data()).decode("utf-8"))
    by_name = {m.name: m.id for m in window.document().project.media_pool}
    assert ids == [by_name["kick.wav"], by_name["snare.wav"]]


def test_folders_do_not_drag(window: MainWindow, kit: Path) -> None:
    pool = imported(window, kit)
    root = pool.model.invisibleRootItem()
    assert root is not None
    drums = root.child(0, NAME)
    assert drums is not None and drums.text() == "drums"

    assert not drums.isDragEnabled()
