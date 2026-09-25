"""Shared fixtures.

Note there is no sys.path manipulation here. The package is installed
editable (D-27), and adding the source tree to sys.path would defeat the
point of the src-layout.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Set
from pathlib import Path

import pytest

# Qt must not try to open a display in CI or over SSH. Set before any Qt
# import so it applies to the whole session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def _nothing_writes_your_home(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """No test may write the developer's real config, on any platform.

    Qt resolves `QStandardPaths` and `QSettings` from the home directory, so
    anything that asks where themes live or what was last chosen would
    otherwise land in `~/.config` - a suite that changes the machine it ran
    on. Autouse because the hazard is not confined to the tests that mean to
    touch settings: building a `MainWindow` is enough.

    ⚠️ **Session-scoped, because Qt caches the location the first time
    anything asks for it.** Redirecting `HOME` per test looks like it works
    and does not: every test after the first quietly shares the first one's
    directory, so settings leak between tests while the fixture appears to
    isolate them. Found by a test that saw a notice raised by its
    predecessor. `_empty_config` below is what gives each test a clean
    slate; this one only decides *where* the one shared file lives.

    ⚠️ **Settings are forced into an INI file inside that home.** The native
    `QSettings` format is a file under `HOME` only on Linux: on Windows it is
    the registry and on macOS CFPreferences, and redirecting the environment
    reaches neither. Without this, `_empty_config`'s `clear()` would empty
    the developer's real settings before every test on exactly the platforms
    `06` recommends for anything audible - and every check here would pass on
    Linux, which is the only leg anyone runs locally.

    PySide6 is imported inside the fixture rather than at module scope, so a
    core-only run does not pull Qt in to set something it will never use.

    The environment is saved and restored by hand rather than through
    `monkeypatch`, which is function-scoped and cannot be requested here -
    and which, when it was requested by an autouse fixture, moved every
    test's patches to the back of its own teardown and broke a cache-clearing
    fixture.
    """
    home = tmp_path_factory.mktemp("home")
    redirected = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "APPDATA": str(home / "AppData"),
        # The peak cache (M2 phase 4). Resolved by `core` from exactly these,
        # not by Qt, so on every platform this is the whole of the redirect.
        "XDG_CACHE_HOME": str(home / ".cache"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "USERPROFILE": str(home),
    }
    before = {name: os.environ.get(name) for name in redirected}
    os.environ.update(redirected)

    from PySide6.QtCore import QSettings, QStandardPaths

    QStandardPaths.setTestModeEnabled(True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(home / "settings")
    )
    try:
        yield
    finally:
        QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
        QStandardPaths.setTestModeEnabled(False)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(scope="session", autouse=True)
def _nothing_waits_for_a_person() -> Iterator[None]:
    """A modal dialog in an offscreen test fails the test instead of hanging it.

    Offscreen, nobody can click, so a real `exec()` waits forever and the
    suite stops with no failure and no name. Every place the application
    waits for a person is a method a test replaces; this is what happens to a
    test that forgot to.

    ⚠️ It reaches what goes through Python: a dialog's `exec()` and
    `QFileDialog`'s static choosers. It cannot reach `QMessageBox.question`
    and its siblings, which run their loop in C++ - so the application never
    calls them, and builds a box and calls `exec()` instead. Found by a probe
    that hung while this was being written.

    Patched and restored by hand, for the reason the fixture above gives.
    """
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "a test reached a real modal dialog - replace the window method "
            "that asks instead"
        )

    patched = [
        (QDialog, "exec"),
        (QMessageBox, "exec"),
        (QFileDialog, "exec"),
        (QFileDialog, "getOpenFileName"),
        (QFileDialog, "getOpenFileNames"),
        (QFileDialog, "getSaveFileName"),
        (QFileDialog, "getExistingDirectory"),
    ]
    saved = [(owner, name, owner.__dict__.get(name)) for owner, name in patched]
    for owner, name in patched:
        setattr(owner, name, staticmethod(refuse))
    try:
        yield
    finally:
        for owner, name, original in saved:
            if original is None:
                delattr(owner, name)
            else:
                setattr(owner, name, original)


@pytest.fixture(autouse=True)
def _tidied_as_marked(request: pytest.FixtureRequest) -> Iterator[None]:
    """A `gui` test is tidied up after; any other test must need no tidying.

    The two fixtures below undo what Qt leaves behind - windows, remembered
    settings, installed themes - and until tests-speeds step 6 they ran
    around every test. Four tests in five never touch Qt, so that was time
    spent tidying nothing, and they now run only for tests marked `gui`.
    `test_markers.py` is what makes the mark something to rely on.

    What that gives up is checked instead of assumed. A test without the mark
    fails at teardown if it built the `QApplication`, left a window alive,
    or left a setting or a directory in the config location - each of which
    would otherwise leak into whichever test ran next in that process, with
    nothing to say where it came from. Checking costs a fraction of wiping,
    and it names the test that did it.

    The body is `tidied`, so that `test_markers.py` can drive it both ways.
    """
    yield from tidied(
        request, marked=request.node.get_closest_marker("gui") is not None
    )


def tidied(request: pytest.FixtureRequest, *, marked: bool) -> Iterator[None]:
    """The fixture above, as a generator a test can drive with either answer.

    A marked test gets the two fixtures below through `getfixturevalue`
    rather than as parameters, which would run them for every test. Asked
    for in this order, they tear down in the reverse - settings first, then
    windows - as they did when both were autouse.
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    if marked:
        request.getfixturevalue("_no_window_outlives_its_test")
        request.getfixturevalue("_empty_config")
        yield
        return

    instance = QCoreApplication.instance()
    windows = (
        set(QApplication.topLevelWidgets())
        if isinstance(instance, QApplication)
        else set()
    )
    yield
    left = left_behind(instance is not None, windows)
    assert not left, (
        f"{request.node.nodeid} is not marked gui, and left behind "
        + ", ".join(left)
        + " - mark it gui, so it is tidied up after"
    )


def left_behind(had_application: bool, windows: Set[object]) -> list[str]:
    """What a test that needs no Qt must not leave: exactly what the two
    fixtures below would otherwise have cleared."""
    from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths
    from PySide6.QtWidgets import QApplication

    found = []
    instance = QCoreApplication.instance()
    if instance is not None and not had_application:
        found.append("a QApplication")
    if isinstance(instance, QApplication):
        alive = [w for w in QApplication.topLevelWidgets() if w not in windows]
        if alive:
            found.append(f"{len(alive)} window{'s' if len(alive) != 1 else ''}")
    if QSettings().allKeys():
        found.append("settings")
    base = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation
        )
    )
    if base.is_dir() and any(child.is_dir() for child in base.iterdir()):
        found.append(f"a directory in {base}")
    return found


@pytest.fixture
def _no_window_outlives_its_test() -> Iterator[None]:
    """Every parentless widget a `gui` test made is gone before the next test.

    `deleteLater()` only deletes when the event loop next turns, and nothing
    in a test turns it, so windows piled up for the whole session. That is
    not only memory: building a window applies the theme, and applying the
    theme re-polishes every widget in every window still alive - so each
    window cost more than the one before. Found when M2 phase 1 added twenty
    window tests and the suite went from seventy seconds to over three
    minutes; a probe had eight windows alive after eight were released.

    Posted deletions are delivered by hand, the way pytest-qt does it.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return
    for widget in QApplication.topLevelWidgets():
        if widget.parent() is None:
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def _empty_config() -> Iterator[None]:
    """Every `gui` test starts with nothing remembered and no themes installed.

    One config location is shared by the whole session (see above), so
    without this a test inherits whatever its predecessor chose or dropped
    in - and a persistence test can pass because of the test before it
    rather than because of the code. That is not hypothetical: it is how the
    caching above was found.

    Settings are cleared through `QSettings` rather than by deleting the
    file, because Qt holds the parsed file in a cache that outlives it. The
    directories beside it - `themes/` among them - are removed outright.
    """
    from PySide6.QtCore import QSettings, QStandardPaths

    def wipe() -> None:
        QSettings().clear()
        QSettings().sync()
        base = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppConfigLocation
            )
        )
        for child in base.glob("*"):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    wipe()
    yield
    wipe()
