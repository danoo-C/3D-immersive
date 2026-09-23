"""Where user themes live, and what the application remembers choosing.

The `View > Theme` menu is built here too (F-48). Split from `theme_io`
because every question in this file needs Qt to answer - where a platform
puts application config, what the last session chose - and `theme_io` stays
importable without a `QApplication` so the `.3dimtheme` format is testable
headless (D-81 makes the same argument for the notice model).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

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
    """Every theme file the user has put in their theme directory."""
    return theme_io.discover(user_theme_directory())


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
