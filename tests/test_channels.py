"""Channels in the timeline: headers beside lanes, and scrolling through them.

Marked gui. Built as a panel on its own, not a window.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QAction, QFocusEvent, QImage, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, MoveChannel, RemoveChannel, SetAttribute
from immersive.core.model import Channel, SnapSetting, new_channel
from immersive.core.time import Division
from immersive.ui import theme
from immersive.ui.main_window import MainWindow
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.headers import DRAG_THRESHOLD, SILENCED, ChannelHeader
from immersive.ui.timeline.panel import TimelinePanel
from immersive.ui.timeline.view import LANE_HEIGHT

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def paneled(channels: int = 3, *, height: int = 400) -> TimelinePanel:
    document = Document()
    palette = theme.active().channels
    for _ in range(channels):
        document.push(
            AddChannel(document.project, new_channel(document.project, palette))
        )
    panel = TimelinePanel(document, TimeAxis())
    panel.resize(1000, height)
    panel.show()
    QApplication.processEvents()
    return panel


def document_of(panel: TimelinePanel) -> Document:
    return panel._document


def headers(panel: TimelinePanel) -> list[ChannelHeader]:
    return panel.headers.headers()


def channel(panel: TimelinePanel, index: int) -> Channel:
    return document_of(panel).project.channels[index]


# --------------------------------------------------------------------------- #
# the headers follow the project
# --------------------------------------------------------------------------- #


def test_a_header_for_every_channel_in_the_projects_order() -> None:
    panel = paneled(3)
    names = [header.name.text() for header in headers(panel)]
    assert names == ["Channel 1", "Channel 2", "Channel 3"]
    assert [h.chip.colour() for h in headers(panel)] == [
        c.color for c in document_of(panel).project.channels
    ]


def test_the_headers_follow_a_reorder_a_removal_and_undo() -> None:
    panel = paneled(3)
    document = document_of(panel)

    document.push(MoveChannel(document.project, channel(panel, 0), 2))
    assert [h.name.text() for h in headers(panel)] == [
        "Channel 2",
        "Channel 3",
        "Channel 1",
    ]

    document.push(RemoveChannel(document.project, channel(panel, 1)))
    assert [h.name.text() for h in headers(panel)] == ["Channel 2", "Channel 1"]

    document.undo()
    document.undo()
    assert [h.name.text() for h in headers(panel)] == [
        "Channel 1",
        "Channel 2",
        "Channel 3",
    ]


@pytest.mark.parametrize(
    ("button", "field"), [("mute", "mute"), ("solo", "solo"), ("bypass", "hrtf_bypass")]
)
def test_mute_solo_and_bypass_are_each_one_command_that_undo_follows(
    button: str, field: str
) -> None:
    panel = paneled(2)
    document = document_of(panel)
    before = document.can_undo

    getattr(headers(panel)[1], button).click()

    assert getattr(channel(panel, 1), field) is True
    document.undo()
    assert getattr(channel(panel, 1), field) is False
    assert not getattr(headers(panel)[1], button).isChecked()
    assert document.can_undo == before, "one click, one command"
    document.redo()
    assert getattr(headers(panel)[1], button).isChecked()


def test_a_committed_gain_is_one_command() -> None:
    panel = paneled(1)
    document = document_of(panel)

    headers(panel)[0].gain.committed.emit(-6.0)

    assert channel(panel, 0).gain_db == -6.0
    document.undo()
    assert channel(panel, 0).gain_db == 0.0
    assert headers(panel)[0].gain.text() == "0.0 dB"


def test_a_channel_silenced_by_a_solo_says_so_in_words() -> None:
    panel = paneled(3)
    document = document_of(panel)

    document.push(SetAttribute(channel(panel, 0), "solo", True))
    shown = [not header.silenced.isHidden() for header in headers(panel)]
    assert shown == [False, True, True]
    assert headers(panel)[1].silenced.text() == SILENCED

    # A muted channel is not "silenced": its M says why it is quiet.
    document.push(SetAttribute(channel(panel, 2), "mute", True))
    assert [not h.silenced.isHidden() for h in headers(panel)] == [False, True, False]


def test_bypass_is_shown_by_a_label_and_a_state() -> None:
    panel = paneled(1)
    document_of(panel).push(SetAttribute(channel(panel, 0), "hrtf_bypass", True))

    bypass = headers(panel)[0].bypass
    assert bypass.isChecked()
    assert bypass.text() == "⊘"
    assert "HRTF bypass" in bypass.toolTip()


def test_the_snap_indicator_says_whether_the_channel_overrides() -> None:
    panel = paneled(1)
    snap = headers(panel)[0].snap
    assert snap.text() == "snap"
    assert snap.property("overriding") is False

    document_of(panel).push(
        SetAttribute(
            channel(panel, 0), "snap_override", SnapSetting(division=Division.EIGHTH)
        )
    )

    assert snap.text() == "1/8"
    assert snap.property("overriding") is True


def test_a_gain_being_typed_survives_an_edit_to_another_channel() -> None:
    """Rebuilding the column on every change would throw this away."""
    panel = paneled(2)
    first = headers(panel)[0]
    field = first.gain
    press = QPointF(20, 10)
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            field,
            QMouseEvent(
                kind,
                press,
                field.mapToGlobal(press),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton
                if kind is QEvent.Type.MouseButtonPress
                else Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    QTest.keyClicks(field, "-9")

    document_of(panel).push(SetAttribute(channel(panel, 1), "mute", True))

    assert headers(panel)[0] is first
    assert not field.isReadOnly()
    assert field.text() == "-9"


def test_a_long_name_ends_in_an_ellipsis_and_gives_way() -> None:
    """Found by looking: a long name was cut through a letter, hard against
    the snap indicator, with nothing to say there was more of it."""
    panel = paneled(1)
    long = "A long channel name that will not fit in any header"
    document_of(panel).push(SetAttribute(channel(panel, 0), "name", long))
    document_of(panel).push(
        SetAttribute(
            channel(panel, 0), "snap_override", SnapSetting(division=Division.EIGHTH)
        )
    )
    header = headers(panel)[0]

    assert header.name.geometry().right() < header.snap.geometry().left()
    shown = header.name.shown()
    assert shown.endswith("…") and long.startswith(shown[:-1])
    width = header.name.fontMetrics().horizontalAdvance(shown)
    assert width <= header.name.contentsRect().width()
    assert header.name.text() == long
    assert header.name.toolTip() == long


# --------------------------------------------------------------------------- #
# lanes
# --------------------------------------------------------------------------- #


def lanes(panel: TimelinePanel) -> QImage:
    return panel.view.viewport().grab().toImage()


def test_a_line_runs_under_every_lane() -> None:
    panel = paneled(3)
    panel.set_playhead(10**9)  # drawn over everything, so out of the way
    image = lanes(panel)
    separator = theme.group_color("timeline", "separator").upper()

    def row(y: int) -> set[str]:
        return {image.pixelColor(x, y).name().upper() for x in range(image.width())}

    for lane in (1, 2, 3):
        assert row(lane * LANE_HEIGHT - 1) == {separator}
    assert row(LANE_HEIGHT // 2) != {separator}


# --------------------------------------------------------------------------- #
# scrolling through fifteen channels
# --------------------------------------------------------------------------- #


def wheel(target: object, *, dy: int) -> None:
    widget = target
    at = QPointF(100, 100)
    event = QWheelEvent(
        at,
        widget.mapToGlobal(at),  # type: ignore[attr-defined]
        QPoint(),
        QPoint(0, dy),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)  # type: ignore[arg-type]


def aligned(panel: TimelinePanel) -> bool:
    """Every header level with its own lane, in panel coordinates."""
    scroll = panel.view.verticalScrollBar().value()
    viewport = panel.view.viewport()
    return all(
        header.mapTo(panel, QPoint(0, 0)).y()
        == viewport.mapTo(panel, QPoint(0, index * LANE_HEIGHT - scroll)).y()
        for index, header in enumerate(headers(panel))
    )


def test_fifteen_channels_scroll_with_the_wheel_and_the_headers_follow() -> None:
    panel = paneled(15, height=400)
    bar = panel.view.verticalScrollBar()
    assert bar.maximum() > 0, "fifteen lanes do not fit, so there is somewhere to go"

    wheel(panel.view.viewport(), dy=-240)

    assert bar.value() > 0
    assert aligned(panel)


def test_a_wheel_over_the_headers_scrolls_the_lanes() -> None:
    panel = paneled(15, height=400)

    wheel(panel.headers, dy=-240)

    assert panel.view.verticalScrollBar().value() > 0
    assert aligned(panel)


def test_a_middle_drag_pans_through_the_channels_and_the_headers_follow() -> None:
    panel = paneled(15, height=400)
    viewport = panel.view.viewport()
    start, end = QPointF(300, 300), QPointF(300, 100)
    for kind, point, buttons in (
        (QEvent.Type.MouseButtonPress, start, Qt.MouseButton.MiddleButton),
        (QEvent.Type.MouseMove, end, Qt.MouseButton.MiddleButton),
        (QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                kind,
                point,
                viewport.mapToGlobal(point),
                Qt.MouseButton.NoButton
                if kind is QEvent.Type.MouseMove
                else Qt.MouseButton.MiddleButton,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    assert panel.view.verticalScrollBar().value() == 200
    assert aligned(panel)


def test_the_ruler_starts_where_the_lanes_do() -> None:
    panel = paneled(15, height=400)
    ruler = panel.ruler.mapTo(panel, QPoint(0, 0)).x()
    lanes_left = panel.view.viewport().mapTo(panel, QPoint(0, 0)).x()
    assert ruler == lanes_left


def test_headers_below_the_lanes_are_hidden_under_nothing() -> None:
    """The lanes lose a strip to their horizontal scrollbar; the headers'
    column must lose the same, or the last header hangs below its lane."""
    panel = paneled(15, height=400)
    assert panel.headers._clip.height() == panel.view.viewport().height()


# --------------------------------------------------------------------------- #
# adding and removing
# --------------------------------------------------------------------------- #


def names(panel: TimelinePanel) -> list[str]:
    return [header.name.text() for header in headers(panel)]


def test_the_corner_adds_a_channel_below_the_last_in_one_command() -> None:
    panel = paneled(2)
    document = document_of(panel)

    panel.corner.click()

    assert names(panel) == ["Channel 1", "Channel 2", "Channel 3"]
    assert channel(panel, 2).color == theme.active().channels[2]
    document.undo()
    assert names(panel) == ["Channel 1", "Channel 2"]


def test_edit_add_channel_adds_one() -> None:
    window = MainWindow()
    [add] = [a for a in window.findChildren(QAction) if a.text() == "Add &Channel"]
    assert add.isEnabled() and "M3" not in add.toolTip()

    add.trigger()

    assert [c.name for c in window.document().project.channels] == ["Channel 1"]


def action(menu: QMenu, text: str) -> QAction:
    [found] = [a for a in menu.actions() if a.text() == text]
    return found


def test_removing_a_channel_is_one_command_and_undo_puts_it_back_in_place() -> None:
    panel = paneled(3)

    action(headers(panel)[1].context_menu(), "Remove Channel").trigger()

    assert names(panel) == ["Channel 1", "Channel 3"]
    document_of(panel).undo()
    assert names(panel) == ["Channel 1", "Channel 2", "Channel 3"]


# --------------------------------------------------------------------------- #
# renaming
# --------------------------------------------------------------------------- #


def test_a_double_click_on_the_name_opens_it_with_all_of_it_selected() -> None:
    panel = paneled(1)
    header = headers(panel)[0]
    point = QPointF(5, 5)
    QApplication.sendEvent(
        header.name,
        QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            point,
            header.name.mapToGlobal(point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    field = header.renaming()
    assert field is not None
    assert field.selectedText() == "Channel 1"


def rename(
    panel: TimelinePanel, index: int, text: str, key: Qt.Key = Qt.Key.Key_Return
) -> None:
    field = headers(panel)[index].rename()
    field.selectAll()
    QTest.keyClicks(field, text)
    QTest.keyClick(field, key)


def test_a_rename_is_one_command_and_undo_brings_the_old_name_back() -> None:
    panel = paneled(2)

    rename(panel, 1, "Drums")

    assert names(panel) == ["Channel 1", "Drums"]
    assert headers(panel)[1].renaming() is None
    document_of(panel).undo()
    assert names(panel) == ["Channel 1", "Channel 2"]


def test_escape_keeps_the_old_name() -> None:
    panel = paneled(1)
    before = document_of(panel).can_undo

    rename(panel, 0, "Drums", key=Qt.Key.Key_Escape)

    assert names(panel) == ["Channel 1"]
    assert document_of(panel).can_undo == before


@pytest.mark.parametrize("empty", ["", "   "])
def test_an_empty_name_is_refused(empty: str) -> None:
    panel = paneled(1)
    field = headers(panel)[0].rename()
    field.setText(empty)
    QTest.keyClick(field, Qt.Key.Key_Return)

    assert names(panel) == ["Channel 1"]


def test_leaving_the_field_keeps_the_new_name() -> None:
    panel = paneled(1)
    field = headers(panel)[0].rename()
    field.setText("Pads")

    # Offscreen the test's window is never active; send what losing focus sends.
    QApplication.sendEvent(
        field, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason)
    )

    assert names(panel) == ["Pads"]


# --------------------------------------------------------------------------- #
# recolouring
# --------------------------------------------------------------------------- #


def test_the_chip_offers_the_palette_with_the_current_colour_checked() -> None:
    panel = paneled(2)
    menu = headers(panel)[1].colour_menu()
    palette = theme.active().channels

    assert [a.text() for a in menu.actions()] == [
        f"Colour {n}" for n in range(1, len(palette) + 1)
    ]
    assert [a.isChecked() for a in menu.actions()] == [
        n == 1 for n in range(len(palette))
    ]


def test_a_colour_from_the_palette_is_one_command() -> None:
    panel = paneled(1)
    palette = theme.active().channels

    headers(panel)[0].colour_menu().actions()[4].trigger()

    assert channel(panel, 0).color == palette[4]
    assert headers(panel)[0].chip.colour() == palette[4]
    document_of(panel).undo()
    assert channel(panel, 0).color == palette[0]


def test_clicking_the_chip_pops_the_palette_up_without_waiting() -> None:
    panel = paneled(1)
    chip = headers(panel)[0].chip
    point = QPointF(4, 4)
    QApplication.sendEvent(
        chip,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            chip.mapToGlobal(point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    assert any(menu.isVisible() for menu in headers(panel)[0].findChildren(QMenu))


# --------------------------------------------------------------------------- #
# reordering
# --------------------------------------------------------------------------- #


def drag_header(panel: TimelinePanel, index: int, steps: list[float]) -> None:
    """Press on a header, move by each step - the header following the
    pointer, as it does - and release."""
    header = headers(panel)[index]
    grabbed = QPointF(150, 28)

    def send(kind: QEvent.Type, point: QPointF) -> None:
        left = Qt.MouseButton.LeftButton
        QApplication.sendEvent(
            header,
            QMouseEvent(
                kind,
                point,
                header.mapToGlobal(point),
                Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
                Qt.MouseButton.NoButton
                if kind is QEvent.Type.MouseButtonRelease
                else left,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    send(QEvent.Type.MouseButtonPress, grabbed)
    for step in steps:
        send(QEvent.Type.MouseMove, grabbed + QPointF(0, step))
    send(QEvent.Type.MouseButtonRelease, grabbed)


def test_dragging_a_header_down_two_lanes_moves_its_channel_in_one_command() -> None:
    panel = paneled(4)
    before = len(document_of(panel).project.channels)

    drag_header(panel, 0, [25.0] * 5)  # 125 px: its middle is over lane 3

    assert names(panel) == ["Channel 2", "Channel 3", "Channel 1", "Channel 4"]
    assert aligned(panel)
    document_of(panel).undo()
    assert names(panel) == ["Channel 1", "Channel 2", "Channel 3", "Channel 4"]
    assert len(document_of(panel).project.channels) == before


def test_dragging_a_header_up_moves_it_up() -> None:
    panel = paneled(4)
    drag_header(panel, 3, [-30.0] * 4)
    assert names(panel) == ["Channel 1", "Channel 4", "Channel 2", "Channel 3"]


def test_a_press_that_barely_moves_reorders_nothing() -> None:
    panel = paneled(3)
    before = document_of(panel).can_undo

    drag_header(panel, 0, [DRAG_THRESHOLD - 1])

    assert names(panel) == ["Channel 1", "Channel 2", "Channel 3"]
    assert document_of(panel).can_undo == before
    assert aligned(panel)


@pytest.mark.parametrize(
    ("index", "steps", "order"),
    [
        (0, [-40.0] * 5, ["Channel 1", "Channel 2", "Channel 3"]),
        (0, [60.0] * 20, ["Channel 2", "Channel 3", "Channel 1"]),
    ],
)
def test_a_header_dragged_past_either_end_stops_there(
    index: int, steps: list[float], order: list[str]
) -> None:
    panel = paneled(3)
    drag_header(panel, index, steps)
    assert names(panel) == order
    assert aligned(panel)


def test_a_header_dragged_while_scrolled_lands_under_the_pointer() -> None:
    """The mutation this is for: the drop worked out without the scroll, which
    is right only while nothing has been scrolled."""
    panel = paneled(15, height=400)
    panel.view.verticalScrollBar().setValue(200)
    assert aligned(panel)

    drag_header(panel, 5, [28.0] * 4)  # two lanes down, from lane 6

    assert names(panel)[7] == "Channel 6"
    assert aligned(panel)


# --------------------------------------------------------------------------- #
# kept
# --------------------------------------------------------------------------- #


def test_channels_in_every_state_survive_a_save_and_a_reopen(tmp_path: Path) -> None:
    window = MainWindow()
    timeline = window.timeline()
    document = window.document()
    for _ in range(5):
        timeline.add_channel()
    first, second, third, fourth, fifth = document.project.channels
    for target, field, value in (
        (first, "solo", True),
        (second, "mute", True),
        (third, "hrtf_bypass", True),
        (fourth, "gain_db", -7.5),
        (fifth, "snap_override", SnapSetting(division=Division.QUARTER, triplet=True)),
        (fifth, "name", "Pads"),
        (fifth, "color", theme.active().channels[6]),
    ):
        document.push(SetAttribute(target, field, value))
    document.push(MoveChannel(document.project, fifth, 0))
    saved = copy.deepcopy(document.project)
    document.save_as(tmp_path / "channels.3dim")

    document.new()
    assert timeline.headers.headers() == []
    document.open(tmp_path / "channels.3dim")

    assert document.project == saved
    shown = [
        (h.name.text(), h.chip.colour(), h.mute.isChecked(), h.solo.isChecked(),
         h.bypass.isChecked(), h.gain.value(), h.snap.text())
        for h in timeline.headers.headers()
    ]  # fmt: skip
    assert shown == [
        ("Pads", theme.active().channels[6], False, False, False, 0.0, "1/4T"),
        ("Channel 1", theme.active().channels[0], False, True, False, 0.0, "snap"),
        ("Channel 2", theme.active().channels[1], True, False, False, 0.0, "snap"),
        ("Channel 3", theme.active().channels[2], False, False, True, 0.0, "snap"),
        ("Channel 4", theme.active().channels[3], False, False, False, -7.5, "snap"),
    ]


def test_headers_of_a_reopened_project_edit_the_reopened_channels(
    tmp_path: Path,
) -> None:
    """Reopening a file gives channels equal to the ones shown and not the
    same objects; headers still holding the old ones would edit channels no
    longer in the project, with nothing on screen to say so."""
    window = MainWindow()
    window.timeline().add_channel()
    document = window.document()
    document.save_as(tmp_path / "one.3dim")

    document.open(tmp_path / "one.3dim")
    window.timeline().headers.headers()[0].mute.click()

    assert document.project.channels[0].mute is True
