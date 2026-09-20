"""The shell builds. Marked gui: needs a QApplication (offscreen in CI)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDockWidget, QSplitter, QToolBar

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


def test_workspace_is_two_tabs(app: object) -> None:
    """D-49: Top/Front together, 3D on its own."""
    from PySide6.QtWidgets import QTabWidget

    window = MainWindow()
    tabs = window.findChildren(QTabWidget)
    assert len(tabs) == 1
    workspace = tabs[0]
    assert [workspace.tabText(i) for i in range(workspace.count())] == [
        "Top / Front",
        "3D",
    ]


def test_the_ortho_views_share_the_first_tab(app: object) -> None:
    from PySide6.QtWidgets import QTabWidget

    from immersive.ui.widgets.placeholder import Placeholder

    window = MainWindow()
    workspace = window.findChildren(QTabWidget)[0]
    ortho, view3d = workspace.widget(0), workspace.widget(1)
    assert ortho is not None and view3d is not None
    assert len(ortho.findChildren(Placeholder)) == 2
    assert view3d.findChildren(Placeholder) == []  # the 3D tab *is* the panel
    assert isinstance(view3d, Placeholder)


def test_transport_buttons_have_icons_not_ascii(app: object) -> None:
    """04-ui-spec.md, Craft: no ASCII glyphs as UI."""
    window = MainWindow()
    toolbar = window.findChildren(QToolBar)[0]
    actions = [a for a in toolbar.actions() if not a.isSeparator() and a.text()]
    assert actions, "toolbar has no actions"
    for action in actions:
        assert not action.icon().isNull(), action.text()
        assert action.text().isprintable()
        assert not set(action.text()) & set("|<>[]"), action.text()


def test_disabled_actions_explain_themselves(app: object) -> None:
    """A dead button with no tooltip is the thing that reads as unfinished."""
    window = MainWindow()
    toolbar = window.findChildren(QToolBar)[0]
    for action in toolbar.actions():
        if action.isSeparator() or not action.text():
            continue
        assert action.toolTip(), action.text()
