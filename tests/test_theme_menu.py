"""Where themes are found, and what the application remembers.

⚠️ Every test here runs under `QStandardPaths.setTestModeEnabled(True)`, with
`QSettings` forced into an INI file in a temporary home. Without them
`user_theme_directory()` creates a directory in the developer's real config
and `QSettings` writes their real settings — a test run that changes the
machine it ran on, and a persistence test that can pass because of
yesterday's run rather than because of today's code. The last section below
asserts both, because nothing else would notice either going.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QStandardPaths

from immersive.app import build_application
from immersive.ui import theme_io, theme_menu

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    """A QApplication. Home and settings are `conftest.py`'s, for everyone."""
    build_application([])
    yield


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def test_themes_are_found_and_sorted(tmp_path: Path) -> None:
    """Sorted, so the menu does not depend on filesystem iteration order."""
    for name in ("zebra", "apple", "mango"):
        (tmp_path / f"{name}{theme_io.SUFFIX}").write_text("{}", encoding="utf-8")

    found = theme_io.discover(tmp_path)

    assert [path.stem for path in found] == ["apple", "mango", "zebra"]


def test_a_missing_directory_is_empty_rather_than_an_error(tmp_path: Path) -> None:
    """First run, before anything has created it."""
    assert theme_io.discover(tmp_path / "not there") == []


def test_an_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    assert theme_io.discover(tmp_path) == []


def test_only_theme_files_are_found(tmp_path: Path) -> None:
    (tmp_path / f"real{theme_io.SUFFIX}").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "project.3dim").write_text("{}", encoding="utf-8")
    (tmp_path / f"a.directory{theme_io.SUFFIX}").mkdir()

    found = theme_io.discover(tmp_path)

    assert [path.name for path in found] == [f"real{theme_io.SUFFIX}"]


# --------------------------------------------------------------------------- #
# the directory
# --------------------------------------------------------------------------- #


def test_the_theme_directory_is_created_on_use() -> None:
    directory = theme_menu.user_theme_directory()

    assert directory.is_dir()
    assert directory.name == theme_menu.THEMES_DIRNAME


def test_creating_the_directory_twice_is_fine() -> None:
    first = theme_menu.user_theme_directory()
    second = theme_menu.user_theme_directory()

    assert first == second
    assert first.is_dir()


def test_the_directory_can_be_asked_for_without_being_created() -> None:
    """Importing a module must not make a directory on somebody's machine."""
    directory = theme_menu.user_theme_directory(create=False)

    assert not directory.exists()


def test_listing_the_themes_makes_no_directory() -> None:
    """Step 4's bug: the menu listed themes, and listing created the folder.

    Building a window was enough to put a directory in the developer's real
    config. Listing a directory is not a reason to make one.
    """
    assert theme_menu.user_themes() == []
    assert not theme_menu.user_theme_directory(create=False).exists()


def test_importing_the_ui_makes_no_directory(tmp_path: Path) -> None:
    """Created on use, never at import - asserted where import happens.

    Test modules are imported during collection, before any fixture has
    redirected anything, so a directory made at import lands in the real
    home of whoever runs the suite and no fixture can stop it. A fresh
    interpreter with its own empty home is the only place this is visible.
    """
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", "import immersive.ui.main_window"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "APPDATA": str(home / "AppData"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert not list(home.rglob("*")), "importing made something in the home"


def test_user_themes_reads_the_directory() -> None:
    directory = theme_menu.user_theme_directory()
    (directory / f"ocean{theme_io.SUFFIX}").write_text("{}", encoding="utf-8")

    assert [path.stem for path in theme_menu.user_themes()] == ["ocean"]


# --------------------------------------------------------------------------- #
# what is remembered (D-83)
# --------------------------------------------------------------------------- #


def test_nothing_remembered_means_the_built_in() -> None:
    assert theme_menu.remembered() is None


def test_a_path_survives(tmp_path: Path) -> None:
    chosen = tmp_path / f"ocean{theme_io.SUFFIX}"
    theme_menu.remember(chosen)

    assert theme_menu.remembered() == chosen


def test_the_built_in_is_remembered_as_a_sentinel(tmp_path: Path) -> None:
    """Not an empty string, which a bug could produce by accident (D-83)."""
    theme_menu.remember(tmp_path / f"ocean{theme_io.SUFFIX}")
    theme_menu.remember(None)

    assert QSettings().value(theme_menu.SETTINGS_KEY) == theme_menu.BUILTIN_SENTINEL
    assert theme_menu.remembered() is None


def test_a_remembered_path_comes_back_even_when_the_file_has_gone(
    tmp_path: Path,
) -> None:
    """Deciding what to do about it belongs to the caller that can report it.

    Falling back silently here is the behaviour D-83 exists to prevent: the
    theme somebody chose is gone and the application should say it noticed.
    """
    missing = tmp_path / f"deleted{theme_io.SUFFIX}"
    theme_menu.remember(missing)

    assert theme_menu.remembered() == missing
    assert not missing.exists()


def test_a_stored_value_of_the_wrong_kind_means_the_built_in() -> None:
    """QSettings hands back whatever was written, including from an old build."""
    QSettings().setValue(theme_menu.SETTINGS_KEY, 7)

    assert theme_menu.remembered() is None


# --------------------------------------------------------------------------- #
# the suite's own isolation
# --------------------------------------------------------------------------- #


def test_settings_are_a_file_inside_the_test_home() -> None:
    """Not the registry, not CFPreferences, not the developer's `~/.config`.

    The format line is what fails on every platform if `conftest.py` stops
    forcing INI - including Linux, where the path alone would still pass
    because the native format there happens to be a file under `HOME`.
    """
    settings = QSettings()

    assert settings.format() == QSettings.Format.IniFormat
    assert Path(settings.fileName()).is_relative_to(Path(os.environ["HOME"]))


def test_the_theme_directory_is_not_the_one_a_real_launch_uses() -> None:
    """Qt's test mode is the guard that holds on every platform.

    The environment redirects are enough on Linux. Whether Qt's Windows
    lookup reads `APPDATA` at all is not something this suite has checked, so
    the guarantee that does not depend on it is test mode's own corner.
    """
    under_test = theme_menu.user_theme_directory(create=False)
    QStandardPaths.setTestModeEnabled(False)
    try:
        real = theme_menu.user_theme_directory(create=False)
    finally:
        QStandardPaths.setTestModeEnabled(True)

    assert under_test != real
