"""Clips in their lanes: where they sit, what they draw, and when they draw
it again. Marked gui. Built as a panel on its own, over real samples."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage
from PySide6.QtWidgets import QApplication

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.media_store import MediaStore, Prepared, prepare
from immersive.core.model import Clip, new_channel, new_clip_id
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.explorer.media_pool import MIME
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.clips import (
    BODY_ALPHA,
    MIN_NAME,
    MIN_WAVEFORM,
    NAME_HEIGHT,
    TOP,
    ClipItem,
)
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.timeline.panel import TimelinePanel
from immersive.ui.widgets.waveform import MISSING_TEXT

pytestmark = pytest.mark.gui

#: 480 samples a pixel: a second is 100 px.
SCALE = 480.0


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def half_silent(path: Path, seconds: float = 2.0) -> Path:
    """Silence for the first half, full-scale noise for the second."""
    frames = int(SAMPLE_RATE * seconds)
    audio = np.zeros(frames, dtype=np.float32)
    audio[frames // 2 :] = np.random.default_rng(1).uniform(-1, 1, frames - frames // 2)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


class Arrangement:
    """A panel over a project whose one sample is `half_silent`."""

    def __init__(
        self, tmp_path: Path, *, channels: int = 2, stored: bool = True
    ) -> None:
        prepared = prepare(half_silent(tmp_path / "half.wav"))
        assert isinstance(prepared, Prepared)
        self.prepared = prepared
        self.store = MediaStore()
        self.document = Document()
        self.media = prepared.media_file("m-00000001")
        if stored:
            self.store.keep(self.media.id, prepared)
        self.document.push(AddMedia(self.document.project, [self.media]))
        for _ in range(channels):
            project = self.document.project
            self.document.push(
                AddChannel(project, new_channel(project, theme.active().channels))
            )
        self.panel = TimelinePanel(self.document, TimeAxis(SCALE), self.store)
        self.panel.resize(1200, 300)
        self.panel.set_playhead(10**9)  # drawn over everything; keep it away
        self.panel.show()
        QApplication.processEvents()

    def drop(
        self,
        lane: int,
        start: int,
        *,
        offset: int = 0,
        length: int | None = None,
    ) -> Clip:
        clip = Clip(
            new_clip_id(self.document.project),
            self.media.id,
            start,
            offset,
            length or self.media.frames - offset,
        )
        channel = self.document.project.channels[lane]
        self.document.push(DropClips(self.document.project, channel, [clip]))
        return clip

    def item(self, clip: Clip) -> ClipItem:
        [found] = [item for item in self.panel.view.clip_items() if item.clip is clip]
        return found

    def grab(self) -> QImage:
        return self.panel.view.viewport().grab().toImage()


def blend(colour: str, ground: str, alpha: float = BODY_ALPHA) -> tuple[int, int, int]:
    over, under = QColor(colour), QColor(ground)
    return tuple(
        round(a * alpha + b * (1 - alpha))
        for a, b in (
            (over.red(), under.red()),
            (over.green(), under.green()),
            (over.blue(), under.blue()),
        )
    )  # type: ignore[return-value]


def near(pixel: QColor, rgb: tuple[int, int, int], tolerance: int = 2) -> bool:
    return all(
        abs(a - b) <= tolerance
        for a, b in zip((pixel.red(), pixel.green(), pixel.blue()), rgb, strict=True)
    )


def inked_rows(image: QImage, x: int, colour: str, top: int, bottom: int) -> int:
    target = QColor(colour).name().upper()
    return sum(
        image.pixelColor(x, y).name().upper() == target for y in range(top, bottom)
    )


# --------------------------------------------------------------------------- #
# where a clip sits, and in what colour
# --------------------------------------------------------------------------- #


def test_a_clip_sits_in_its_lane_at_its_start(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(1, 48_000)

    item = arrangement.item(clip)

    assert (item.pos().x(), item.pos().y()) == (48_000 / SCALE, LANE_HEIGHT + TOP)
    assert item.boundingRect().width() == clip.length / SCALE


def test_a_clip_is_its_channels_colour(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(
        0, 0, length=SAMPLE_RATE // 2
    )  # silence: no ink below the name
    colour = arrangement.document.project.channels[0].color
    ground = theme.group_color("timeline", "background")

    image = arrangement.grab()
    pixel = image.pixelColor(30, TOP + NAME_HEIGHT + 4)

    assert near(pixel, blend(colour, ground)), pixel.name()
    assert arrangement.item(clip).colour == colour


def test_recolouring_a_channel_repaints_its_clips(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(0, 0, length=SAMPLE_RATE // 2)
    arrangement.grab()
    item = arrangement.item(clip)
    before = item.paints
    other = theme.active().channels[5]

    arrangement.document.push(
        SetAttribute(arrangement.document.project.channels[0], "color", other)
    )
    image = arrangement.grab()

    assert item.paints > before
    ground = theme.group_color("timeline", "background")
    assert near(image.pixelColor(30, TOP + NAME_HEIGHT + 4), blend(other, ground))


# --------------------------------------------------------------------------- #
# what it draws
# --------------------------------------------------------------------------- #


def test_a_trimmed_clip_draws_its_own_part_of_its_sample(tmp_path: Path) -> None:
    """The half-silent sample: a clip of its second half is loud all the way
    across, and one of its first half is flat."""
    arrangement = Arrangement(tmp_path)
    loud = arrangement.drop(0, 0, offset=SAMPLE_RATE, length=SAMPLE_RATE // 2)
    quiet = arrangement.drop(1, 0, offset=0, length=SAMPLE_RATE // 2)
    image = arrangement.grab()
    colour = arrangement.document.project.channels[0].color
    quiet_colour = arrangement.document.project.channels[1].color
    top, bottom = TOP + NAME_HEIGHT, TOP + LANE_HEIGHT - 4

    assert arrangement.item(loud).shows_waveform
    assert inked_rows(image, 20, colour, top, bottom) > 20
    assert (
        inked_rows(image, 20, quiet_colour, LANE_HEIGHT + top, LANE_HEIGHT + bottom)
        <= 1
    )
    assert quiet.offset == 0


def test_a_missing_sample_is_grey_and_says_so(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(0, 0, length=SAMPLE_RATE // 2)
    arrangement.media.missing = True
    arrangement.panel.media_changed()
    item = arrangement.item(clip)
    ground = theme.group_color("timeline", "background")

    image = arrangement.grab()

    assert item.missing
    assert item.label().startswith(MISSING_TEXT)
    assert not item.shows_waveform
    assert near(
        image.pixelColor(30, TOP + NAME_HEIGHT + 4),
        blend(theme.group_color("clip", "missing"), ground),
    )


def test_a_narrow_clip_is_its_body_alone(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    narrow = arrangement.drop(0, 0, length=int((MIN_WAVEFORM - 1) * SCALE))
    middling = arrangement.drop(1, 0, length=int((MIN_NAME - 1) * SCALE))

    assert not arrangement.item(narrow).shows_waveform
    assert not arrangement.item(narrow).shows_name
    assert arrangement.item(middling).shows_waveform
    assert not arrangement.item(middling).shows_name


# --------------------------------------------------------------------------- #
# when it draws again
# --------------------------------------------------------------------------- #


def test_a_repaint_reuses_the_cache_and_a_zoom_does_not(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(0, 0)
    arrangement.grab()
    item = arrangement.item(clip)
    painted = item.paints

    arrangement.panel.view.viewport().repaint()
    arrangement.grab()
    assert item.paints == painted, "nothing changed, so nothing was drawn again"

    arrangement.panel.axis.zoom_about(0, 0.5)
    arrangement.grab()
    assert item.paints > painted
    assert item.boundingRect().width() == clip.length / (SCALE * 0.5)


def test_a_zoom_lays_every_clip_out_again_and_a_scroll_moves_none(
    tmp_path: Path,
) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(0, 96_000)
    item = arrangement.item(clip)

    arrangement.panel.axis.scroll_by(40)
    assert item.pos().x() == 96_000 / SCALE, "a scroll is the view's, not the item's"

    arrangement.panel.axis.zoom_about(0, 2.0)
    assert item.pos().x() == 96_000 / arrangement.panel.axis.scale


def test_peaks_that_arrive_later_are_drawn(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path, stored=False)
    clip = arrangement.drop(0, 0, offset=SAMPLE_RATE, length=SAMPLE_RATE // 2)
    colour = arrangement.document.project.channels[0].color
    top, bottom = TOP + NAME_HEIGHT, TOP + LANE_HEIGHT - 4
    assert inked_rows(arrangement.grab(), 20, colour, top, bottom) == 0

    arrangement.store.keep(arrangement.media.id, arrangement.prepared)
    arrangement.panel.media_changed()

    assert inked_rows(arrangement.grab(), 20, colour, top, bottom) > 20
    assert arrangement.item(clip).shows_waveform


def test_items_follow_the_clips_through_undo(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    arrangement.drop(0, 0, length=10_000)
    assert len(arrangement.panel.view.clip_items()) == 1

    arrangement.document.undo()
    assert arrangement.panel.view.clip_items() == []
    arrangement.document.redo()
    assert len(arrangement.panel.view.clip_items()) == 1


def test_a_theme_switch_repaints_the_cached_clips(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    clip = arrangement.drop(0, 0)
    arrangement.grab()
    item = arrangement.item(clip)
    painted = item.paints

    arrangement.panel.view.retheme()
    arrangement.grab()

    assert item.paints > painted


def test_a_clip_far_wider_than_the_view_draws_only_what_is_on_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qt tells a cached item's first paint that all of it is exposed. Taken
    at its word, a long clip at a close zoom would draw millions of columns
    to show a view's width of them."""
    from immersive.ui.timeline import clips

    drawn: list[int] = []
    real = clips.paint_envelope

    def counting(*args: object, **kwargs: object) -> None:
        columns = kwargs["columns"]
        assert isinstance(columns, range)
        drawn.append(len(columns))
        real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(clips, "paint_envelope", counting)
    arrangement = Arrangement(tmp_path)
    arrangement.panel.axis.zoom_about(0, 1 / SCALE)  # one sample a pixel
    arrangement.drop(0, 0, offset=SAMPLE_RATE, length=SAMPLE_RATE)  # 48 000 px
    arrangement.grab()

    width = arrangement.panel.view.viewport().width()
    assert drawn, "it drew its waveform"
    assert max(drawn) <= width + 2


# --------------------------------------------------------------------------- #
# dropping from the pool, through the view
# --------------------------------------------------------------------------- #


def pool_drag(*media_ids: str) -> QMimeData:
    """What the pool puts in a drag (04, *Media pool*)."""
    data = QMimeData()
    data.setData(MIME, QByteArray(json.dumps(list(media_ids)).encode("utf-8")))
    return data


def drag_over(
    arrangement: Arrangement,
    data: QMimeData,
    x: float,
    y: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> bool:
    """Enter and move over the lanes; whether the view would take it.

    The view's handlers are called directly rather than through
    `QApplication.sendEvent`: Qt passes an ignored drag event on up the
    parent chain expecting a real drag in progress, and with only a
    synthesised event there, that crashed the interpreter.
    """
    view = arrangement.panel.view
    point = QPoint(round(x), round(y))
    actions = Qt.DropAction.CopyAction
    buttons = Qt.MouseButton.LeftButton
    view.dragEnterEvent(QDragEnterEvent(point, actions, data, buttons, modifiers))
    move = QDragMoveEvent(point, actions, data, buttons, modifiers)
    view.dragMoveEvent(move)
    return move.isAccepted()


def drop_at(
    arrangement: Arrangement,
    data: QMimeData,
    x: float,
    y: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> bool:
    drag_over(arrangement, data, x, y, modifiers)
    event = QDropEvent(
        QPointF(x, y),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        modifiers,
    )
    arrangement.panel.view.dropEvent(event)
    return event.isAccepted()


def mid(lane: int) -> float:
    return lane * LANE_HEIGHT + LANE_HEIGHT / 2


def test_a_row_dropped_on_a_lane_lands_snapped_in_one_command(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    document = arrangement.document
    before = document.can_undo

    assert drop_at(arrangement, pool_drag(arrangement.media.id), 110, mid(1))

    [clip] = document.project.channels[1].clips
    assert clip.start == 54_000, "52 800 under the pointer, snapped to 1/16"
    assert clip.length == arrangement.media.frames
    document.undo()
    assert document.project.channels[1].clips == []
    assert document.can_undo == before


def test_alt_drops_exactly_under_the_pointer(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    drop_at(
        arrangement,
        pool_drag(arrangement.media.id),
        110,
        mid(0),
        Qt.KeyboardModifier.AltModifier,
    )
    assert arrangement.document.project.channels[0].clips[0].start == 52_800


def test_below_the_last_lane_a_drop_makes_a_channel_and_one_undo_removes_it(
    tmp_path: Path,
) -> None:
    arrangement = Arrangement(tmp_path, channels=2)
    document = arrangement.document
    media = arrangement.media.id

    drop_at(arrangement, pool_drag(media, media), 0, mid(4))

    assert len(document.project.channels) == 3
    assert [clip.start for clip in document.project.channels[2].clips] == [
        0,
        arrangement.media.frames,
    ]
    assert len(arrangement.panel.headers.headers()) == 3
    document.undo()
    assert len(document.project.channels) == 2


def test_a_drop_over_a_clip_trims_it(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    under = arrangement.drop(0, 0)  # two seconds

    drop_at(arrangement, pool_drag(arrangement.media.id), 100, mid(0))  # at 1 s

    assert under.length == SAMPLE_RATE, "trimmed to where the drop begins"
    assert len(arrangement.document.project.channels[0].clips) == 2


def test_shift_over_an_occupied_span_is_refused_before_the_release(
    tmp_path: Path,
) -> None:
    arrangement = Arrangement(tmp_path)
    arrangement.drop(0, 0)
    document = arrangement.document
    before = document.can_undo
    shift = Qt.KeyboardModifier.ShiftModifier

    assert not drag_over(
        arrangement, pool_drag(arrangement.media.id), 100, mid(0), shift
    )
    assert arrangement.panel.view.landing() is None
    assert not drop_at(arrangement, pool_drag(arrangement.media.id), 100, mid(0), shift)
    assert len(document.project.channels[0].clips) == 1
    assert document.can_undo == before
    # Over empty space, Shift has nothing to refuse.
    assert drag_over(arrangement, pool_drag(arrangement.media.id), 100, mid(1), shift)


def test_a_drag_of_anything_else_is_not_taken(tmp_path: Path) -> None:
    arrangement = Arrangement(tmp_path)
    text = QMimeData()
    text.setText("hello")

    assert not drag_over(arrangement, text, 100, mid(0))
    assert not drag_over(arrangement, pool_drag("m-deadbeef"), 100, mid(0))


def test_the_outline_shows_where_it_will_land_until_the_drag_leaves(
    tmp_path: Path,
) -> None:
    arrangement = Arrangement(tmp_path)
    view = arrangement.panel.view

    drag_over(arrangement, pool_drag(arrangement.media.id), 110, mid(1))
    landing = view.landing()
    assert landing is not None and (landing.lane, landing.start) == (1, 54_000)
    drop = theme.group_color("timeline", "drop").upper()
    image = arrangement.grab()
    x = round(54_000 / SCALE)
    assert drop in {
        image.pixelColor(x, y).name().upper()
        for y in range(LANE_HEIGHT, 2 * LANE_HEIGHT)
    }

    from PySide6.QtGui import QDragLeaveEvent

    view.dragLeaveEvent(QDragLeaveEvent())
    assert view.landing() is None
