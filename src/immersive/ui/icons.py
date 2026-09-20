"""SVG icons, tinted with a palette colour when they are loaded.

Qt's SVG renderer does not resolve `currentColor`, so the token is substituted
textually before rendering. That indirection is the point: an icon follows the
palette instead of being baked to one colour at design time, which is what lets
a theme (M9) recolour the whole set without shipping a second copy of it.

Resources are reached through `importlib.resources`, never `__file__` (D-30).
"""

from __future__ import annotations

from functools import cache
from importlib import resources

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from immersive.ui import theme

_PACKAGE = "immersive.assets.icons"

#: The token every icon uses for its ink. Substituted, never rendered as-is.
_INK = "currentColor"

#: 1x and 2x, so the toolbar stays crisp when the window moves to a hidpi
#: screen. Qt picks the nearest and scales down, which is the cheap direction.
_SIZES = (16, 32)

#: The window and taskbar icon is asked for at sizes no toolbar ever needs -
#: alt-tab and dock previews go well past 32 - so it is rendered from its own
#: ladder rather than widening _SIZES and paying for a 256 px copy of every
#: transport glyph that will never be drawn at that size.
_APP_SIZES = (16, 32, 48, 64, 128, 256)


@cache
def _source(name: str) -> str:
    """The raw SVG text for `name`, read once per process."""
    return resources.files(_PACKAGE).joinpath(f"{name}.svg").read_text(encoding="utf-8")


def _render(name: str, colour: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(_source(name).replace(_INK, colour).encode("utf-8"))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


@cache
def icon(name: str, colour: str | None = None, disabled: str | None = None) -> QIcon:
    """A themed `QIcon` carrying both a normal and a disabled rendering.

    Giving Qt the disabled pixmap explicitly beats letting it grey the normal
    one out: its default is a washed-out blend that reads as a rendering fault
    rather than as a deliberate state.
    """
    result = QIcon()
    for size in _SIZES:
        result.addPixmap(
            _render(name, colour or theme.TEXT_HI, size), QIcon.Mode.Normal
        )
        result.addPixmap(
            _render(name, disabled or theme.TEXT_DIM, size), QIcon.Mode.Disabled
        )
    return result


@cache
def app_icon() -> QIcon:
    """The application icon: a source placed on a ring around the listener.

    Accent-coloured rather than `text-hi`, because this one is not a control
    on a toolbar - it is the application's mark in a taskbar and an alt-tab
    list, where it has to carry identity rather than blend into a panel.
    """
    result = QIcon()
    for size in _APP_SIZES:
        result.addPixmap(_render("app", theme.ACCENT, size), QIcon.Mode.Normal)
    return result


def available() -> tuple[str, ...]:
    """Every icon name that ships with the package, sorted."""
    names = (
        path.name[: -len(".svg")]
        for path in resources.files(_PACKAGE).iterdir()
        if path.name.endswith(".svg")
    )
    return tuple(sorted(names))
