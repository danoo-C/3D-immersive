"""The top and front views (M5 phase 1): where a channel is drawn, pairs,
bypass, what is on top, and selecting. Marked gui.

The geometry is read through the views' own icons, in pixels, and a pixel
is read back only where an icon is what must be on top.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import SetAttribute
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
from immersive.ui import theme, theme_io
from immersive.ui.main_window import MainWindow
from immersive.ui.spatial import look
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


# ------------------------------------------------------ what an icon says


def blend(colour: str, opacity: float) -> QColor:
    """`colour` painted at `opacity` over the views' background."""
    over, under = QColor(colour), QColor(theme.group_color("spatial", "background"))
    return QColor(
        *(
            round(opacity * a + (1 - opacity) * b)
            for a, b in zip(_rgb(over), _rgb(under), strict=True)
        )
    )


def close(one: QColor, other: QColor) -> bool:
    return all(abs(a - b) <= 2 for a, b in zip(_rgb(one), _rgb(other), strict=True))


def test_a_nearer_icon_is_drawn_larger_in_both_views() -> None:
    """By its distance in three dimensions, the same in either view."""
    near, far = Position(-1.0, 0.5, 0.5), Position(1.5, 3.0, 2.5)
    top, front = views(
        document_with(
            channel(1, near, colour="#F472B6"), channel(2, far, colour="#34D399")
        )
    )
    for view in (top, front):
        big, small = view.icons()
        assert big.radius == look.radius(near) > small.radius == look.radius(far)
        inside_big = big.centre + QPointF(big.radius - 1.5, 0)
        beyond_small = small.centre + QPointF(big.radius - 1.5, 0)
        assert pixel(view, inside_big) == QColor("#F472B6")
        assert pixel(view, beyond_small) != QColor("#34D399")


def test_a_quieter_icon_is_fainter() -> None:
    loud = channel(1, Position(-1.5, 1.5, 0.5), colour="#F472B6")
    quiet = channel(2, Position(1.5, 1.5, 0.5), colour="#F472B6", gain_db=-20.0)
    for view in views(document_with(loud, quiet)):
        at_loud, at_quiet = (icon.centre for icon in view.icons())
        assert pixel(view, at_loud) == QColor("#F472B6")
        assert close(pixel(view, at_quiet), blend("#F472B6", 0.55))


def test_a_muted_icon_and_one_silenced_by_a_solo_are_at_a_quarter() -> None:
    muted = channel(1, Position(-1.5, 1.5, 0.5), colour="#F472B6", mute=True)
    top, front = views(document_with(muted))
    for view in (top, front):
        [icon] = view.icons()
        assert close(pixel(view, icon.centre), blend("#F472B6", 0.25))

    soloed = channel(2, Position(1.5, 1.5, 0.5), colour="#34D399", solo=True)
    silenced = channel(3, Position(-1.5, 1.5, 0.5), colour="#F472B6", gain_db=6.0)
    top, _ = views(document_with(soloed, silenced))
    at_soloed, at_silenced = (icon.centre for icon in top.icons())
    assert pixel(top, at_soloed) == QColor("#34D399")
    assert close(pixel(top, at_silenced), blend("#F472B6", 0.25))


def test_a_pairs_line_is_as_faint_as_its_icons() -> None:
    """In the front view, clear of the lines of height: the middle of a
    muted pair's line is nearer the background than a heard pair's."""
    heard = channel(1, Position(-1.0, 1.0, 1.5), stereo=True, mode=Pairing.LINKED)
    muted = channel(
        2, Position(-1.0, 1.0, -1.5), stereo=True, mode=Pairing.LINKED, mute=True
    )
    _, front = views(document_with(heard, muted))
    background = pixel(front, QPointF(W - 3, 3))

    def middle(left: int) -> QColor:
        icons = front.icons()
        return pixel(front, (icons[left].centre + icons[left + 1].centre) / 2)

    assert _apart(middle(2), background) < 0.5 * _apart(middle(0), background)


def test_the_selected_ring_is_not_faint_with_its_channel() -> None:
    """It is the selection's: the same around a muted icon as a heard one."""
    heard = channel(1, Position(-1.5, 1.0, 0.5))
    muted = channel(2, Position(1.5, 1.0, 0.5), mute=True)
    document = document_with(heard, muted)
    document.selection.select(Kind.CHANNELS, [heard, muted])
    _, front = views(document)

    ring = QColor(theme.group_color("spatial", "selected"))

    def on_ring(icon: int) -> QColor:
        """Above the icon, across the ring's width, the pixel it covers
        most: one pixel alone may be half covered, by where the radius
        falls."""
        [*_, at] = [i for i in front.icons() if i.channel is (heard, muted)[icon]]
        grab = front.grab().toImage()
        across = [
            grab.pixelColor((at.centre + QPointF(0, -(at.radius + gap))).toPoint())
            for gap in (1.5, 2.5, 3.5, 4.5)
        ]
        return min(across, key=lambda colour: _apart(colour, ring))

    assert on_ring(0) == on_ring(1)
    assert _apart(on_ring(1), ring) < 30


def test_a_soloed_icon_glows_beyond_its_edge() -> None:
    soloed = channel(1, Position(1.5, 1.5, 0.5), colour="#34D399", solo=True)
    plain = channel(2, Position(-1.5, 1.5, 0.5), colour="#34D399", solo=True)
    document = document_with(soloed, plain)
    top, _ = views(document)
    background = pixel(top, QPointF(2, 2))

    def beyond(icon_index: int) -> QColor:
        icon = top.icons()[icon_index]
        return pixel(top, icon.centre + QPointF(icon.radius + 3, 0))

    assert beyond(0) != background and beyond(1) != background
    document.push(SetAttribute(plain, "solo", False))
    assert beyond(0) != background, "still soloed"
    assert beyond(1) == background, "no glow"


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


# ------------------------------------------------------------- the window


def shortcut(window: MainWindow, key: str) -> None:
    """Trigger the window's action bound to `key`, as pressing it would."""
    [action] = [
        a for a in window.findChildren(QAction) if a.shortcut().toString() == key
    ]
    assert action.isEnabled(), f"{key} does something now"
    action.trigger()


def test_keys_1_and_2_focus_the_views_and_3_shows_the_3d_tab() -> None:
    window = MainWindow()
    window.show()
    window.activateWindow()
    top, front = window.spatial_views()
    [workspace] = window.findChildren(QTabWidget)

    shortcut(window, "3")
    assert workspace.currentIndex() == 1
    shortcut(window, "2")
    assert workspace.currentIndex() == 0
    assert window.focusWidget() is front, "the window's own: offscreen none is active"
    shortcut(window, "1")
    assert window.focusWidget() is top


def test_an_edit_repaints_the_views() -> None:
    """A position typed anywhere - here an edit pushed, as the pane pushes
    one - is drawn: the views are asked to repaint, not left showing where
    the source was."""
    window = MainWindow()
    window.show()
    document = window.document()
    document.project.media_pool += document_with().project.media_pool
    placed = channel(1, Position(1.0, 1.0, 0.0))
    document.project.channels.append(placed)
    QApplication.processEvents()
    top, front = window.spatial_views()
    painted = {top: 0, front: 0}

    class Counter(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.Paint and watched in painted:
                painted[watched] += 1
            return False

    counter = Counter()
    for view in (top, front):
        view.installEventFilter(counter)
    document.push(SetAttribute(placed, "position", Position(-2.0, 0.5, 1.0)))
    QApplication.processEvents()

    assert painted[top] >= 1 and painted[front] >= 1
    [icon] = top.icons()
    assert near(icon.centre, *_xy(top.point_of(Position(-2.0, 0.5, 1.0))))


def test_a_theme_switch_changes_what_the_views_paint() -> None:
    top, _ = views(document_with())
    corner = QPointF(2, 2)
    before = pixel(top, corner)
    original = theme.active()
    try:
        theme.use(
            theme.Theme(
                name="Green",
                tokens={**theme_io.builtin().tokens, "surface.panel": "#00FF00"},
                channels=theme_io.builtin().channels,
                groups=theme_io.builtin().groups,
            )
        )
        top.retheme()
        assert pixel(top, corner) == QColor("#00FF00") != before
    finally:
        theme.use(original)


def pixel(view: QWidget, at: QPointF) -> QColor:
    return view.grab().toImage().pixelColor(at.toPoint())


def _xy(point: QPointF) -> tuple[float, float]:
    return point.x(), point.y()


def _rgb(colour: QColor) -> tuple[int, int, int]:
    return colour.red(), colour.green(), colour.blue()


def _apart(one: QColor, other: QColor) -> int:
    return sum(abs(a - b) for a, b in zip(_rgb(one), _rgb(other), strict=True))
