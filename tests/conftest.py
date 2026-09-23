"""Shared fixtures.

Note there is no sys.path manipulation here. The package is installed
editable (D-27), and adding the source tree to sys.path would defeat the
point of the src-layout.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Qt must not try to open a display in CI or over SSH. Set before any Qt
# import so it applies to the whole session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _nothing_writes_your_home(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """No test may write the developer's real config, on any platform.

    Qt resolves `QStandardPaths` and `QSettings` from the home directory, so
    anything that asks where themes live or what was last chosen would
    otherwise land in `~/.config` - a suite that changes the machine it ran
    on, and a persistence test that can pass because of yesterday's run
    rather than because of today's code.

    `setTestModeEnabled` moves Qt into a throwaway corner of the home
    directory, which is most of it; the environment redirects say *which*
    home. Autouse because the hazard is not confined to the tests that mean
    to touch settings - building a `MainWindow` is enough.

    PySide6 is imported inside the fixture rather than at module scope, so a
    core-only run does not pull Qt in to set something it will never use.

    The environment is saved and restored by hand rather than through
    `monkeypatch`. Requesting that fixture here would make it a dependency of
    an autouse fixture, which moves it to the front of every test's setup and
    therefore to the *back* of every test's teardown - so a test that patched
    something would still be patched while later fixtures tore down. That is
    not hypothetical: it broke a cache-clearing fixture on the first run.
    """
    home = tmp_path_factory.mktemp("home")
    redirected = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "APPDATA": str(home / "AppData"),
    }
    before = {name: os.environ.get(name) for name in redirected}
    os.environ.update(redirected)

    from PySide6.QtCore import QStandardPaths

    QStandardPaths.setTestModeEnabled(True)
    try:
        yield
    finally:
        QStandardPaths.setTestModeEnabled(False)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
