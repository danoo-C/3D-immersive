"""Fade handles on the clip: drawn on a selected clip, grabbed in its name
strip, dragged as one edit on release (F-15, D-101). Marked gui."""

from __future__ import annotations

import copy
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.model import Clip, Fade, FadeShape, MediaFile, new_channel
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import HANDLE_SIZE, NAME_HEIGHT, TOP, ClipItem
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.timeline.panel import TimelinePanel

pytestmark = pytest.mark.gui

#: 480 samples a pixel: a second is 100 px.
SCALE = 480.0
SECOND = SAMPLE_RATE
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 60 * SECOND)
NONE = Qt.KeyboardModifier.NoModifier


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def paneled() -> tuple[TimelinePanel, list[Clip]]:
    """Two lanes; on each, a clip two seconds long at 1 s with a quarter
    second of fade-in and half a second of fade-out."""
    document = Document()
    document.push(AddMedia(document.project, [MEDIA]))
    clips = []
    for lane in range(2):
        project = document.project
        document.push(
            AddChannel(project, new_channel(project, theme.active().channels))
        )
        clip = Clip(
            f"k-0000000{lane}",
            MEDIA.id,
            SECOND,
            0,
            2 * SECOND,
            fade_in=Fade(SECOND // 4),
            fade_out=Fade(SECOND // 2, FadeShape.EQUAL_POWER),
        )
        document.push(DropClips(project, project.channels[lane], [clip]))
        clips.append(clip)
    panel = TimelinePanel(document, TimeAxis(SCALE))
    panel.resize(1200, 300)
    panel.show()
    QApplication.processEvents()
    return panel, clips


def mouse(
    panel: TimelinePanel, kind: QEvent.Type, point: QPointF, *, held: bool = True
) -> None:
    left = Qt.MouseButton.LeftButton
    viewport = panel.view.viewport()
    pressed = (
        left
        if held and kind is not QEvent.Type.MouseButtonRelease
        else Qt.MouseButton.NoButton
    )
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            kind,
            point,
            viewport.mapToGlobal(point),
            Qt.MouseButton.NoButton if kind is QEvent.Type.MouseMove else left,
            pressed,
            NONE,
        ),
    )


def drag(
    panel: TimelinePanel, start: QPointF, dx: float, *, release: bool = True
) -> None:
    end = start + QPointF(dx, 0)
    mouse(panel, QEvent.Type.MouseButtonPress, start)
    mouse(panel, QEvent.Type.MouseMove, (start + end) / 2)
    mouse(panel, QEvent.Type.MouseMove, end)
    if release:
        mouse(panel, QEvent.Type.MouseButtonRelease, end)


def point(lane: int, seconds: float, y: float) -> QPointF:
    """`seconds` into the timeline, `y` pixels into lane `lane`'s clip."""
    return QPointF(seconds * SECOND / SCALE, lane * LANE_HEIGHT + TOP + y)


#: In the name strip, and below it.
IN_STRIP, BELOW = 5.0, NAME_HEIGHT + 10.0

#: Where each clip's fades end: a quarter second in, and half a second
#: before its end at 3 s.
FADE_IN_END, FADE_OUT_START = 1.25, 2.5


def edits(panel: TimelinePanel) -> int:
    return len(panel._document._stack)


def item_of(panel: TimelinePanel, clip: Clip) -> ClipItem:
    [item] = [i for i in panel.view.clip_items() if i.clip is clip]
    return item


def selected(panel: TimelinePanel, *clips: Clip) -> None:
    panel._document.selection.select(Kind.CLIPS, clips)
    QApplication.processEvents()


# --------------------------------------------------------------------------- #
# the drag
# --------------------------------------------------------------------------- #


def test_a_handle_drag_sets_the_fade_in_one_command_on_release() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    count = edits(panel)

    drag(panel, point(0, FADE_IN_END, IN_STRIP), 25)  # a quarter second right

    assert clip.fade_in == Fade(SECOND // 2)
    assert clip.fade_out == Fade(SECOND // 2, FadeShape.EQUAL_POWER)
    assert (clip.start, clip.length) == (SECOND, 2 * SECOND), "no trim"
    assert edits(panel) == count + 1
    panel._document.undo()
    assert clip.fade_in == Fade(SECOND // 4)


def test_dragging_a_fade_outs_handle_left_lengthens_it() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    drag(panel, point(0, FADE_OUT_START, IN_STRIP), -25)
    assert clip.fade_out == Fade(SECOND * 3 // 4, FadeShape.EQUAL_POWER)


def test_a_fade_is_drawn_where_the_release_will_put_it() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 25, release=False)

    assert panel.view.dragging()
    assert item_of(panel, clip).fades()[0] == Fade(SECOND // 2)
    assert clip.fade_in == Fade(SECOND // 4), "nothing edited until the release"
    mouse(panel, QEvent.Type.MouseButtonRelease, point(0, FADE_IN_END + 0.25, IN_STRIP))
    assert item_of(panel, clip).fades()[0] == clip.fade_in == Fade(SECOND // 2)


def test_a_fade_stops_at_the_other_fade_and_at_nothing() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 500)
    assert clip.fade_in.length == 2 * SECOND - SECOND // 2, "up to the fade-out"
    panel._document.undo()

    drag(panel, point(0, FADE_OUT_START, IN_STRIP), 500)
    assert clip.fade_out.length == 0, "and no shorter than nothing"
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 500)
    assert clip.fade_in.length == 2 * SECOND, "the whole clip, with no fade-out"


def test_where_two_fades_meet_the_fade_in_is_grabbed() -> None:
    """Both handles are at one place: the nearer wins, and a tie goes to the
    fade-in, whose handle is the one at the start of the strip's order."""
    panel, (clip, _) = paneled()
    selected(panel, clip)
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 500)
    meeting = 1 + clip.fade_in.length / SECOND

    drag(panel, point(0, meeting, IN_STRIP), -25)

    assert clip.fade_in.length == 2 * SECOND - SECOND // 2 - SECOND // 4
    assert clip.fade_out.length == SECOND // 2


def test_a_handle_drag_changes_the_same_fade_of_every_selected_clip() -> None:
    """F-51, as a trim does."""
    panel, clips = paneled()
    selected(panel, *clips)
    count = edits(panel)

    drag(panel, point(0, FADE_IN_END, IN_STRIP), 25)

    assert [clip.fade_in for clip in clips] == [Fade(SECOND // 2)] * 2
    assert edits(panel) == count + 1


def test_escape_during_a_handle_drag_puts_it_back_and_edits_nothing() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    before, count = copy.deepcopy(panel._document.project), edits(panel)
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 25, release=False)

    QApplication.sendEvent(
        panel.view, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NONE)
    )
    mouse(panel, QEvent.Type.MouseButtonRelease, point(0, FADE_IN_END + 0.25, IN_STRIP))

    assert panel._document.project == before and edits(panel) == count
    assert item_of(panel, clip).fades()[0] == Fade(SECOND // 4)


# --------------------------------------------------------------------------- #
# what a press takes
# --------------------------------------------------------------------------- #


def test_below_the_strip_an_edge_still_trims() -> None:
    """A fade of nothing has its handle at the clip's corner, where the
    trim's edge zone also is: the strip is the handle's, the rest the trim's."""
    panel, (clip, _) = paneled()
    clip.fade_in = Fade()
    selected(panel, clip)

    drag(panel, point(0, 1.0, BELOW), 25)

    assert clip.start == SECOND + SECOND // 4 and clip.fade_in == Fade()


def test_in_the_strip_at_the_corner_the_handle_wins() -> None:
    panel, (clip, _) = paneled()
    clip.fade_in = Fade()
    selected(panel, clip)
    panel.view._lay_out()

    drag(panel, point(0, 1.0 + 0.01, IN_STRIP), 25)

    assert clip.start == SECOND and clip.fade_in == Fade(SECOND // 4)


def test_a_press_that_selects_a_clip_takes_its_body_not_a_handle() -> None:
    """Handles are drawn on selected clips; a press on one that was not
    selected does what the pointer showed there."""
    panel, (clip, _) = paneled()
    drag(panel, point(0, FADE_IN_END, IN_STRIP), 50)
    assert clip.fade_in == Fade(SECOND // 4)
    assert clip.start != SECOND, "moved, as a body drag does"


def test_the_pointer_shows_a_handle_before_the_press() -> None:
    panel, (clip, _) = paneled()
    selected(panel, clip)
    viewport = panel.view.viewport()
    mouse(panel, QEvent.Type.MouseMove, point(0, FADE_IN_END, IN_STRIP), held=False)
    assert viewport.cursor().shape() is Qt.CursorShape.SizeHorCursor
    mouse(panel, QEvent.Type.MouseMove, point(0, 2.0, IN_STRIP), held=False)
    assert viewport.cursor().shape() is not Qt.CursorShape.SizeHorCursor


# --------------------------------------------------------------------------- #
# drawn
# --------------------------------------------------------------------------- #


def colour_at(item: ClipItem, x: float, y: float) -> QColor:
    image = item.scene().views()[0].grab().toImage()
    at = item.scene().views()[0].mapFromScene(item.mapToScene(QPointF(x, y)))
    return QColor(image.pixelColor(at.x(), at.y()))


def near(colour: QColor, hex_: str, within: int = 12) -> bool:
    """Within a few levels of `hex_` on every channel: a line or a fill at a
    fractional pixel is blended at its edges."""
    wanted = QColor(hex_)
    return all(
        abs(a - b) <= within
        for a, b in (
            (colour.red(), wanted.red()),
            (colour.green(), wanted.green()),
            (colour.blue(), wanted.blue()),
        )
    )


def test_handles_are_drawn_on_a_selected_clip_only() -> None:
    panel, (clip, other) = paneled()
    selected(panel, clip)
    handle = theme.group_color("clip", "fade.handle")
    middle = FADE_IN_END * SECOND / SCALE - SECOND / SCALE, 2 + HANDLE_SIZE / 2
    assert near(colour_at(item_of(panel, clip), *middle), handle, within=2)
    assert not near(colour_at(item_of(panel, other), *middle), handle)


def test_a_fade_is_drawn_as_its_shapes_curve() -> None:
    """A quarter of the way into the equal-power fade-out the curve stands at
    sin(67.5°) of the height - falling, and not a straight line."""
    panel, (clip, _) = paneled()
    item = item_of(panel, clip)
    fade = theme.group_color("clip", "fade")
    x = (FADE_OUT_START + 0.125 - 1) * SECOND / SCALE
    height = item.boundingRect().height() - 3

    def at_gain(gain: float) -> float:
        return height + 1 - gain * height

    falling = at_gain(FadeShape.EQUAL_POWER.gain(0.75))
    assert any(near(colour_at(item, x, falling + dy), fade) for dy in (-1, 0, 1))
    for wrong in (FadeShape.EQUAL_POWER.gain(0.25), 0.75):  # rising; straight
        assert not near(colour_at(item, x, at_gain(wrong)), fade)


def test_a_clip_whose_fade_changes_is_painted_again() -> None:
    """The item repaints only when what it draws changes, and a fade is
    part of what it draws."""
    panel, (clip, _) = paneled()
    item = item_of(panel, clip)
    panel.view.grab()
    before = item.paints

    for name, fade in (("fade_in", Fade(SECOND)), ("fade_out", Fade(SECOND // 4))):
        panel._document.push(SetAttribute(clip, name, fade))
        panel.view.grab()
        assert item.paints > before, name
        before = item.paints
