"""Dragging a source in the top and front views (M5 phase 2, D-144, D-145):
the axes a drag sets, one edit at its release, Esc, and the other view
following. Marked gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.model import Pairing, Position, mirror, sides
from immersive.ui.spatial.ortho_view import OrthoView
from immersive.ui.spatial.placing import Placing
from immersive.ui.spatial.scale import Scale
from test_ortho_view import H, W, channel, document_with

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def views(document: Document) -> tuple[OrthoView, OrthoView]:
    """Both views, on one scale and one `Placing`, as the window has them."""
    scale, placing = Scale(), Placing()
    top = OrthoView(document, scale, "top", placing)
    front = OrthoView(document, scale, "front", placing)
    for view in (top, front):
        view.resize(W, H)
    return top, front


def press(view: OrthoView, at: QPointF) -> QPoint:
    point = at.toPoint()
    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=point)
    return point


def move(view: OrthoView, to: QPoint) -> None:
    QTest.mouseMove(view, to)


def release(view: OrthoView, at: QPoint) -> None:
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=at)


def per_metre(view: OrthoView) -> float:
    return Scale().per_metre(view.width(), view.height())


def test_a_drag_in_the_top_view_sets_x_and_y_by_the_metres_moved() -> None:
    placed = channel(1, Position(1.0, 1.0, 0.5))
    document = document_with(placed)
    top, _ = views(document)
    per = per_metre(top)
    [icon] = top.icons()

    # Pressed 3 px off the icon's centre: the drag keeps that offset.
    start = press(top, icon.centre + QPointF(3, -2))
    move(top, start + QPoint(20, 0))
    to = start + QPoint(50, -25)
    move(top, to)
    release(top, to)

    assert placed.position.x == pytest.approx(1.0 + 50 / per, abs=1e-6)
    assert placed.position.y == pytest.approx(1.0 + 25 / per, abs=1e-6)
    assert placed.position.z == 0.5, "height is the front view's"


def test_a_drag_in_the_front_view_sets_x_and_z_and_leaves_y() -> None:
    placed = channel(1, Position(-1.0, 2.0, 0.0))
    document = document_with(placed)
    _, front = views(document)
    per = per_metre(front)
    [icon] = front.icons()

    start = press(front, icon.centre)
    to = start + QPoint(-30, -40)
    move(front, to)
    release(front, to)

    assert placed.position.x == pytest.approx(-1.0 - 30 / per, abs=1e-6)
    assert placed.position.z == pytest.approx(40 / per, abs=1e-6)
    assert placed.position.y == 2.0


def test_the_release_is_one_edit_and_one_undo() -> None:
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document = document_with(placed)
    top, _ = views(document)
    [icon] = top.icons()

    start = press(top, icon.centre)
    for step in range(1, 12):
        move(top, start + QPoint(step * 5, 0))
    assert placed.position == Position(0.0, 1.0, 0.0), "no edit during the drag"
    assert not document.can_undo
    release(top, start + QPoint(55, 0))

    assert placed.position.x > 0.0
    assert document.undo()
    assert placed.position == Position(0.0, 1.0, 0.0)
    assert not document.can_undo, "one step"


def test_the_other_view_shows_the_drag_before_the_release() -> None:
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document = document_with(placed)
    top, front = views(document)
    [before] = front.icons()
    [icon] = top.icons()

    start = press(top, icon.centre)
    move(top, start + QPoint(60, 0))

    [during] = front.icons()
    assert during.centre.x() == pytest.approx(before.centre.x() + 60, abs=1.0)
    assert placed.position.x == 0.0


def test_esc_drops_the_drag_and_makes_no_edit() -> None:
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document = document_with(placed)
    top, front = views(document)
    [icon] = top.icons()

    start = press(top, icon.centre)
    move(top, start + QPoint(40, 40))
    QTest.keyClick(top, Qt.Key.Key_Escape)
    release(top, start + QPoint(40, 40))

    assert placed.position == Position(0.0, 1.0, 0.0)
    assert not document.can_undo
    [back] = front.icons()
    assert back.centre == front.point_of(Position(0.0, 1.0, 0.0))


def test_a_click_that_does_not_move_only_selects() -> None:
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document = document_with(placed)
    top, _ = views(document)
    [icon] = top.icons()

    at = press(top, icon.centre)
    move(top, at + QPoint(1, 1))
    release(top, at + QPoint(1, 1))

    assert document.selection.channels() == [placed]
    assert not document.can_undo


def test_a_linked_pair_dragged_by_its_right_leads_with_its_right() -> None:
    """D-145: the right under the pointer, the left in its mirror, and the
    edit storing that left."""
    placed = channel(1, Position(-1.0, 1.0, 0.0), stereo=True, mode=Pairing.LINKED)
    document = document_with(placed)
    top, _ = views(document)
    per = per_metre(top)
    _, right_icon = top.icons()
    assert right_icon.side == 1

    start = press(top, right_icon.centre)
    to = start + QPoint(40, -20)
    move(top, to)
    release(top, to)

    _, right = sides(placed)
    assert right.x == pytest.approx(1.0 + 40 / per, abs=1e-6)
    assert right.y == pytest.approx(1.0 + 20 / per, abs=1e-6)
    assert placed.position == mirror(
        right, placed.placement.pivot, placed.placement.mirrored
    )
