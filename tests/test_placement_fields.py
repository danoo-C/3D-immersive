"""The channel view's Placement section (M4 phase 9; D-132, D-135): where a
channel's sides, its mode, its pivot and its mirrored axes are set. Marked
gui."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from immersive.app import build_application
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Pairing,
    Placement,
    Position,
    new_channel,
    sides,
)
from immersive.core.selection import Kind
from immersive.ui import theme
from immersive.ui.main_window import MainWindow
from immersive.ui.parameters.views import MODES, ChannelView
from immersive.ui.widgets.numeric import MIXED
from test_parameters import stacked, type_into

pytestmark = pytest.mark.gui

STEREO = MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 2, 48_000)
MONO = MediaFile("m-00000002", "/m.wav", "m.wav", 48_000, 1, 48_000)


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def a_window(*media: MediaFile) -> tuple[MainWindow, list[Channel]]:
    """A new channel for each of `media`, holding one clip of it."""
    window = MainWindow()
    document = window.document()
    project = document.project
    document.push(AddMedia(project, [STEREO, MONO]))
    for n, one in enumerate(media):
        channel = new_channel(project, theme.active().channels)
        document.push(AddChannel(project, channel))
        document.push(
            DropClips(project, channel, [Clip(f"k-0000000{n}", one.id, 0, 0, 48_000)])
        )
    window.show()
    QApplication.processEvents()
    return window, list(project.channels)


def view_of(window: MainWindow, *channels: Channel) -> ChannelView:
    window.document().selection.select(Kind.CHANNELS, list(channels))
    view = window.parameters().view()
    assert isinstance(view, ChannelView)
    return view


def shown(view: ChannelView, field: object) -> bool:
    return not field.isHidden()  # type: ignore[attr-defined]


def label(view: ChannelView, field: QWidget) -> str:
    name = view._form.labelForField(field)
    assert isinstance(name, QLabel)
    return name.text()


def test_a_new_stereo_channel_is_a_linked_pair_with_its_pivot_and_mirror() -> None:
    window, [channel] = a_window(STEREO)
    view = view_of(window, channel)
    assert view.mode.currentText() == MODES[Pairing.LINKED] == "Linked"
    assert [label(view, field) for field in view.position] == [
        "Left X",
        "Left Y",
        "Left Z",
    ]
    assert all(shown(view, field) for field in (*view.right, *view.pivot))
    assert shown(view, view._mirror_row) and shown(view, view.mono)
    assert [box.isChecked() for box in view.mirrored] == [True, False, False]


def test_a_mono_channel_is_one_position_until_it_asks_for_two() -> None:
    window, [channel] = a_window(MONO)
    view = view_of(window, channel)
    assert label(view, view.position[0]) == "Position X"
    assert not any(shown(view, field) for field in (*view.right, *view.pivot))
    assert shown(view, view.mono)

    view.mono.click()

    assert channel.placement.mono
    assert label(view, view.position[0]) == "Left X"
    assert all(shown(view, field) for field in view.right)


def test_one_point_hides_the_second_side_and_the_link() -> None:
    window, [channel] = a_window(STEREO)
    view = view_of(window, channel)
    view.mode.activated.emit(list(MODES).index(Pairing.POINT))
    assert channel.placement.mode is Pairing.POINT
    assert label(view, view.position[0]) == "Position X"
    hidden = (*view.right, *view.pivot, view._mirror_row, view.mono)
    assert not any(shown(view, field) for field in hidden)


def test_typing_a_linked_right_side_moves_the_left_through_the_mirror() -> None:
    window, [channel] = a_window(STEREO)
    view = view_of(window, channel)
    count = stacked(window)

    type_into(view.right[0], "1.5")

    assert channel.position.x == -1.5
    assert sides(channel)[1].x == 1.5
    assert stacked(window) == count + 1
    assert view.position[0].text() == "-1.50 m"


def test_each_placement_field_is_one_edit_and_undo_puts_it_back() -> None:
    window, [channel] = a_window(STEREO)
    document = window.document()
    view = view_of(window, channel)
    before = channel.placement
    count = stacked(window)

    type_into(view.pivot[0], "0.5")
    view.mirrored[2].click()
    view.mono.click()
    view.mode.activated.emit(list(MODES).index(Pairing.FREE))
    type_into(view.right[1], "2")

    placement = channel.placement
    assert (placement.mode, placement.pivot, placement.mirrored, placement.mono) == (
        Pairing.FREE,
        Position(0.5, 0.0, 0.0),
        (True, False, True),
        True,
    )
    assert placement.right.y == 2.0
    assert stacked(window) == count + 5
    for _ in range(5):
        document.undo()
    assert channel.placement == before
    assert view.mode.currentText() == "Linked"


def test_several_channels_read_a_dash_where_they_differ_and_take_one_edit() -> None:
    window, channels = a_window(STEREO, STEREO)
    document = window.document()
    document.push(
        SetAttribute(
            channels[1],
            "placement",
            Placement(mode=Pairing.LINKED, pivot=Position(1.0, 0, 0)),
        )
    )
    view = view_of(window, *channels)
    assert view.pivot[0].text() == MIXED and view.pivot[1].text() == "0.00 m"
    count = stacked(window)

    type_into(view.pivot[0], "-0.5")

    assert [c.placement.pivot.x for c in channels] == [-0.5, -0.5]
    assert stacked(window) == count + 1


def test_the_placement_is_greyed_when_every_channel_is_bypassed() -> None:
    window, [channel] = a_window(STEREO)
    view = view_of(window, channel)
    window.document().push(SetAttribute(channel, "hrtf_bypass", True))
    placement = (view.mode, *view.position, *view.right, *view.pivot, *view.mirrored)
    assert not any(widget.isEnabled() for widget in placement)
    assert "not placed" in view.position[0].toolTip()
