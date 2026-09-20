"""The shell builds. Marked gui: needs a QApplication (offscreen in CI)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDockWidget, QSplitter

from immersive.app import build_application
from immersive.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> object:
    return build_application([])


def test_window_constructs(app: object) -> None:
    window = MainWindow()
    assert window.windowTitle() == "3d immersive"
    assert window.centralWidget() is not None


def test_menu_bar_has_the_specified_menus(app: object) -> None:
    window = MainWindow()
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles == ["File", "Edit", "View", "Transport", "Render", "Help"]


def test_layout_is_splitters_not_docks(app: object) -> None:
    """D-15: a fixed layout with draggable splitters, no dockable panels."""
    window = MainWindow()
    root = window.centralWidget()
    assert isinstance(root, QSplitter)
    assert window.findChildren(QDockWidget) == []
    splitters = window.findChildren(QSplitter)
    # root + upper + left column + workspace
    assert len(splitters) == 4


def test_every_region_is_present(app: object) -> None:
    from immersive.ui.widgets.placeholder import Placeholder

    window = MainWindow()
    panels = window.findChildren(Placeholder)
    assert len(panels) == 7  # pool, params, top, front, 3d, keyframes, timeline
