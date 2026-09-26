"""The parameters pane: following the selection, and the project's settings,
the clip's, the channel's and the sample's fields. Marked gui."""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.peaks import build
from immersive.core.model import (
    Clip,
    Fade,
    FadeShape,
    MediaFile,
    SnapSetting,
    new_channel,
)
from immersive.core.selection import Kind
from immersive.core.time import SAMPLE_RATE, Division, to_bar_beat
from immersive.ui import theme
from immersive.ui.main_window import COMMON_SIGNATURES, MainWindow
from immersive.ui.parameters.pane import ParametersPane
from immersive.ui.parameters.views import (
    ChannelView,
    ClipView,
    MediaView,
    ProjectView,
    duration_of,
)
from immersive.ui.timeline.grid import Unit
from immersive.ui.timeline.headers import ChannelHeader
from immersive.ui.widgets.numeric import MIXED, NumericField

pytestmark = pytest.mark.gui

SECOND = SAMPLE_RATE
MEDIA = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10 * SECOND)
#: A bar at 120 BPM in 4/4: four half-second beats.
BAR = 2 * SECOND


@pytest.fixture(autouse=True)
def _application() -> Iterator[None]:
    build_application([])
    yield


def arrange(document: Document, lanes: int = 2) -> list[list[Clip]]:
    """`lanes` channels, each with clips a second long at 0, 2 and 4 s."""
    document.push(AddMedia(document.project, [MEDIA]))
    grid = []
    for lane in range(lanes):
        project = document.project
        document.push(
            AddChannel(project, new_channel(project, theme.active().channels))
        )
        clips = [
            Clip(f"k-000{lane}{n}000", MEDIA.id, n * 2 * SECOND, 0, SECOND)
            for n in range(3)
        ]
        document.push(DropClips(project, project.channels[lane], clips))
        grid.append(clips)
    return grid


def a_window(lanes: int = 2) -> tuple[MainWindow, list[list[Clip]]]:
    window = MainWindow()
    grid = arrange(window.document(), lanes)
    window.show()
    QApplication.processEvents()
    return window, grid


def finish(window: MainWindow, timeout: float = 20.0) -> None:
    """Until the workers preparing samples are done, and their results in."""
    deadline = time.monotonic() + timeout
    while window.importing():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError("the samples did not finish loading")
    QApplication.processEvents()


def stacked(window: MainWindow) -> int:
    return len(window.document()._stack)


def press(field: NumericField) -> None:
    """A click that never moved: it opens the field for typing."""
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            field,
            QMouseEvent(
                kind,
                QPointF(20, 8),
                field.mapToGlobal(QPointF(20, 8)),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )


def type_into(field: NumericField, text: str) -> None:
    press(field)
    field.selectAll()
    QTest.keyClicks(field, text)
    QTest.keyClick(field, Qt.Key.Key_Return)


def project_view(window: MainWindow) -> ProjectView:
    view = window.parameters().view()
    assert isinstance(view, ProjectView)
    return view


# --------------------------------------------------------------------------- #
# following the selection
# --------------------------------------------------------------------------- #


def test_the_pane_follows_the_selections_kind() -> None:
    window, grid = a_window()
    document, pane = window.document(), window.parameters()
    assert pane.view().heading() == "Project"

    document.selection.select(Kind.CLIPS, [grid[0][0]])
    assert not isinstance(pane.view(), ProjectView)
    document.selection.select(Kind.CHANNELS, document.project.channels[:1])
    assert not isinstance(pane.view(), ProjectView)
    document.selection.select(Kind.MEDIA, document.project.media_pool)
    assert not isinstance(pane.view(), ProjectView)
    document.selection.clear()
    assert isinstance(pane.view(), ProjectView)


def test_the_view_is_rebuilt_only_when_the_kind_changes() -> None:
    window, grid = a_window()
    document, pane = window.document(), window.parameters()
    document.selection.select(Kind.CLIPS, [grid[0][0]])
    view = pane.view()

    document.selection.select(Kind.CLIPS, [grid[1][2]])
    document.push(SetAttribute(document.project.channels[0], "name", "Kick"))

    assert pane.view() is view


def test_a_value_being_typed_survives_an_edit_elsewhere() -> None:
    window, _ = a_window()
    document = window.document()
    tempo = project_view(window).tempo
    press(tempo)
    tempo.selectAll()
    QTest.keyClicks(tempo, "133")

    document.push(SetAttribute(document.project.channels[0], "name", "Kick"))

    assert tempo.text() == "133"
    QTest.keyClick(tempo, Qt.Key.Key_Return)
    assert document.project.bpm == 133.0


# --------------------------------------------------------------------------- #
# the project's settings
# --------------------------------------------------------------------------- #


def test_a_tempo_from_the_pane_is_one_undo_and_the_toolbar_follows() -> None:
    window, _ = a_window()
    document = window.document()
    count = stacked(window)

    type_into(project_view(window).tempo, "96.5 BPM")

    assert document.project.bpm == 96.5 and stacked(window) == count + 1
    assert window._tempo.text() == "96.5 BPM"
    document.undo()
    assert project_view(window).tempo.text() == window._tempo.text() == "120.0 BPM"


def test_a_tempo_from_the_toolbar_is_one_undo_and_the_pane_follows() -> None:
    window, _ = a_window()
    document = window.document()
    count = stacked(window)

    type_into(window._tempo, "140")

    assert document.project.bpm == 140.0 and stacked(window) == count + 1
    assert project_view(window).tempo.text() == "140.0 BPM"


@pytest.mark.parametrize(("typed", "landed"), [("5", 20.0), ("5000 BPM", 999.0)])
def test_a_tempo_out_of_range_lands_at_its_end_and_says_so(
    typed: str, landed: float
) -> None:
    """D-104: the field shows where it landed, which is how it says so."""
    window, _ = a_window()
    tempo = project_view(window).tempo
    type_into(tempo, typed)
    assert window.document().project.bpm == landed
    assert tempo.text() == f"{landed:.1f} BPM"


def test_the_same_tempo_typed_again_is_no_edit() -> None:
    window, _ = a_window()
    count = stacked(window)
    type_into(project_view(window).tempo, "120")
    assert stacked(window) == count
    assert project_view(window).tempo.text() == "120.0 BPM"


def test_the_signature_from_the_pane_is_one_undo_each_and_the_toolbar_follows() -> None:
    window, _ = a_window()
    document, view = window.document(), project_view(window)
    count = stacked(window)

    type_into(view.beats, "7")
    view.note.activated.emit(view.note.findText("8"))

    assert document.project.time_signature == (7, 8)
    assert stacked(window) == count + 2
    assert window._signature_chip.text() == "7/8"
    document.undo()
    assert document.project.time_signature == (7, 4)
    assert (view.beats.text(), view.note.currentText()) == ("7", "4")


def test_choosing_the_note_already_set_is_no_edit() -> None:
    window, _ = a_window()
    view = project_view(window)
    count = stacked(window)
    view.note.activated.emit(view.note.findText("4"))
    assert stacked(window) == count


def test_the_signatures_beats_stop_at_one_and_thirty_two() -> None:
    window, _ = a_window()
    type_into(project_view(window).beats, "40")
    assert window.document().project.time_signature == (32, 4)
    type_into(project_view(window).beats, "0")
    assert window.document().project.time_signature == (1, 4)


def test_the_note_offers_only_note_values() -> None:
    """D-104: 1, 2, 4, 8 or 16."""
    window, _ = a_window()
    note = project_view(window).note
    assert [note.itemText(i) for i in range(note.count())] == ["1", "2", "4", "8", "16"]


def test_the_toolbars_signature_menu_offers_the_common_ones() -> None:
    window, _ = a_window()
    document = window.document()
    menu = window.signature_menu()
    texts = [action.text() for action in menu.actions()]
    assert texts == ["{}/{}".format(*signature) for signature in COMMON_SIGNATURES]
    assert [a.text() for a in menu.actions() if a.isChecked()] == ["4/4"]
    count = stacked(window)

    [six_eight] = [a for a in menu.actions() if a.text() == "6/8"]
    six_eight.trigger()

    assert document.project.time_signature == (6, 8) and stacked(window) == count + 1
    view = project_view(window)
    assert (view.beats.text(), view.note.currentText()) == ("6", "8")


def test_a_tempo_change_moves_the_grid_and_no_clip() -> None:
    """D-52: the material stays where it is in time; the bars move over it."""
    window, grid = a_window()
    document = window.document()
    clip = grid[0][2]
    before = (clip.start, to_bar_beat(clip.start, 120.0, (4, 4)))

    type_into(project_view(window).tempo, "90")

    assert clip.start == before[0]
    assert to_bar_beat(clip.start, document.project.bpm, (4, 4)) != before[1]


def test_the_engines_fields_are_drawn_dead_and_name_m4() -> None:
    window, _ = a_window()
    view = project_view(window)
    for field in (view.hrtf, view.rolloff, view.master, view.limiter):
        assert not field.isEnabled()
        assert "M4" in field.toolTip()
    project = window.document().project
    assert view.hrtf.currentText() == project.hrtf.id
    assert view.limiter.isChecked() == project.master.limiter_on


def test_the_toolbars_tempo_and_signature_stay_out_of_the_focus_chain() -> None:
    """As the snap chip does, or the window opens with a ring around one."""
    window, _ = a_window()
    assert window._tempo.focusPolicy() is Qt.FocusPolicy.ClickFocus
    assert window._signature_chip.focusPolicy() is Qt.FocusPolicy.NoFocus


# --------------------------------------------------------------------------- #
# collapsing
# --------------------------------------------------------------------------- #


def test_collapsing_gives_the_room_to_the_pool_and_opening_takes_it_back() -> None:
    window, _ = a_window()
    window.resize(1500, 950)
    QApplication.processEvents()
    pane = window.parameters()
    splitter = pane.parentWidget()
    assert isinstance(splitter, QSplitter)
    pool, open_height = splitter.sizes()
    assert "▾" in pane.header().text()

    QTest.mouseClick(pane.header(), Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert pane.collapsed() and "▸" in pane.header().text()
    assert splitter.sizes()[1] <= pane.header().sizeHint().height()
    assert splitter.sizes()[0] > pool

    QTest.mouseClick(pane.header(), Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert not pane.collapsed()
    assert splitter.sizes()[1] == open_height


# --------------------------------------------------------------------------- #
# the clip view
# --------------------------------------------------------------------------- #


def clip_view(window: MainWindow) -> ClipView:
    view = window.parameters().view()
    assert isinstance(view, ClipView)
    return view


def a_clip_selected(
    *clips_of: tuple[int, int],
) -> tuple[MainWindow, list[list[Clip]], ClipView]:
    window, grid = a_window()
    chosen = [grid[lane][n] for lane, n in clips_of or ((0, 0),)]
    window.document().selection.select(Kind.CLIPS, chosen)
    return window, grid, clip_view(window)


def test_a_clip_shows_its_source_start_length_offset_gain_and_fades() -> None:
    window, grid = a_window()
    clip = grid[0][1]
    clip.offset, clip.gain_db = SECOND // 4, -3.0
    clip.fade_in = Fade(4_800)
    clip.fade_out = Fade(9_600, FadeShape.EQUAL_POWER)
    window.document().selection.select(Kind.CLIPS, [clip])
    view = clip_view(window)

    assert view.labels() == [
        "Source",
        "Start",
        "Length",
        "Crop offset",
        "Gain",
        "Fade in",
        "Fade out",
    ]
    assert view.heading() == "Clip" and view.source.text() == "a.wav"
    assert [
        f.text()
        for f in (view.start, view.length, view.offset, view.gain, view.fade_in)
    ] == ["2.1.000", "1.000 s", "0.250 s", "-3.0 dB", "100 ms"]
    assert (view.fade_out.text(), view.fade_out_shape.currentText()) == (
        "200 ms",
        "Equal power",
    )


@pytest.mark.parametrize(
    ("field", "typed", "expected"),
    [
        ("start", "3.1.000", ("start", 2 * BAR)),
        ("length", "0.5 s", ("length", SECOND // 2)),
        ("offset", "250 ms", ("offset", SECOND // 4)),
        ("gain", "-6 dB", ("gain_db", -6.0)),
    ],
)
def test_each_clip_field_is_one_undo(
    field: str, typed: str, expected: tuple[str, object]
) -> None:
    window, grid, view = a_clip_selected((0, 0))
    document, clip = window.document(), grid[0][0]
    before, count = copy.deepcopy(document.project), stacked(window)

    type_into(getattr(view, field), typed)

    name, value = expected
    assert getattr(clip, name) == value
    assert stacked(window) == count + 1
    document.undo()
    assert document.project == before


def test_the_clip_in_the_timeline_follows_the_pane() -> None:
    window, grid, view = a_clip_selected((0, 0))
    clip = grid[0][0]
    type_into(view.start, "0:06")
    [item] = [i for i in window.timeline().view.clip_items() if i.clip is clip]
    assert item.pos().x() == 6 * SECOND / window.timeline().axis.scale


@pytest.mark.parametrize("edge", ["in", "out"])
def test_a_fades_length_and_shape_are_each_one_undo(edge: str) -> None:
    window, grid, view = a_clip_selected((0, 0))
    clip, count = grid[0][0], stacked(window)
    length = view.fade_in if edge == "in" else view.fade_out
    shape = view.fade_in_shape if edge == "in" else view.fade_out_shape

    type_into(length, "100 ms")
    shape.activated.emit(1)

    fade = clip.fade_in if edge == "in" else clip.fade_out
    assert fade == Fade(4_800, FadeShape.EQUAL_POWER)
    assert stacked(window) == count + 2


def test_several_clips_show_a_dash_where_they_differ() -> None:
    window, grid = a_window()
    grid[1][1].gain_db = -6.0
    grid[1][1].fade_out = Fade(480, FadeShape.EQUAL_POWER)
    window.document().selection.select(Kind.CLIPS, [grid[0][2], grid[1][1]])
    view = clip_view(window)

    assert view.heading() == "2 clips"
    assert view.start.text() == "2.1.000", "the selection's start, the earliest"
    assert view.length.text() == "1.000 s", "the same for both"
    assert view.gain.text() == view.fade_out.text() == MIXED
    assert view.fade_out_shape.currentIndex() == -1
    assert view.fade_out_shape.currentText() == ""
    assert view.fade_out_shape.placeholderText() == MIXED


def test_a_value_set_over_a_dash_goes_to_every_clip_in_one_edit() -> None:
    window, grid = a_window()
    grid[1][1].gain_db = -6.0
    chosen = [grid[0][2], grid[1][1], grid[1][2]]
    window.document().selection.select(Kind.CLIPS, chosen)
    count = stacked(window)

    type_into(clip_view(window).gain, "-3")
    clip_view(window).fade_out_shape.activated.emit(1)

    assert [clip.gain_db for clip in chosen] == [-3.0] * 3
    assert {clip.fade_out.shape for clip in chosen} == {FadeShape.EQUAL_POWER}
    assert stacked(window) == count + 2
    window.document().undo()
    window.document().undo()
    assert [clip.gain_db for clip in chosen] == [0.0, -6.0, 0.0]


def test_the_start_moves_the_selection_and_keeps_its_shape() -> None:
    """D-102: not every clip to one start, which on one lane would leave one."""
    window, grid, view = a_clip_selected((0, 0), (0, 1), (1, 2))
    count = stacked(window)

    type_into(view.start, "0:10")

    assert [grid[0][0].start, grid[0][1].start, grid[1][2].start] == [
        10 * SECOND,
        12 * SECOND,
        14 * SECOND,
    ]
    assert stacked(window) == count + 1
    assert view.start.text() == "6.1.000"


def test_a_length_past_the_neighbour_lands_at_the_neighbour_and_says_so() -> None:
    _window, grid, view = a_clip_selected((0, 0))
    type_into(view.length, "5 s")
    assert grid[0][0].length == 2 * SECOND, "the next clip starts at 2 s"
    assert view.length.text() == "2.000 s"


def test_a_length_that_cannot_change_is_no_edit_and_is_put_back() -> None:
    window, _grid, view = a_clip_selected((0, 0))
    type_into(view.length, "5 s")
    count = stacked(window)

    type_into(view.length, "9 s")

    assert stacked(window) == count
    assert view.length.text() == "2.000 s"


def test_a_crop_offset_stops_at_the_samples_end() -> None:
    _window, grid, view = a_clip_selected((0, 0))
    type_into(view.offset, "20 s")
    assert grid[0][0].offset == 9 * SECOND, "a ten-second sample, a one-second clip"
    assert grid[0][0].start == 0 and view.offset.text() == "9.000 s"


def test_a_fade_stops_where_the_other_begins() -> None:
    """D-101."""
    _window, grid, view = a_clip_selected((0, 0))
    type_into(view.fade_out, "600 ms")
    type_into(view.fade_in, "800 ms")
    assert (grid[0][0].fade_in.length, grid[0][0].fade_out.length) == (
        SECOND * 4 // 10,
        SECOND * 6 // 10,
    )
    assert view.fade_in.text() == "400 ms"


def test_the_start_reads_as_the_ruler_counts() -> None:
    window, _, view = a_clip_selected((0, 1))
    assert view.start.text() == "2.1.000"
    window.set_ruler_unit(Unit.TIME)
    assert view.start.text() == "0:02.000"
    type_into(view.start, "3.5")
    assert view.start.text() == "0:03.500"


def test_the_start_reads_the_new_bars_after_a_tempo_change() -> None:
    window, _, view = a_clip_selected((0, 1))
    window.document().push(SetAttribute(window.document().project, "bpm", 60.0))
    assert view.start.text() == "1.3.000"


# --------------------------------------------------------------------------- #
# the channel view
# --------------------------------------------------------------------------- #


def channel_view(window: MainWindow) -> ChannelView:
    view = window.parameters().view()
    assert isinstance(view, ChannelView)
    return view


def channels_selected(*lanes: int) -> tuple[MainWindow, ChannelView]:
    window, _ = a_window(lanes=3)
    channels = window.document().project.channels
    window.document().selection.select(Kind.CHANNELS, [channels[n] for n in lanes])
    return window, channel_view(window)


def header(window: MainWindow, lane: int) -> ChannelHeader:
    return window.timeline().headers.headers()[lane]


def test_a_channel_shows_what_its_header_edits_and_what_comes_later() -> None:
    window, view = channels_selected(1)
    assert view.labels() == [
        "Name",
        "Colour",
        "Gain",
        "",
        "",
        "",
        "Snap",
        "Position X",
        "Position Y",
        "Position Z",
        "Pan",
    ]
    channel = window.document().project.channels[1]
    assert view.heading() == "Channel" and view.name.text() == channel.name
    assert (view.gain.text(), view.snap.text()) == ("0.0 dB", "Follows the project")
    assert [box.text() for box in (view.mute, view.solo, view.bypass)] == [
        "Mute",
        "Solo",
        "HRTF bypass",
    ]


def test_each_channel_field_is_one_undo_and_the_header_follows() -> None:
    window, view = channels_selected(0)
    count = stacked(window)

    type_into(view.gain, "-4.5")
    view.mute.click()
    view.name.setText("Kick")
    view.name.editingFinished.emit()
    [second] = [a for a in view.colour_menu().actions() if a.text() == "Colour 2"]
    second.trigger()
    [eighth] = [a for a in view.snap_menu().actions() if a.text() == "1/8"]
    eighth.trigger()

    assert stacked(window) == count + 5
    shown = header(window, 0)
    assert shown.gain.text() == "-4.5 dB" and shown.mute.isChecked()
    assert shown.name.text() == "Kick"
    assert shown.chip.colour() == theme.active().channels[1]
    assert shown.snap.text() == "1/8" and view.snap.text() == "1/8"


def test_an_edit_in_the_header_shows_in_the_pane() -> None:
    window, view = channels_selected(0)
    header(window, 0).solo.click()
    header(window, 0).gain.committed.emit(3.0)
    assert view.solo.isChecked() and view.gain.text() == "+3.0 dB"


def test_several_channels_take_a_value_as_one_edit_and_not_a_name() -> None:
    window, view = channels_selected(0, 2)
    document = window.document()
    channels = document.project.channels
    document.push(SetAttribute(channels[2], "mute", True))
    count = stacked(window)

    assert view.heading() == "2 channels"
    assert not view.name.isEnabled() and view.name.text() == MIXED
    assert view.mute.mixed()

    view.mute.click()
    type_into(view.gain, "-2")

    assert (channels[0].mute, channels[1].mute, channels[2].mute) == (True, False, True)
    assert channels[0].gain_db == channels[2].gain_db == -2.0 != channels[1].gain_db
    assert stacked(window) == count + 2


def test_a_name_left_empty_is_put_back() -> None:
    window, view = channels_selected(0)
    before, count = view.name.text(), stacked(window)
    view.name.setText("   ")
    view.name.editingFinished.emit()
    assert stacked(window) == count and view.name.text() == before


def test_position_is_dead_until_m5_and_pan_shows_only_when_bypassed() -> None:
    _window, view = channels_selected(0)
    for field in view.position:
        assert not field.isEnabled() and "M5" in field.toolTip()
    assert view.pan.isHidden()

    view.bypass.click()

    assert not view.pan.isHidden() and not view.pan.isEnabled()
    assert "M4" in view.pan.toolTip()


# --------------------------------------------------------------------------- #
# the sample view
# --------------------------------------------------------------------------- #


def a_pane(
    media: list[MediaFile],
    *,
    heard: list[str] | None = None,
    unavailable: str = "",
) -> tuple[Document, ParametersPane]:
    document = Document()
    document.push(AddMedia(document.project, media))
    audio = np.linspace(-1, 1, 4_800, dtype=np.float32).reshape(-1, 1)

    def hear(media_id: str) -> bool:
        assert heard is not None
        heard.append(media_id)
        return True

    pane = ParametersPane(
        document,
        unit=lambda: Unit.BARS,
        peaks=lambda _media_id: build(audio),
        audition=None if heard is None else hear,
        unavailable=unavailable,
    )
    pane.resize(250, 400)
    pane.show()
    return document, pane


STEREO = MediaFile(
    "m-00000002", "/samples/drums/Kick.wav", "Kick.wav", 44_100, 2, 3 * SECOND // 2
)


def test_a_sample_shows_its_file_its_facts_and_its_waveform() -> None:
    document, pane = a_pane([STEREO], heard=[])
    document.selection.select(Kind.MEDIA, [STEREO])
    view = pane.view()
    assert isinstance(view, MediaView)

    assert view.heading() == "Kick.wav"
    assert view.path.full() == STEREO.path and view.path.toolTip() == STEREO.path
    assert (view.rate.text(), view.channels.text(), view.length.text()) == (
        "44 100 Hz",
        "Stereo",
        "1.500 s",
    )
    assert view.waveform.isVisibleTo(view) and view.waveform._pyramid is not None


def test_the_audition_button_plays_the_sample() -> None:
    heard: list[str] = []
    document, pane = a_pane([STEREO], heard=heard)
    document.selection.select(Kind.MEDIA, [STEREO])
    view = pane.view()
    assert isinstance(view, MediaView)
    assert view.hear.isEnabled()
    view.hear.click()
    assert heard == [STEREO.id]


def test_the_audition_button_says_why_it_cannot_play() -> None:
    gone = MediaFile("m-00000003", "/gone.wav", "gone.wav", SAMPLE_RATE, 1, SECOND)
    gone.missing = True
    document, pane = a_pane([STEREO, gone], unavailable="PortAudio is not installed")
    for chosen, why in (
        ([STEREO], "Cannot be heard: PortAudio is not installed"),
        ([STEREO, gone], "Select one sample to hear it"),
    ):
        document.selection.select(Kind.MEDIA, chosen)
        view = pane.view()
        assert isinstance(view, MediaView)
        assert not view.hear.isEnabled() and view.hear.toolTip() == why

    document, pane = a_pane([gone], heard=[])
    document.selection.select(Kind.MEDIA, [gone])
    view = pane.view()
    assert isinstance(view, MediaView)
    assert view.hear.toolTip() == "Its file is missing" and not view.hear.isEnabled()


def test_several_samples_show_what_they_share() -> None:
    other = MediaFile("m-00000004", "/b.wav", "b.wav", 44_100, 1, 90 * SECOND)
    document, pane = a_pane([STEREO, other])
    document.selection.select(Kind.MEDIA, [STEREO, other])
    view = pane.view()
    assert isinstance(view, MediaView)
    assert view.heading() == "2 samples"
    assert (view.rate.text(), view.channels.text(), view.length.text()) == (
        "44 100 Hz",
        MIXED,
        MIXED,
    )
    assert not view.waveform.isVisibleTo(view)


def test_a_long_sample_reads_in_minutes() -> None:
    assert duration_of(90 * SECOND + SECOND // 2) == "1:30.500"
    assert duration_of(SECOND * 3 // 2) == "1.500 s"


def test_a_rename_ended_after_a_second_channel_is_selected_renames_nothing() -> None:
    """The field reads `—` once two are selected; ending the edit then must
    not give both channels that name."""
    window, view = channels_selected(0)
    channels = window.document().project.channels
    names = [channel.name for channel in channels]
    view.name.setText("Kick")
    window.document().selection.add(Kind.CHANNELS, [channels[1]])

    view.name.editingFinished.emit()

    assert [channel.name for channel in channels] == names


def test_a_name_being_typed_survives_an_edit_elsewhere() -> None:
    window, view = channels_selected(0)
    window.activateWindow()
    view.name.setFocus()
    QApplication.processEvents()
    assert view.name.hasFocus()
    view.name.setText("Kic")

    window.document().push(SetAttribute(window.document().project, "bpm", 99.0))

    assert view.name.text() == "Kic"
    view.name.clearFocus()  # ends the edit while the window is still here
    assert window.document().project.channels[0].name == "Kic"


def test_the_colour_menu_checks_only_a_colour_every_channel_has() -> None:
    window, view = channels_selected(0, 1)
    checked = [a.text() for a in view.colour_menu().actions() if a.isChecked()]
    assert checked == [], "two channels, two colours"
    channels = window.document().project.channels
    window.document().push(SetAttribute(channels[1], "color", channels[0].color))
    checked = [a.text() for a in view.colour_menu().actions() if a.isChecked()]
    assert checked == ["Colour 1"]


def test_the_snap_menu_shows_a_channels_own_setting() -> None:
    window, view = channels_selected(0)
    channel = window.document().project.channels[0]
    window.document().push(
        SetAttribute(channel, "snap_override", SnapSetting(division=Division.EIGHTH))
    )
    checked = [a.text() for a in view.snap_menu().actions() if a.isChecked()]
    assert checked == ["1/8"]


def test_a_sample_selected_while_its_file_loads_is_drawn_once_it_has(
    tmp_path: Path,
) -> None:
    """Opening a project loads its samples on workers; the pane is told
    when their peaks arrive, as the timeline is."""
    wav = tmp_path / "tone.wav"
    soundfile.write(wav, np.sin(np.linspace(0, 400, SECOND)).astype("float32"), SECOND)
    window = MainWindow()
    window.import_paths([wav])
    finish(window)
    window.document().save_as(tmp_path / "a.3dim")

    window.open_project(tmp_path / "a.3dim")
    window.document().selection.select(Kind.MEDIA, window.document().project.media_pool)
    view = window.parameters().view()
    assert isinstance(view, MediaView) and view.waveform._pyramid is None

    finish(window)

    assert view.waveform._pyramid is not None
