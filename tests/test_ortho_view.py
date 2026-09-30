"""The top and front views (M5 phase 1): where a channel is drawn, pairs,
bypass, what is on top, and selecting. Marked gui.

The geometry is read through the views' own icons, in pixels, and a pixel
is read back only where an icon is what must be on top.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Pairing,
    Placement,
    Position,
    sides,
)
from immersive.core.selection import Kind
from immersive.ui.spatial.ortho_view import OrthoView
from immersive.ui.spatial.scale import Scale

pytestmark = pytest.mark.gui

W, H = 600, 400


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def document_with(*channels: Channel) -> Document:
    """A document whose project has a stereo and a mono sample, and these
    channels."""
    document = Document()
    project = document.project
    project.media_pool += [
        MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 2, 48_000),
        MediaFile("m-00000002", "/m.wav", "m.wav", 48_000, 1, 48_000),
    ]
    project.channels += channels
    return document


def channel(
    n: int,
    where: Position,
    *,
    stereo: bool = False,
    mode: Pairing = Pairing.POINT,
    colour: str = "#22D3EE",
    **settings: object,
) -> Channel:
    media = "m-00000001" if stereo else "m-00000002"
    return Channel(
        f"c-{n:08x}",
        f"C{n}",
        colour,
        position=where,
        placement=Placement(mode=mode),
        clips=[Clip(f"k-{n:08x}", media, 0, 0, 1000)],
        **settings,  # type: ignore[arg-type]
    )


def views(document: Document, scale: Scale | None = None) -> tuple[OrthoView, ...]:
    scale = scale or Scale()
    made = []
    for plane in ("top", "front"):
        view = OrthoView(document, scale, plane)
        view.resize(W, H)
        made.append(view)
    return tuple(made)


def near(point: QPointF, x: float, y: float) -> bool:
    return abs(point.x() - x) < 1.0 and abs(point.y() - y) < 1.0


# ------------------------------------------------------------- geometry


def test_a_channel_is_drawn_where_its_position_is_in_both_views() -> None:
    """(1, 2, 0): 1 m right of the head and 2 m ahead from above, 1 m right
    at ear level from behind - at a zoom and a pan, within a pixel."""
    scale = Scale()
    scale.zoom_about("top", W, H, 420.0, 130.0, 0.6)
    scale.pan("front", W, H, -25.0, 40.0)
    top, front = views(document_with(channel(1, Position(1.0, 2.0, 0.0))), scale)
    per = scale.per_metre(W, H)

    head = top.point_of(Position())
    [icon] = top.icons()
    assert near(icon.centre, head.x() + per, head.y() - 2 * per)

    head = front.point_of(Position())
    [icon] = front.icons()
    assert near(icon.centre, head.x() + per, head.y()), "at ear level"


def test_height_is_up_in_the_front_view_and_nowhere_in_the_top() -> None:
    top, front = views(document_with(channel(1, Position(0.0, 0.0, 1.5))))
    per = Scale().per_metre(W, H)

    [icon] = top.icons()
    assert near(icon.centre, *_xy(top.point_of(Position())))
    [icon] = front.icons()
    head = front.point_of(Position())
    assert near(icon.centre, head.x(), head.y() - 1.5 * per)


def test_a_pair_is_its_two_sides_and_a_bypassed_channel_nothing() -> None:
    linked = channel(1, Position(-1.0, 1.0, 0.0), stereo=True, mode=Pairing.LINKED)
    free = channel(2, Position(1.0, 2.0, 0.0), stereo=True, mode=Pairing.FREE)
    free.placement.right = Position(2.0, -1.0, 0.5)
    mono = channel(3, Position(0.0, 3.0, 0.0), mode=Pairing.LINKED)
    bypassed = channel(4, Position(0.0, 1.0, 0.0), hrtf_bypass=True)
    top, _ = views(document_with(linked, free, mono, bypassed))

    drawn = [(icon.channel.id, icon.side) for icon in top.icons()]
    assert drawn == [
        (linked.id, 0),
        (linked.id, 1),
        (free.id, 0),
        (free.id, 1),
        (mono.id, -1),
    ], "a mono channel not asking for two is one point; bypassed, none"
    left, right = sides(linked)
    icons = top.icons()
    assert near(icons[0].centre, *_xy(top.point_of(left)))
    assert near(icons[1].centre, *_xy(top.point_of(right)))
    assert right.x == 1.0, "mirrored in X about the listener"


# ------------------------------------------------------------- drawing


def test_an_icon_is_painted_in_its_channels_colour_where_it_is() -> None:
    top, front = views(
        document_with(channel(1, Position(1.0, 2.0, 0.5), colour="#F472B6"))
    )
    for view in (top, front):
        [icon] = view.icons()
        assert pixel(view, icon.centre) == QColor("#F472B6")


def test_the_selected_channel_is_drawn_over_the_others() -> None:
    """Two icons in one place: whichever is selected is the one seen, and
    the one a click there takes."""
    first = channel(1, Position(1.0, 1.0, 0.0), colour="#F472B6")
    second = channel(2, Position(1.0, 1.0, 0.0), colour="#34D399")
    document = document_with(first, second)
    top, _ = views(document)
    at = top.icons()[0].centre

    assert pixel(top, at) == QColor("#34D399"), "the later one, unselected"
    document.selection.select(Kind.CHANNELS, [first])
    assert pixel(top, at) == QColor("#F472B6")
    assert top.icon_at(at).channel is first  # type: ignore[union-attr]


# ------------------------------------------------------------- selecting


def test_a_click_selects_ctrl_click_toggles_and_nothing_clears() -> None:
    first = channel(1, Position(-1.5, 1.0, 0.0))
    second = channel(2, Position(1.5, 1.0, 0.0))
    document = document_with(first, second)
    top, _ = views(document)
    one, two = (icon.centre.toPoint() for icon in top.icons())

    QTest.mouseClick(top, Qt.MouseButton.LeftButton, pos=one)
    assert document.selection.channels() == [first]
    QTest.mouseClick(
        top, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, two
    )
    assert document.selection.channels() == [first, second]
    QTest.mouseClick(
        top, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, one
    )
    assert document.selection.channels() == [second]
    QTest.mouseClick(top, Qt.MouseButton.LeftButton, pos=top.rect().topLeft())
    assert document.selection.kind is None


def pixel(view: OrthoView, at: QPointF) -> QColor:
    return view.grab().toImage().pixelColor(at.toPoint())


def _xy(point: QPointF) -> tuple[float, float]:
    return point.x(), point.y()
