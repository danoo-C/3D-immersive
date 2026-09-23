"""Where themes are found, and what the application remembers.

⚠️ Every test here runs under `QStandardPaths.setTestModeEnabled(True)`.
Without it `user_theme_directory()` creates a directory in the developer's
real config and `QSettings` writes their real settings — a test run that
changes the machine it ran on, and a persistence test that can pass because
of yesterday's run rather than because of today's code.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from immersive.app import build_application
from immersive.ui import theme_io, theme_menu

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    """A QApplication, and settings emptied between tests.

    Redirecting the home directory is `conftest.py`'s, autouse for every
    test in the suite - building a `MainWindow` is enough to reach for it,
    so confining the guard to this file would not have been a guard.
    """
    build_application([])
    QSettings().clear()
    yield
    QSettings().clear()


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
