"""Switching themes repaints the running application (F-48, D-82).

Marked gui: a QApplication, offscreen. Home and settings are redirected by
the autouse fixture in conftest.py, so nothing here touches a real config.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
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


def test_the_order_itself_is_use_then_clear_then_sheet_then_walk(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-82 says the order is the decision, so the order is what is asserted.

    The consequence test above cannot see every reordering. Moving `use()`
    after the sheet is invisible today, because `stylesheet()` is handed the
    theme and nothing between the cache clears and `use()` reads a colour -
    and it stops being invisible the first time something does, which is the
    moment nobody will think to look. The window icon's cache is the same:
    nothing asserts on the window icon's pixels, so only the call shows it.
    """
    calls: list[str] = []

    def recording(name: str, real: Callable[..., object]) -> Callable[..., object]:
        def record(*args: object, **kwargs: object) -> object:
            calls.append(name)
            return real(*args, **kwargs)

        return record

    monkeypatch.setattr(theme, "use", recording("use", theme.use))
    monkeypatch.setattr(
        icons.icon, "cache_clear", recording("icons", icons.icon.cache_clear)
    )
    monkeypatch.setattr(
        icons.app_icon, "cache_clear", recording("app icon", icons.app_icon.cache_clear)
    )
    monkeypatch.setattr(theme, "stylesheet", recording("sheet", theme.stylesheet))
    monkeypatch.setattr(MainWindow, "retheme", recording("walk", MainWindow.retheme))

    window.apply_theme(loud())

    assert calls == ["use", "icons", "app icon", "sheet", "walk"]


# --------------------------------------------------------------------------- #
# not repainting what is already painted
# --------------------------------------------------------------------------- #


def sheets_set(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every stylesheet given to the application from here on."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    real = app.setStyleSheet
    calls: list[str] = []

    def record(sheet: str) -> None:
        calls.append(sheet)
        real(sheet)

    monkeypatch.setattr(app, "setStyleSheet", record)
    return calls


def test_a_new_window_does_not_repaint_the_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-applying the theme `build_application()` had just applied was half
    of what building a window cost - Qt re-polishes every widget on every
    `setStyleSheet`, identical or not. Found by the suite's speed plan."""
    calls = sheets_set(monkeypatch)

    made = MainWindow()

    assert calls == []
    made.deleteLater()


def test_applying_the_theme_already_applied_does_nothing(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = sheets_set(monkeypatch)

    window.apply_theme(theme.active())

    assert calls == []


def test_the_same_theme_over_another_sheet_is_still_painted(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both halves of the check: the active theme can be right while the
    application still wears another theme's sheet, and then skipping would
    leave it wrong on screen."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setStyleSheet(theme.stylesheet(loud()))
    calls = sheets_set(monkeypatch)

    window.apply_theme(theme.active())

    assert calls == [theme.stylesheet(theme.active())]


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


def test_opening_the_menu_is_what_rescans(window: MainWindow) -> None:
    """F-48 needs the rescan tied to opening the menu, not to a caller.

    Every other test here calls `repopulate()` itself, so none of them would
    notice the connection to `aboutToShow` going - and then a file dropped in
    needs a restart again.
    """
    directory = theme_menu.user_theme_directory()
    written(directory / f"ocean{theme_io.SUFFIX}", tokens={"accent": "#FF0000"})

    window._theme_menu.aboutToShow.emit()

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


# --------------------------------------------------------------------------- #
# the milestone's own acceptance
# --------------------------------------------------------------------------- #


def test_a_broken_theme_is_listed_selectable_reported_and_survivable(
    window: MainWindow,
) -> None:
    """M9's acceptance line, as one journey.

    "a deliberately broken theme file is reported without preventing
    startup" — so it has to appear in the menu, be selectable, report what is
    wrong *in the UI*, and leave the application painting whatever it could
    salvage.
    """
    directory = theme_menu.user_theme_directory()
    path = directory / f"broken{theme_io.SUFFIX}"
    written(
        path,
        name="Broken",
        tokens={"accent": "not a colour", "invented": "#FF0000"},
        groups={"spaceship": {"hull": "#FF0000"}},
    )

    window._theme_menu.repopulate()
    entries = {action.text(): action for action in window._theme_menu.actions()}
    assert "broken" in entries, "it is listed"
    assert entries["broken"].isEnabled(), "and selectable"

    entries["broken"].trigger()

    # Still painting, on what could be salvaged.
    assert theme.stylesheet(theme.active())
    assert theme.color("accent") == theme_io.builtin().token("accent")

    # Reported, in the UI, not on stderr (F-56).
    reported = window.notices().newest_first()
    assert len(reported) == 1
    assert reported[0].severity is Severity.WARN
    assert len(reported[0].detail) == 3, reported[0].detail
    assert window.statusBar().currentMessage() == reported[0].message
    assert not window._notice_count.isHidden()


def test_a_theme_that_is_not_even_json_is_reported_as_an_error(
    window: MainWindow,
) -> None:
    directory = theme_menu.user_theme_directory()
    path = directory / f"garbage{theme_io.SUFFIX}"
    path.write_text("this is not json", encoding="utf-8")

    window.choose_theme(path)

    reported = window.notices().newest_first()
    assert reported[0].severity is Severity.ERROR
    assert theme.active() == theme_io.builtin(), "and it still paints"


def test_a_theme_changing_only_the_accent_changes_only_the_accent_rules(
    window: MainWindow,
) -> None:
    """The milestone's own line, met more precisely than it asks.

    The phase doc names "the playhead and focus ring". There is no playhead —
    the timeline is M3's, and 04's ownership table says so. What is assertable
    now is stronger than the sentence: **every rule that resolves to accent
    changes, and no other byte of the sheet does.** That is what "and nothing
    else" means.
    """
    builtin = theme_io.builtin()
    before = theme.stylesheet(builtin)
    old_accent = builtin.token("accent")
    new_accent = "#FF0000"

    directory = theme_menu.user_theme_directory()
    window.choose_theme(
        written(
            directory / f"accent{theme_io.SUFFIX}",
            name="Red accent",
            tokens={"accent": new_accent},
        )
    )
    after = theme.stylesheet(theme.active())

    assert before != after, "something changed"
    assert len(before.splitlines()) == len(after.splitlines())

    changed = [
        (was, now)
        for was, now in zip(before.splitlines(), after.splitlines(), strict=True)
        if was != now
    ]
    assert changed, "and it was the sheet that changed"
    for was, now in changed:
        assert old_accent in was, f"a line changed that was not accent: {was}"
        assert now == was.replace(old_accent, new_accent)

    # The focus ring is one of them, so the assertion keeps its connection to
    # what the acceptance line was actually asking about. Only the selector
    # can say so: every changed line contains the new accent by construction.
    assert any(":focus" in was for was, _ in changed), changed


def test_the_accent_reaches_actual_pixels(window: MainWindow) -> None:
    """ "Visibly" — rendered, not merely substituted into a string.

    Offscreen Qt still rasterises, so this is a real image. A stylesheet that
    is correct and never reaches the screen would pass every other test in
    this file.
    """
    window.resize(400, 300)
    directory = theme_menu.user_theme_directory()
    window.choose_theme(
        written(
            directory / f"green{theme_io.SUFFIX}",
            name="Green",
            tokens={"surface.window": "#00FF00"},
        )
    )
    window.show()

    image = window.grab().toImage()
    colours = {
        image.pixelColor(x, y).name().upper()
        for x in range(0, image.width(), 7)
        for y in range(0, image.height(), 7)
    }

    assert "#00FF00" in colours, sorted(colours)
