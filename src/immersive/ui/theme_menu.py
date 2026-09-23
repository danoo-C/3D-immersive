"""Where user themes live, and what the application remembers choosing.

The `View > Theme` menu is built here too (F-48). Split from `theme_io`
because every question in this file needs Qt to answer - where a platform
puts application config, what the last session chose - and `theme_io` stays
importable without a `QApplication` so the `.3dimtheme` format is testable
headless (D-81 makes the same argument for the notice model).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QWidget

from immersive.ui import theme_io

#: Inside the application's config location, so a theme sits beside whatever
#: M8's preferences end up writing rather than in a directory of its own.
THEMES_DIRNAME = "themes"

#: What `QSettings` stores the choice under.
SETTINGS_KEY = "theme/selected"

#: The value meaning "the bundled theme". It has no path, and an empty string
#: would be indistinguishable from a bug that wrote one (D-83).
BUILTIN_SENTINEL = "<builtin>"


def user_theme_directory(*, create: bool = True) -> Path:
    """The platform's place for this application's themes.

    `~/.config/3d immersive/themes` on Linux and the equivalent elsewhere,
    resolved by Qt rather than by assembling a path per platform.

    Created on use rather than at import, which is the difference between an
    application that makes a directory when somebody opens the theme menu and
    one that makes a directory because a test imported a module.
    """
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    directory = Path(base) / THEMES_DIRNAME
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def user_themes() -> list[Path]:
    """Every theme file the user has put in their theme directory.

    Never creates it. Listing a directory is not a reason to make one, and
    `discover` already treats a missing directory as "no user themes" - which
    is the truthful answer on a first run. Creation is `run()`'s, once, on a
    real launch.
    """
    return theme_io.discover(user_theme_directory(create=False))


def remember(path: Path | None) -> None:
    """Persist the choice. `None` means the bundled theme (D-83)."""
    QSettings().setValue(SETTINGS_KEY, BUILTIN_SENTINEL if path is None else str(path))


def remembered() -> Path | None:
    """What the last session chose, or `None` for the bundled theme.

    A stored path is returned whether or not it still exists. Deciding what
    to do about a theme that has gone is the caller's, because the caller is
    the one that can report it - and silently falling back here would be the
    behaviour D-83 exists to prevent.
    """
    stored = QSettings().value(SETTINGS_KEY)
    if not isinstance(stored, str) or stored == BUILTIN_SENTINEL or not stored:
        return None
    return Path(stored)


class ThemeMenu(QMenu):
    """`View > Theme`: the bundled theme, then whatever the user has put in.

    **Repopulated every time it is opened**, which is what F-48's "discovered"
    costs: a `.3dimtheme` dropped into the directory has to appear without a
    restart, and the only moment that can be true without a file watcher is
    the moment somebody asks to see the list. It is one `iterdir` of a
    directory holding a handful of files.

    A file watcher would make it appear a few seconds sooner and would be a
    thread, a debounce and a class of bug, for a directory people edit twice
    a year. Hot-reload is explicitly out of scope for M9.
    """

    def __init__(
        self,
        title: str,
        parent: QWidget | None,
        choose: Callable[[Path | None], None],
    ) -> None:
        super().__init__(title, parent)
        self._choose = choose
        self._current: Path | None = None
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self.aboutToShow.connect(self.repopulate)
        self.repopulate()

    def current(self) -> Path | None:
        """Which theme is ticked. `None` is the bundled one."""
        return self._current

    def set_current(self, path: Path | None) -> None:
        """Tick `path` without choosing it, for restoring a remembered one."""
        self._current = path
        self.repopulate()

    def repopulate(self) -> None:
        """Rebuild from the directory as it is right now."""
        for action in self.actions():
            self._group.removeAction(action)
        self.clear()

        self._entry(theme_io.builtin().name, None)
        found = user_themes()
        if found:
            self.addSeparator()
        for path in found:
            self._entry(path.stem, path)

        if not found:
            missing = QAction("No user themes found", self)
            missing.setEnabled(False)
            missing.setToolTip(
                f"Put a {theme_io.SUFFIX} file in {user_theme_directory(create=False)}"
            )
            self.addAction(missing)

    def _entry(self, label: str, path: Path | None) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(path == self._current)
        action.setToolTip(str(path) if path is not None else "The bundled theme")
        action.triggered.connect(lambda _checked=False, p=path: self._picked(p))
        self._group.addAction(action)
        self.addAction(action)
        return action

    def _picked(self, path: Path | None) -> None:
        self._current = path
        self._choose(path)
