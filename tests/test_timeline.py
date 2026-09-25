"""The timeline: its view on the shared axis, and the grid it draws.

Marked gui. Built widget by widget rather than as a `MainWindow`, which costs
fifty milliseconds a test for a window none of these look at.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QAction, QImage, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddClip, AddMedia, SetAttribute
from immersive.core.io import project_io
from immersive.core.model import Channel, Clip, MediaFile, Project, SnapSetting
from immersive.core.time import SAMPLE_RATE, Division
from immersive.ui import theme, theme_io
from immersive.ui.main_window import MainWindow, snap_text
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.grid import Unit
from immersive.ui.timeline.panel import EXTENT_BEYOND, EXTENT_FLOOR, TimelinePanel
from immersive.ui.timeline.view import SCROLL_STEP, ZOOM_STEP, TimelineView

pytestmark = pytest.mark.gui

WIDTH, HEIGHT = 800, 120
HOUR = SAMPLE_RATE * 3600

#: At 120 BPM and 480 samples a pixel a beat is 50 px and a bar 200.
SCALE = 480.0
BAR_PX = 200

#: Multipliers and offsets that give every token a colour unlike any other.
SPREAD = ((37, 11), (53, 7), (71, 3))


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    before = theme.active()
    yield
    theme.use(before)


def viewed(
    scale: float = SCALE, *, snapping: bool = False
) -> tuple[TimelineView, Document]:
    document = Document()
    document.project.snap.enabled = snapping
    view = TimelineView(document, TimeAxis(scale, extent=HOUR))
    view.resize(WIDTH, HEIGHT)
    view.show()
    return view, document


def grabbed(view: TimelineView) -> QImage:
    return view.viewport().grab().toImage()


def colour(key: str) -> str:
    return theme.group_color("timeline", key).upper()


def at(image: QImage, x: int) -> str:
    return image.pixelColor(x, image.height() // 2).name().upper()


def row(image: QImage) -> set[str]:
    return {at(image, x) for x in range(image.width())}


def wheel(
    view: TimelineView,
    x: float,
    *,
    dx: int = 0,
    dy: int = 0,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    point = QPointF(x, 10)
    event = QWheelEvent(
        point,
        view.viewport().mapToGlobal(point),
        QPoint(),
        QPoint(dx, dy),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


# --------------------------------------------------------------------------- #
# the grid, where the axis says
# --------------------------------------------------------------------------- #


def test_bar_lines_are_drawn_where_the_axis_puts_them() -> None:
    view, _ = viewed()
    view.axis.scroll_to(130)
    image = grabbed(view)
    first, last = view.axis.visible()

    bars = [n * BAR_PX * SCALE for n in range(int(first // (BAR_PX * SCALE)) + 1, 40)]
    columns = [round(view.axis.x_of(sample)) for sample in bars if sample < last]
    assert len(columns) >= 3
    for x in columns:
        assert at(image, x) == colour("grid"), x
        assert at(image, x + BAR_PX // 8) == colour("background"), "between beats"
    assert at(image, columns[0] + BAR_PX // 4) == colour("grid.beat")


def test_division_lines_follow_the_snap_setting() -> None:
    on, _ = viewed(snapping=True)  # 1/16 is 12.5 px: room
    off, _ = viewed(snapping=False)

    assert colour("grid.division") in row(grabbed(on))
    assert colour("grid.division") not in row(grabbed(off))


def loud() -> theme.Theme:
    """The built-in with every token a colour unlike any other."""
    builtin = theme_io.builtin()
    return replace(
        builtin,
        tokens={
            name: "#" + "".join(f"{(n * k + c) % 256:02X}" for k, c in SPREAD)
            for n, name in enumerate(sorted(builtin.tokens))
        },
    )


def test_a_theme_change_repaints_every_colour() -> None:
    view, _ = viewed(snapping=True)
    before = row(grabbed(view))
    theme.use(loud())

    view.retheme()

    assert not before & row(grabbed(view))


# --------------------------------------------------------------------------- #
# the scrollbar is the axis
# --------------------------------------------------------------------------- #


def test_the_axis_is_as_wide_as_the_lanes() -> None:
    view, _ = viewed()
    assert view.axis.width == view.viewport().width()

    view.resize(WIDTH + 150, HEIGHT)

    assert view.axis.width == view.viewport().width()


def test_moving_the_scrollbar_moves_the_axis() -> None:
    view, _ = viewed()

    view.horizontalScrollBar().setValue(1234)

    assert view.axis.offset == 1234


def test_moving_the_axis_moves_the_scrollbar() -> None:
    view, _ = viewed()

    view.axis.scroll_to(777)

    assert view.horizontalScrollBar().value() == 777


def test_the_scrollbar_reaches_exactly_the_axis_extent() -> None:
    view, _ = viewed()
    assert view.horizontalScrollBar().maximum() == view.axis.span() - view.axis.width


# --------------------------------------------------------------------------- #
# the wheel
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("notch", "factor"), [(120, 1 / ZOOM_STEP), (-120, ZOOM_STEP)])
def test_ctrl_wheel_zooms_about_the_cursor(notch: int, factor: float) -> None:
    view, _ = viewed()
    view.axis.scroll_to(view.axis.span() // 2)
    before = view.axis.sample_at(300)

    wheel(view, 300, dy=notch, modifiers=Qt.KeyboardModifier.ControlModifier)

    assert view.axis.scale == pytest.approx(SCALE * factor)
    assert abs(view.axis.sample_at(300) - before) <= 0.5 * view.axis.scale


@pytest.mark.parametrize(
    ("dx", "dy", "modifiers"),
    [
        (0, -120, Qt.KeyboardModifier.ShiftModifier),
        (-120, 0, Qt.KeyboardModifier.ShiftModifier),
        (-120, 0, Qt.KeyboardModifier.NoModifier),
    ],
    ids=["shift and a vertical delta", "shift and a sideways one", "sideways alone"],
)
def test_shift_wheel_or_a_sideways_wheel_scrolls_along_time(
    dx: int, dy: int, modifiers: Qt.KeyboardModifier
) -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    wheel(view, 300, dx=dx, dy=dy, modifiers=modifiers)

    assert view.axis.offset == 1000 + SCROLL_STEP
    assert view.axis.scale == SCALE
    assert view.verticalScrollBar().value() == 0


def test_the_wheel_alone_leaves_time_where_it_is() -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    wheel(view, 300, dy=-120)

    assert (view.axis.offset, view.axis.scale) == (1000, SCALE)


# --------------------------------------------------------------------------- #
# the ruler and the playhead
# --------------------------------------------------------------------------- #


def paneled(scale: float = SCALE) -> TimelinePanel:
    document = Document()
    document.project.snap.enabled = False
    panel = TimelinePanel(document, TimeAxis(scale))
    panel.resize(WIDTH, HEIGHT + 60)
    panel.show()
    return panel


def click(panel: TimelinePanel, x: float) -> None:
    point = QPointF(x, 5)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        point,
        panel.ruler.mapToGlobal(point),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(panel.ruler, event)


def column(image: QImage, x: int) -> set[str]:
    return {image.pixelColor(x, y).name().upper() for y in range(image.height())}


def test_clicking_the_ruler_puts_the_playhead_under_the_click() -> None:
    panel = paneled()
    panel.axis.scroll_to(500)

    click(panel, 123)

    assert panel.playhead() == round(panel.axis.sample_at(123))
    assert panel.playhead() == (500 + 123) * SCALE


def test_the_playhead_is_drawn_in_both_widgets() -> None:
    panel = paneled()
    click(panel, 300)
    playhead = colour("playhead")

    assert at(grabbed(panel.view), 300) == playhead
    assert playhead in column(panel.ruler.grab().toImage(), 300)
    assert playhead not in column(panel.ruler.grab().toImage(), 250)


def test_the_playhead_is_drawn_over_the_grid() -> None:
    panel = paneled()
    click(panel, 2 * BAR_PX)  # exactly on a bar line

    assert at(grabbed(panel.view), 2 * BAR_PX) == colour("playhead")


def test_switching_the_unit_changes_the_labels_and_not_the_grid() -> None:
    panel = paneled()
    lanes, labels = grabbed(panel.view), panel.ruler.grab().toImage()

    panel.set_unit(Unit.TIME)

    assert grabbed(panel.view) == lanes
    assert panel.ruler.grab().toImage() != labels


def test_the_ruler_draws_its_group() -> None:
    panel = paneled()
    image = panel.ruler.grab().toImage()
    drawn = {
        image.pixelColor(x, y).name().upper()
        for x in range(image.width())
        for y in range(image.height())
    }
    for key in ("background", "tick", "text"):
        assert theme.group_color("ruler", key).upper() in drawn, key


# --------------------------------------------------------------------------- #
# in the window
# --------------------------------------------------------------------------- #


def test_the_window_has_the_timeline_in_place_of_its_placeholder() -> None:
    window = MainWindow()
    assert isinstance(window.timeline(), TimelinePanel)
    assert window.timeline().axis is window.timeline().view.axis


def test_the_ruler_units_are_one_checked_pair_in_the_view_menu() -> None:
    window = MainWindow()
    actions = {
        action.text().replace("&", ""): action
        for action in window.findChildren(QAction)
        if action.text().startswith("Ruler")
    }
    bars, time = actions["Ruler: Bars / Beats"], actions["Ruler: Minutes / Seconds"]
    assert bars.isEnabled() and time.isEnabled()
    assert "M3" not in bars.toolTip() + time.toolTip()
    assert bars.isChecked() and not time.isChecked()

    time.trigger()

    assert window.timeline().unit() is Unit.TIME
    assert time.isChecked() and not bars.isChecked()


def everything(image: QImage) -> set[str]:
    """Every colour in `image`, read in one pass rather than pixel by pixel -
    a window-sized grab is a third of a million `pixelColor` calls."""
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    pixels = np.frombuffer(
        rgb.constBits(), dtype=np.uint32, count=rgb.sizeInBytes() // 4
    )
    return {f"#{value & 0xFFFFFF:06X}" for value in np.unique(pixels)}


def test_a_theme_switch_in_the_window_repaints_the_ruler_and_the_lanes() -> None:
    """Through D-82's walk, and without the panel being built again."""
    window = MainWindow()
    window.resize(1500, 950)
    window.show()
    timeline = window.timeline()
    before = everything(timeline.ruler.grab().toImage()) | everything(
        grabbed(timeline.view)
    )

    window.apply_theme(loud())

    assert window.timeline() is timeline
    after = everything(timeline.ruler.grab().toImage()) | everything(
        grabbed(timeline.view)
    )
    assert not before & after


# --------------------------------------------------------------------------- #
# the project in the timeline
# --------------------------------------------------------------------------- #


def saved(tmp_path: Path, project: Project) -> Path:
    path = tmp_path / "song.3dim"
    project_io.save(project, path)
    return path


def test_an_opened_project_draws_its_own_tempo_and_new_goes_back(
    tmp_path: Path,
) -> None:
    """90 BPM in 3/4: a beat is 32 000 samples and a bar three of them."""
    panel = paneled()
    document = panel._document
    document.open(saved(tmp_path, Project(bpm=90.0, time_signature=(3, 4))))
    document.project.snap.enabled = False
    image = grabbed(panel.view)

    def x(sample: float) -> int:
        return round(panel.axis.x_of(sample))

    assert at(image, x(96_000)) == colour("grid")  # bar 2
    assert at(image, x(32_000)) == colour("grid.beat")
    assert at(image, x(24_000)) == colour("background"), "not 120's beat"

    document.new()
    document.project.snap.enabled = False
    image = grabbed(panel.view)
    assert at(image, x(24_000)) == colour("grid.beat")
    assert at(image, x(96_000)) == colour("grid")


def chips(window: MainWindow) -> set[str]:
    return {label.text() for label in window.findChildren(QLabel)}


def test_the_toolbar_reads_the_open_projects_tempo_and_follows_undo(
    tmp_path: Path,
) -> None:
    window = MainWindow()
    project = Project(
        bpm=90.0,
        time_signature=(3, 4),
        snap=SnapSetting(division=Division.EIGHTH, triplet=True),
    )
    window.document().open(saved(tmp_path, project))
    assert {"90.0 BPM", "3/4", "Snap 1/8T"} <= chips(window)

    window.document().push(SetAttribute(window.document().project, "bpm", 100.0))
    assert "100.0 BPM" in chips(window)
    window.document().undo()
    assert "90.0 BPM" in chips(window)

    window.document().new()
    assert {"120.0 BPM", "4/4", "Snap 1/16"} <= chips(window)


def test_the_snap_chip_says_off_and_triplet() -> None:
    assert snap_text(SnapSetting(enabled=False)) == "Snap off"
    assert snap_text(SnapSetting(division=Division.QUARTER)) == "Snap 1/4"
    assert snap_text(SnapSetting(division=Division.EIGHTH, triplet=True)) == "Snap 1/8T"


def test_the_timeline_scrolls_as_far_as_the_project_reaches() -> None:
    panel = paneled()
    document = panel._document
    assert panel.axis.extent == EXTENT_FLOOR

    twenty_minutes = SAMPLE_RATE * 60 * 20
    media = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, SAMPLE_RATE)
    channel = Channel("c-00000001", "One", "#A855F7")
    document.push(AddMedia(document.project, [media]))
    document.push(AddChannel(document.project, channel))
    document.push(
        AddClip(channel, Clip("k-00000001", media.id, twenty_minutes, 0, SAMPLE_RATE))
    )

    assert panel.axis.extent == twenty_minutes + SAMPLE_RATE + EXTENT_BEYOND
    document.undo()
    assert panel.axis.extent == EXTENT_FLOOR


class Paints(QObject):
    """Counts the paint events a widget is sent."""

    def __init__(self, widget: QObject) -> None:
        super().__init__()
        self.count = 0
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint:
            self.count += 1
        return False


def test_a_change_to_the_project_repaints_the_lanes_and_the_ruler() -> None:
    """A grab renders afresh whatever was scheduled, so what is counted here
    is the repaint itself - without it the screen keeps the old grid until
    something else happens to repaint it."""
    panel = paneled()
    QApplication.processEvents()
    lanes, ruler = Paints(panel.view.viewport()), Paints(panel.ruler)

    panel._document.push(SetAttribute(panel._document.project, "bpm", 90.0))
    QApplication.processEvents()

    assert lanes.count and ruler.count


def test_ruler_ticks_are_longest_at_bars_and_shortest_at_divisions() -> None:
    """Looking at a grab found beats and divisions ticked alike, so the beat
    was hard to find on the ruler; the lanes had always told them apart."""
    panel = paneled()
    panel._document.project.snap.enabled = True  # 1/16: 12.5 px
    panel.set_playhead(10 * BAR_PX * int(SCALE))  # out of the way
    image = panel.ruler.grab().toImage()
    tick = theme.group_color("ruler", "tick").upper()

    def length(x: int) -> int:
        return sum(
            image.pixelColor(x, y).name().upper() == tick for y in range(image.height())
        )

    bar, beat, division = length(BAR_PX), length(BAR_PX + 50), length(BAR_PX + 25)
    assert bar > beat > division > 0


# --------------------------------------------------------------------------- #
# the middle button
# --------------------------------------------------------------------------- #


def mouse(
    view: TimelineView,
    kind: QEvent.Type,
    x: float,
    button: Qt.MouseButton = Qt.MouseButton.MiddleButton,
) -> None:
    point = QPointF(x, 40)
    held = Qt.MouseButton.NoButton if kind is QEvent.Type.MouseButtonRelease else button
    event = QMouseEvent(
        kind,
        point,
        view.viewport().mapToGlobal(point),
        Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else button,
        held,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)


def drag(
    view: TimelineView,
    path: list[float],
    button: Qt.MouseButton = Qt.MouseButton.MiddleButton,
) -> None:
    mouse(view, QEvent.Type.MouseButtonPress, path[0], button)
    for x in path[1:]:
        mouse(view, QEvent.Type.MouseMove, x, button)
    mouse(view, QEvent.Type.MouseButtonRelease, path[-1], button)


def test_a_middle_drag_pans_the_lanes_with_the_hand() -> None:
    """Dragging left brings later time into view, as a hand dragging paper
    would - and the scrollbar, and so the ruler, go with it."""
    view, _ = viewed()
    view.axis.scroll_to(1000)

    drag(view, [400, 350, 301.6, 300])

    assert view.axis.offset == 1100
    assert view.horizontalScrollBar().value() == 1100


def test_a_long_pan_does_not_drift_from_the_hand() -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    drag(view, [400] + [400 - 0.4 * step for step in range(1, 251)] + [300])

    assert view.axis.offset == 1100


def test_a_pan_stops_at_the_start_of_the_timeline() -> None:
    view, _ = viewed()
    view.axis.scroll_to(50)

    drag(view, [100, 700])

    assert view.axis.offset == 0


def test_only_the_middle_button_pans() -> None:
    view, _ = viewed()
    view.axis.scroll_to(1000)

    drag(view, [400, 300], button=Qt.MouseButton.LeftButton)

    assert view.axis.offset == 1000


def test_the_hand_shows_while_panning_and_goes_after() -> None:
    view, _ = viewed()
    mouse(view, QEvent.Type.MouseButtonPress, 400)
    assert view.viewport().cursor().shape() is Qt.CursorShape.ClosedHandCursor

    mouse(view, QEvent.Type.MouseButtonRelease, 400)

    assert view.viewport().cursor().shape() is Qt.CursorShape.ArrowCursor
