"""The bypass strip (M5 phase 3, D-36, D-147): a chip for each bypassed
channel, wrapped, hidden when none; a click selecting and ⊘ un-bypassing.
Marked gui."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import SetAttribute
from immersive.core.model import Channel, Position
from immersive.ui.main_window import MainWindow
from immersive.ui.spatial.bypass_strip import BypassStrip
from immersive.ui.spatial.ortho_view import OrthoView
from immersive.ui.spatial.scale import Scale
from test_ortho_view import channel, document_with

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def strip_for(document: Document, width: int = 500) -> BypassStrip:
    strip = BypassStrip(document)
    strip.resize(width, strip.height())
    return strip


def bypassed(n: int, name: str = "") -> Channel:
    made = channel(n, Position(1.0, float(n), 0.0), hrtf_bypass=True)
    made.name = name or made.name
    return made


def click(strip: BypassStrip, at: QPointF, ctrl: bool = False) -> None:
    modifiers = (
        Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    )
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton, modifiers, at.toPoint())


def on_name(strip: BypassStrip, of: Channel) -> QPointF:
    [chip] = [chip for chip in strip.chips() if chip.channel is of]
    return QPointF(chip.rect.left() + 20, chip.rect.center().y())


def test_a_chip_for_each_bypassed_channel_and_none_other() -> None:
    first, placed, last = bypassed(1), channel(2, Position(0.0, 1.0, 0.0)), bypassed(3)
    strip = strip_for(document_with(first, placed, last))

    assert [chip.channel for chip in strip.chips()] == [first, last]
    assert not strip.isHidden()


def test_the_strip_is_hidden_when_none_is_bypassed_and_follows_edits() -> None:
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document = document_with(placed)
    strip = strip_for(document)
    assert strip.isHidden()
    assert strip.height() == 0, "no room taken"

    document.push(SetAttribute(placed, "hrtf_bypass", True))
    assert not strip.isHidden()
    assert [chip.channel for chip in strip.chips()] == [placed]
    document.undo()
    assert strip.isHidden()


def test_every_chip_is_inside_the_strip_when_they_wrap() -> None:
    many = [bypassed(n, f"Backing vocal {n}") for n in range(1, 13)]
    strip = strip_for(document_with(*many), width=360)
    chips = strip.chips()

    assert len({chip.rect.top() for chip in chips}) > 1, "more than one row"
    for chip in chips:
        assert strip.rect().toRectF().contains(chip.rect), chip.channel.name
    for one, other in pairwise(chips):
        assert not one.rect.intersects(other.rect)


def test_a_long_name_is_cut_short_and_its_chip_kept_narrow() -> None:
    strip = strip_for(document_with(bypassed(1, "A very long name " * 8)))
    [chip] = strip.chips()
    assert chip.rect.width() < 220


def test_a_click_on_a_chip_selects_and_ctrl_click_toggles() -> None:
    first, second = bypassed(1), bypassed(2)
    document = document_with(first, second)
    strip = strip_for(document)

    click(strip, on_name(strip, first))
    assert document.selection.channels() == [first]
    click(strip, on_name(strip, second), ctrl=True)
    assert document.selection.channels() == [first, second]
    click(strip, on_name(strip, first), ctrl=True)
    assert document.selection.channels() == [second]
    assert first.hrtf_bypass and second.hrtf_bypass


def test_the_glyph_un_bypasses_in_one_edit_and_the_icon_is_back() -> None:
    kept = Position(-2.0, 1.5, 0.5)
    back = channel(1, kept, hrtf_bypass=True)
    document = document_with(back, bypassed(2))
    strip = strip_for(document)
    top = OrthoView(document, Scale(), "top")
    top.resize(600, 400)
    assert top.icons() == []

    [chip, _] = strip.chips()
    click(strip, chip.glyph.center())

    assert not back.hrtf_bypass
    assert document.selection.kind is None, "⊘ un-bypasses, and selects nothing"
    [icon] = top.icons()
    assert icon.channel is back and icon.centre == top.point_of(kept)
    assert [chip.channel.id for chip in strip.chips()] == ["c-00000002"]
    document.undo()
    assert [chip.channel.id for chip in strip.chips()] == [back.id, "c-00000002"]
    assert not document.can_undo, "one edit"


def test_in_the_window_the_strip_is_under_the_top_view_and_follows_edits() -> None:
    """A bypass made elsewhere - here an edit pushed, as a header's B button
    pushes one - shows the strip under the top view, which gives it the
    room; undone, the top view has it back."""
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    document = window.document()
    document.project.media_pool += document_with().project.media_pool
    placed = channel(1, Position(0.0, 1.0, 0.0))
    document.project.channels.append(placed)
    QApplication.processEvents()
    top, _ = window.spatial_views()
    strip = window.bypass_strip()
    whole = top.height()
    assert strip.isHidden()

    document.push(SetAttribute(placed, "hrtf_bypass", True))
    QApplication.processEvents()
    assert strip.isVisible() and strip.height() > 0
    assert strip.geometry().top() == top.geometry().bottom() + 1
    assert strip.width() == top.width()
    assert top.height() == whole - strip.height()
    assert top.icons() == []

    document.undo()
    QApplication.processEvents()
    assert strip.isHidden() and top.height() == whole
