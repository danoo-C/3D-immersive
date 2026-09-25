"""Channels in the timeline: headers beside lanes, and scrolling through them.

Marked gui. Built as a panel on its own, not a window.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, MoveChannel, RemoveChannel, SetAttribute
from immersive.core.model import Channel, SnapSetting, new_channel
from immersive.core.time import Division
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.headers import SILENCED, ChannelHeader
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
