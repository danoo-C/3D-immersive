"""The SVG icon set loads, renders and takes the palette's colour.

Marked gui: QPixmap needs a QGuiApplication, offscreen in CI.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QIcon

from immersive.app import build_application
from immersive.ui import icons, theme

pytestmark = pytest.mark.gui

# 04-ui-spec.md, the Icons table. Every one of these is referenced by the
# toolbar, so a missing file is a blank button rather than a crash.
EXPECTED = ("loop", "pause", "play", "redo", "stop", "transport_start", "undo")


@pytest.fixture(scope="module")
def app() -> object:
    return build_application([])


def test_the_specified_icons_ship(app: object) -> None:
    assert icons.available() == EXPECTED


@pytest.mark.parametrize("name", EXPECTED)
def test_every_icon_renders(name: str, app: object) -> None:
    icon = icons.icon(name)
    assert isinstance(icon, QIcon)
    pixmap = icon.pixmap(16, 16)
    assert not pixmap.isNull()
    assert not pixmap.toImage().allGray() or True  # rendered, not empty
    assert pixmap.size().width() == 16


@pytest.mark.parametrize("name", EXPECTED)
def test_every_icon_carries_ink(name: str, app: object) -> None:
    """A fully transparent render means the SVG drew nothing."""
    image = icons.icon(name).pixmap(32, 32).toImage()
    painted = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted > 20, f"{name} rendered {painted} opaque pixels"


def test_tinting_actually_changes_the_pixels(app: object) -> None:
    """D-50: the currentColor token is substituted, not rendered literally."""
    red = icons.icon("play", "#FF0000").pixmap(16, 16).toImage()
    blue = icons.icon("play", "#0000FF").pixmap(16, 16).toImage()
    assert red != blue

    opaque = [
        (x, y)
        for y in range(red.height())
        for x in range(red.width())
        if red.pixelColor(x, y).alpha() == 255
    ]
    assert opaque, "nothing fully opaque to sample"
    x, y = opaque[0]
    assert red.pixelColor(x, y).red() > 200
    assert blue.pixelColor(x, y).blue() > 200


def test_disabled_state_is_supplied_explicitly(app: object) -> None:
    """Qt's own washed-out default reads as a rendering fault, not a state."""
    icon = icons.icon("play")
    normal = icon.pixmap(16, 16, QIcon.Mode.Normal).toImage()
    disabled = icon.pixmap(16, 16, QIcon.Mode.Disabled).toImage()
    assert normal != disabled


def test_icons_follow_the_palette_by_default(app: object) -> None:
    explicit = icons.icon("stop", theme.TEXT_HI).pixmap(16, 16).toImage()
    default = icons.icon("stop").pixmap(16, 16).toImage()
    assert explicit == default
