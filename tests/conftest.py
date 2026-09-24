"""Shared fixtures.

Note there is no sys.path manipulation here. The package is installed
editable (D-27), and adding the source tree to sys.path would defeat the
point of the src-layout.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
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


@pytest.fixture(autouse=True)
def _empty_config() -> Iterator[None]:
    """Every test starts with nothing remembered and no themes installed.

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
