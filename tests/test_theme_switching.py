"""Switching themes repaints the running application (F-48, D-82).

Marked gui: a QApplication, offscreen. Home and settings are redirected by
the autouse fixture in conftest.py, so nothing here touches a real config.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from immersive.app import build_application
from immersive.ui import icons, theme, theme_io, theme_menu
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity
from immersive.ui.widgets.placeholder import Placeholder

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _restore_theme() -> Iterator[None]:
    build_application([])
    before = theme.active()
    yield
    theme.use(before)
    icons.icon.cache_clear()
    icons.app_icon.cache_clear()


@pytest.fixture
def window() -> Iterator[MainWindow]:
    made = MainWindow()
    yield made
    made.deleteLater()


def loud() -> theme.Theme:
    """A theme where every single token differs from the built-in.

    So that "did anything keep an old colour" is answerable by looking for
    any old colour anywhere, rather than by knowing which widget uses which
    token.
    """
    builtin = theme_io.builtin()
    swapped = {
        name: f"#{(index * 17 + 1) % 256:02X}{(index * 29 + 3) % 256:02X}80"
        for index, name in enumerate(sorted(builtin.tokens))
    }
    assert not set(swapped.values()) & set(builtin.tokens.values())
    return replace(builtin, name="Loud", tokens=swapped)


def written(path: Path, **document: object) -> Path:
    path.write_text(
        json.dumps({"schema_version": theme_io.SCHEMA_VERSION, **document}),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# the repaint
# --------------------------------------------------------------------------- #


def test_applying_a_theme_changes_the_application_stylesheet(
    window: MainWindow,
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    before = app.styleSheet()

    window.apply_theme(loud())

    assert app.styleSheet() != before


def test_a_placeholder_follows_the_switch(window: MainWindow) -> None:
    """The inline stylesheets D-82 exists for."""
    panel = window.findChildren(Placeholder)[0]
    before = panel.styleSheet()
    assert theme_io.builtin().token("surface.panel") in before

    window.apply_theme(loud())

    assert panel.styleSheet() != before
    assert theme_io.builtin().token("surface.panel") not in panel.styleSheet()


def test_no_widget_keeps_a_colour_from_the_old_theme(window: MainWindow) -> None:
    """The acceptance line, asserted by looking rather than by remembering.

    Every token differs under `loud()`, so any built-in colour surviving
    anywhere in any widget's stylesheet is a widget the walk did not reach.
    A test that checked the widgets we thought of would find only those.
    """
    old = set(theme_io.builtin().tokens.values())

    window.apply_theme(loud())

    survivors = [
        f"{type(widget).__name__}: {widget.styleSheet()}"
        for widget in [window, *window.findChildren(QWidget)]
        if any(colour in widget.styleSheet() for colour in old)
    ]

    assert not survivors, "widgets kept the old theme:\n" + "\n".join(survivors)


def test_the_icon_cache_is_dropped_on_a_switch(window: MainWindow) -> None:
    """Phase 1 predicted this exact failure and left the note that says so.

    `icons.icon()` memoises the rendered QIcon against its arguments, so the
    first call under one theme answers every later call under any other.
    """
    icons.icon.cache_clear()
    icons.icon("play")
    assert icons.icon.cache_info().currsize == 1

    window.apply_theme(loud())

    assert icons.icon.cache_info().currsize <= len(window._icon_actions) + 1
    before = icons.icon("play")
    window.apply_theme(theme_io.builtin())
    assert icons.icon("play") is not before, "a re-render, not the cached one"


def test_the_order_is_use_then_clear_then_sheet_then_walk(
    window: MainWindow,
) -> None:
    """D-82's order, asserted through its observable consequence.

    A widget that re-read its colours before `use()` had landed would get the
    colour it already had, so the whole walk would be a no-op — and the
    stylesheet would be built from the outgoing theme.
    """
    chosen = loud()
    window.apply_theme(chosen)

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert theme.active() is chosen
    assert app.styleSheet() == theme.stylesheet(chosen)


# --------------------------------------------------------------------------- #
# the menu
# --------------------------------------------------------------------------- #


def test_the_view_menu_has_a_theme_submenu(window: MainWindow) -> None:
    assert window._theme_menu.title() == "&Theme"
    labels = [action.text() for action in window._theme_menu.actions()]
    assert theme_io.builtin().name in labels


def test_a_theme_dropped_in_appears_without_a_restart(window: MainWindow) -> None:
    """F-48, and the reason the menu repopulates on `aboutToShow`."""
    labels = [action.text() for action in window._theme_menu.actions()]
    assert "ocean" not in labels

    directory = theme_menu.user_theme_directory()
    written(directory / f"ocean{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})

    window._theme_menu.repopulate()

    assert "ocean" in [action.text() for action in window._theme_menu.actions()]


def test_an_empty_theme_directory_says_so_rather_than_showing_nothing(
    window: MainWindow,
) -> None:
    window._theme_menu.repopulate()
    entries = window._theme_menu.actions()

    assert [action.text() for action in entries][1:] == ["No user themes found"]
    assert not entries[1].isEnabled()


def test_choosing_a_user_theme_applies_it(window: MainWindow) -> None:
    directory = theme_menu.user_theme_directory()
    path = written(
        directory / f"red{theme_io.SUFFIX}",
        name="Red",
        tokens={"accent": "#FF0000"},
    )

    window.choose_theme(path)

    assert theme.color("accent") == "#FF0000"
    assert theme.active().name == "Red"


def test_choosing_the_built_in_comes_back(window: MainWindow) -> None:
    window.apply_theme(loud())

    window.choose_theme(None)

    assert theme.active() == theme_io.builtin()


def test_the_menu_is_exclusive(window: MainWindow) -> None:
    directory = theme_menu.user_theme_directory()
    written(directory / f"one{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})
    written(directory / f"two{theme_io.SUFFIX}", tokens={"accent": "#00FF00"})
    window._theme_menu.repopulate()

    entries = {action.text(): action for action in window._theme_menu.actions()}
    entries["one"].trigger()

    assert entries["one"].isChecked()
    assert not entries["two"].isChecked()
    current = window._theme_menu.current()
    assert current is not None
    assert current.stem == "one"


# --------------------------------------------------------------------------- #
# what survives a restart (D-83)
# --------------------------------------------------------------------------- #


def test_a_chosen_theme_survives_a_new_window() -> None:
    """ "Across a restart" is a new MainWindow: QSettings outlives both."""
    directory = theme_menu.user_theme_directory()
    path = written(
        directory / f"red{theme_io.SUFFIX}", name="Red", tokens={"accent": "#FF0000"}
    )

    first = MainWindow()
    first.choose_theme(path)
    first.deleteLater()

    theme.use(theme_io.builtin())
    second = MainWindow()

    assert theme.active().name == "Red"
    assert second._theme_menu.current() == path
    second.deleteLater()


def test_the_built_in_survives_a_new_window() -> None:
    directory = theme_menu.user_theme_directory()
    path = written(directory / f"red{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})

    first = MainWindow()
    first.choose_theme(path)
    first.choose_theme(None)
    first.deleteLater()

    second = MainWindow()

    assert theme.active() == theme_io.builtin()
    assert second._theme_menu.current() is None
    second.deleteLater()


def test_a_theme_that_has_gone_falls_back_and_says_so() -> None:
    """D-83's whole reason: silence here reads as a broken application."""
    directory = theme_menu.user_theme_directory()
    path = written(directory / f"doomed{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})

    first = MainWindow()
    first.choose_theme(path)
    first.deleteLater()
    path.unlink()

    second = MainWindow()

    assert theme.active() == theme_io.builtin()
    assert second._theme_menu.current() is None
    reported = second.notices().newest_first()
    assert len(reported) == 1
    assert "no longer there" in reported[0].message
    assert reported[0].severity is Severity.WARN
    second.deleteLater()


def test_restoring_a_theme_is_quiet_when_it_works() -> None:
    """A notice on every launch is how people learn to stop reading them."""
    directory = theme_menu.user_theme_directory()
    path = written(directory / f"quiet{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})

    first = MainWindow()
    first.choose_theme(path)
    first.deleteLater()

    second = MainWindow()

    assert second.notices().newest_first() == []
    second.deleteLater()


def test_restoring_a_broken_theme_still_reports() -> None:
    """Quiet when it works is not quiet when it does not."""
    directory = theme_menu.user_theme_directory()
    path = directory / f"broken{theme_io.SUFFIX}"
    written(path, tokens={"nope": "#FF0000"})

    first = MainWindow()
    first.choose_theme(path)
    first.deleteLater()

    second = MainWindow()

    reported = second.notices().newest_first()
    assert len(reported) == 1
    assert reported[0].severity is Severity.WARN
    second.deleteLater()
