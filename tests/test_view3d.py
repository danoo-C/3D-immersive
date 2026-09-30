"""The 3D view (M5 phase 4, D-148): where the projection puts a source and
its height, the ground's fit, what covers what, the icons' rules, and no
input. Marked gui."""

from __future__ import annotations

import math
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import SetAttribute
from immersive.core.model import Pairing, Position, sides
from immersive.core.selection import Kind
from immersive.ui import theme
from immersive.ui.main_window import MainWindow
from immersive.ui.spatial import look
from immersive.ui.spatial.view3d import View3D
from test_ortho_view import channel, document_with, near, pixel, shortcut

pytestmark = pytest.mark.gui

W, H = 800, 500


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def view_of(document: Document) -> View3D:
    view = View3D(document)
    view.resize(W, H)
    return view


def background() -> QColor:
    return QColor(theme.group_color("spatial", "background"))


# ------------------------------------------------------------- geometry


def test_a_source_is_drawn_where_the_projection_puts_it_above_its_foot() -> None:
    """(1, 2, 0.5): a metre right and two ahead, half a metre up; its drop
    line reaches the ground straight below it, half a metre down."""
    view = view_of(document_with(channel(1, Position(1.0, 2.0, 0.5), colour="#F472B6")))
    per = view.per_metre()
    cos = math.cos(math.radians(30))

    assert near(view.point_of(Position()), W / 2, H / 2), "the head at the centre"
    [icon] = view.icons()
    assert near(icon.centre, W / 2 + per * cos * (1 - 2), H / 2 - per * (1.5 + 0.5))
    assert pixel(view, icon.centre) == QColor("#F472B6")

    foot = view.point_of(Position(1.0, 2.0, 0.0))
    assert foot.x() == pytest.approx(icon.centre.x())
    assert foot.y() - icon.centre.y() == pytest.approx(0.5 * per)
    assert pixel(view, foot) != background(), "the drop line's foot"
    assert pixel(view, (foot + icon.centre) / 2 + QPointF(0.0, 3.0)) != background()


def test_the_ground_steps_and_holds_as_a_source_moves() -> None:
    placed = channel(1, Position(0.0, 1.5, 0.0))
    document = document_with(placed)
    view = view_of(document)
    assert view.half_size() == 2.0

    document.push(SetAttribute(placed, "position", Position(0.0, 2.5, 0.0)))
    assert view.half_size() == 4.0
    scale = view.per_metre()
    document.push(SetAttribute(placed, "position", Position(0.0, 3.9, 0.0)))
    assert view.half_size() == 4.0 and view.per_metre() == scale, "held"
    document.push(SetAttribute(placed, "position", Position(0.0, 0.0, 5.0)))
    assert view.half_size() == 8.0, "height counts"


def test_the_ground_and_every_source_fit_in_the_view() -> None:
    far = channel(1, Position(4.0, 4.0, 4.0))
    low = channel(2, Position(-4.0, -4.0, -4.0))
    view = view_of(document_with(far, low))
    rect = view.rect().toRectF()
    half = view.half_size()

    for x in (-half, half):
        for y in (-half, half):
            assert rect.contains(view.point_of(Position(x, y, 0.0)))
    for icon in view.icons():
        assert rect.contains(icon.centre), icon.channel.name


# --------------------------------------------------------- what covers what


def test_a_source_in_line_is_covered_by_the_one_nearer_the_camera() -> None:
    """Two sources the projection puts in one place: the one nearer the
    camera is seen, though it is smaller and first in the channel order."""
    behind = Position(1.2, 0.2, -0.1)
    ahead = Position(behind.x - 3, behind.y - 3, behind.z + 3)
    for order in ((0, 1), (1, 0)):
        made = [
            channel(1, ahead, colour="#F472B6"),
            channel(2, behind, colour="#34D399"),
        ]
        view = view_of(document_with(*(made[n] for n in order)))
        first, second = view.icons()
        assert near(first.centre, second.centre.x(), second.centre.y())
        assert first.radius > second.radius, "the farther is the larger"
        assert pixel(view, first.centre) == QColor("#F472B6")


def test_the_head_covers_a_source_behind_it_and_not_one_before_it() -> None:
    head_fill = QColor(theme.group_color("spatial", "head.fill"))
    before = view_of(
        document_with(channel(1, Position(-0.5, -0.5, 0.5), colour="#F472B6"))
    )
    assert pixel(before, before.point_of(Position())) == QColor("#F472B6")

    behind = view_of(
        document_with(channel(1, Position(0.5, 0.5, -0.5), colour="#F472B6"))
    )
    assert pixel(behind, behind.point_of(Position())) == head_fill


# ------------------------------------------------------------- the icons


def test_icons_are_drawn_by_the_ortho_views_rules() -> None:
    """A pair is its two sides, a bypassed channel nothing, and each icon's
    radius and opacity are phase 3's (D-146)."""
    pair = channel(1, Position(-1.0, 2.0, 0.5), stereo=True, mode=Pairing.LINKED)
    point = channel(2, Position(2.0, -1.0, 1.0), gain_db=-20.0, mute=True)
    bypassed = channel(3, Position(0.0, 1.0, 0.0), hrtf_bypass=True)
    view = view_of(document_with(pair, point, bypassed))

    drawn = {(icon.channel.id, icon.side): icon for icon in view.icons()}
    assert set(drawn) == {(pair.id, 0), (pair.id, 1), (point.id, -1)}
    left, right = sides(pair)
    for key, where in (((pair.id, 0), left), ((pair.id, 1), right)):
        assert drawn[key].radius == look.radius(where)
        assert near(drawn[key].centre, *_xy(view.point_of(where)))
    assert drawn[(point.id, -1)].opacity == look.opacity(-20.0, heard=False)


# ------------------------------------------------------------- no input


def test_a_press_a_drag_and_a_scroll_change_nothing() -> None:
    placed = channel(1, Position(1.0, 1.0, 0.0))
    document = document_with(placed)
    document.selection.select(Kind.CHANNELS, [placed])
    view = view_of(document)
    view.show()
    before = view.grab().toImage()
    [icon] = view.icons()
    at = icon.centre.toPoint()

    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=at)
    QTest.mouseMove(view, at + QPoint(60, 40))
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=at + QPoint(60, 40))
    QTest.mouseDClick(view, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    QTest.mouseClick(view, Qt.MouseButton.MiddleButton, pos=at)
    wheel = QWheelEvent(
        QPointF(at),
        view.mapToGlobal(QPointF(at)),
        QPoint(),
        QPoint(0, 240),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view, wheel)

    assert document.selection.channels() == [placed]
    assert placed.position == Position(1.0, 1.0, 0.0) and not document.can_undo
    assert view.grab().toImage() == before
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus


# ------------------------------------------------------------- the window


def test_key_3_shows_it_and_an_edit_repaints_it() -> None:
    window = MainWindow()
    window.show()
    document = window.document()
    document.project.media_pool += document_with().project.media_pool
    placed = channel(1, Position(1.0, 1.0, 0.0))
    document.project.channels.append(placed)
    [workspace] = window.findChildren(QTabWidget)

    shortcut(window, "3")
    QApplication.processEvents()
    view = window.view3d()
    assert workspace.currentWidget() is view
    painted = [0]

    class Counter(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.Paint and watched is view:
                painted[0] += 1
            return False

    counter = Counter()
    view.installEventFilter(counter)
    document.push(SetAttribute(placed, "position", Position(-2.0, 0.5, 1.0)))
    QApplication.processEvents()

    assert painted[0] >= 1
    [icon] = view.icons()
    assert near(icon.centre, *_xy(view.point_of(Position(-2.0, 0.5, 1.0))))


def _xy(point: QPointF) -> tuple[float, float]:
    return point.x(), point.y()
