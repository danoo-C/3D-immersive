"""The shell builds. Marked gui: needs a QApplication (offscreen in CI)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMenu,
    QSplitter,
    QToolBar,
    QToolButton,
    QWidget,
)

from immersive.app import build_application
from immersive.ui import theme
from immersive.ui.main_window import MainWindow

pytestmark = pytest.mark.gui

ROADMAP = Path(__file__).resolve().parents[1] / "docs" / "06-roadmap.md"


@pytest.fixture(scope="module")
def app() -> object:
    return build_application([])


def test_window_constructs(app: object) -> None:
    window = MainWindow()
    assert window.windowTitle() == "Untitled[*] — 3d immersive"
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


def _menu_actions(window: MainWindow) -> list[QAction]:
    """Every non-separator action in the menu bar.

    Callers must keep `window` alive for as long as they use the result:
    the QActions are owned by it, and shiboken deletes the C++ side the
    moment the last Python reference to the window goes.
    """
    return [
        action
        for entry in window.menuBar().actions()
        if isinstance(menu := entry.menu(), QMenu)
        for action in menu.actions()
        if not action.isSeparator()
    ]


def test_disabled_actions_explain_themselves(app: object) -> None:
    """A dead control with no tooltip is the thing that reads as unfinished.

    04-ui-spec.md, Craft: a not-yet-implemented action is disabled and says
    why in its tooltip. This walked only the toolbar for a while, which is
    exactly where the rule already held - all nineteen disabled *menu*
    actions were bare, and the rule was tested where it could not fail.

    "Not built yet" is one reason; since M2, having nothing to undo is the
    other. What is asserted is that there *is* a reason, on the line after
    the action's name.
    """
    window = MainWindow()
    toolbar = window.findChildren(QToolBar)[0]
    controls: list[QAction] = [
        action
        for action in toolbar.actions()
        if not action.isSeparator() and action.text()
    ]
    controls += _menu_actions(window)
    assert len(controls) > 20, "the walk stopped finding controls"

    for action in controls:
        label = action.text().replace("&", "")
        assert action.toolTip(), label
        if not action.isEnabled():
            assert action.toolTip().partition("\n")[2], label


def test_menus_actually_show_their_tooltips(app: object) -> None:
    """Qt suppresses tooltips inside a QMenu unless asked.

    Without this the explanations above exist in the object model and reach
    nobody — which reads as done and is not.
    """
    window = MainWindow()
    for entry in window.menuBar().actions():
        menu = entry.menu()
        assert isinstance(menu, QMenu)
        assert menu.toolTipsVisible(), entry.text()


def test_tooltips_carry_the_shortcut(app: object) -> None:
    """04-ui-spec.md, Craft: tooltips carry the shortcut as `Action  (Key)`."""
    window = MainWindow()
    for action in _menu_actions(window):
        key = action.shortcut().toString()
        if key:
            assert f"({key})" in action.toolTip(), action.text()


def test_undo_and_redo_match_the_specified_keys(app: object) -> None:
    """04-ui-spec.md's keyboard table says Ctrl+Z / Ctrl+Shift+Z.

    QKeySequence.StandardKey.Redo resolves to Ctrl+Y on Linux and Windows,
    which disagreed with both the spec and the toolbar's own tooltip inside
    the same window.
    """
    window = MainWindow()
    keys = {
        action.text().replace("&", ""): action.shortcut().toString()
        for action in _menu_actions(window)
    }
    assert keys["Undo"] == "Ctrl+Z"
    assert keys["Redo"] == "Ctrl+Shift+Z"


def test_quit_has_a_shortcut_on_every_platform(app: object) -> None:
    """StandardKey.Quit resolves to nothing under some Linux platform themes.

    It left the only action in the application that actually works as the
    only one with no key at all.
    """
    window = MainWindow()
    quit_action = next(
        action
        for action in _menu_actions(window)
        if action.text().replace("&", "") == "Quit"
    )
    assert quit_action.isEnabled()
    assert not quit_action.shortcut().isEmpty()


def test_the_window_carries_an_icon(app: object) -> None:
    """Otherwise the taskbar and alt-tab show Qt's default placeholder."""
    window = MainWindow()
    icon = window.windowIcon()
    assert not icon.isNull()
    assert not icon.pixmap(256, 256).isNull()


def test_no_control_is_a_label_dressed_as_a_button(app: object) -> None:
    """The ARM toggle was a bordered QLabel: the one dead control that looked
    alive, in a toolbar of visibly greyed ones."""
    window = MainWindow()
    toolbar = window.findChildren(QToolBar)[0]
    for label in toolbar.findChildren(QLabel):
        style = label.styleSheet()
        assert "border:" not in style, label.text()

    arm = next(
        button for button in toolbar.findChildren(QToolButton) if button.text() == "ARM"
    )
    assert arm.isCheckable()
    assert not arm.isEnabled()
    assert not arm.icon().isNull()


def test_the_transport_readout_is_the_only_primary_chip(app: object) -> None:
    """04-ui-spec.md: the position readout leads, the rest of the bar supports.

    Asserted because the two states are one boolean apart, and a `_chip` that
    forgot the distinction would render a toolbar where nothing leads and no
    test would mind.
    """
    window = MainWindow()
    primary = window._chip("1.1.000", primary=True).styleSheet()
    secondary = window._chip("120.0 BPM").styleSheet()

    assert theme.color("text.primary") in primary
    assert theme.color("text.secondary") in secondary
    assert primary != secondary


# --------------------------------------------------------------------------- #
# promises
# --------------------------------------------------------------------------- #


def completed_milestones() -> set[str]:
    """Every milestone `06` marks ✅, read from its headings."""
    text = ROADMAP.read_text(encoding="utf-8")
    return set(re.findall(r"^## ([MS]\d+) — .*✅", text, flags=re.MULTILINE))


def stale_promises(tooltips: list[str], complete: set[str]) -> list[str]:
    """Tooltips saying something arrives at a milestone that already has."""
    return [
        tip
        for tip in tooltips
        for milestone in re.findall(r"arrives? at ([MS]\d+)", tip)
        if milestone in complete
    ]


def test_the_roadmap_markers_are_where_this_reads_them() -> None:
    """If the headings change shape the check below goes vacuous, so say so."""
    assert {"M0", "S0", "M1", "M9"} <= completed_milestones()


def test_the_check_would_have_caught_this_phase(app: object) -> None:
    """M1 finished headless, and five actions went on saying they arrive at M1
    for as long as nothing read the roadmap to notice. That is the reason M2
    phase 1 exists."""
    stale = "Save  (Ctrl+S)\nNot built yet — the project model arrives at M1."

    assert stale_promises([stale], completed_milestones()) == [stale]


def test_no_tooltip_promises_a_milestone_that_has_arrived(app: object) -> None:
    """Every tooltip in the window, actions and widgets alike, against `06`."""
    window = MainWindow()
    tooltips = [action.toolTip() for action in window.findChildren(QAction)]
    tooltips += [widget.toolTip() for widget in window.findChildren(QWidget)]
    assert any("arrive" in tip for tip in tooltips), "the walk found no promises"

    assert stale_promises(tooltips, completed_milestones()) == []
