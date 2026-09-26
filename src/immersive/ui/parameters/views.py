"""The pane's views: one for each kind of thing the selection can hold, and
one for the project when it holds nothing (04, *Parameters pane*).

Every view is a form of fields that edit through the document, one command
per gesture, and read the model back in `show_values()` - which commits
nothing, and leaves a field that is being typed into alone, so an edit
elsewhere never throws away what someone is typing.

**Several things at once.** A field shows the value they share, or `—`
where it differs, and a value set there is set on all of them in one edit
(04, *Selection*). A clip's start is the exception, and is the selection's
(D-102).

**Fields a later milestone brings are drawn, disabled**, with that
milestone in their tooltip, as every unbuilt action in the window is.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, TypeVar

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from immersive.core.commands import Command, Compound
from immersive.core.document import Document
from immersive.core.edits import (
    Edge,
    MoveClips,
    SetAttribute,
    SetLengths,
    SlipClips,
    fade_room,
)
from immersive.core.io.peaks import Pyramid
from immersive.core.model import (
    MIN_CLIP_LENGTH,
    Channel,
    Clip,
    Fade,
    FadeShape,
    MediaFile,
    SnapSetting,
)
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.timeline.grid import Unit, snap_text
from immersive.ui.timeline.snap_menu import fill_snap_menu
from immersive.ui.units import Duration, Plain, Position, clock
from immersive.ui.widgets.check import CheckBox
from immersive.ui.widgets.numeric import MIXED, NumericField
from immersive.ui.widgets.waveform import Waveform

#: Why a field is drawn but dead, by the milestone that brings it.
M4 = "the binaural engine arrives at M4"
M5 = "the spatial views arrive at M5"

#: The tempo's ends and its resolution (D-104).
TEMPO_FLOOR, TEMPO_CEILING = 20.0, 999.0

#: How many beats a bar may have, and which note a beat may be (D-104).
BEATS_FLOOR, BEATS_CEILING = 1, 32
NOTES = (1, 2, 4, 8, 16)

#: A clip's gain, as a channel's: below the floor is what mute is for.
GAIN_FLOOR, GAIN_CEILING = -60.0, 12.0

#: The longest time a field on the timeline takes: a day, far past any
#: project, so it is the clip's own limits that stop a value, not the field.
LONGEST = 24 * 60 * 60 * 48_000

#: How far one pixel of drag moves a time: ten milliseconds.
TIME_STEP = 480

#: The fade shapes a clip may have, as the combo box lists them.
SHAPES = {FadeShape.LINEAR: "Linear", FadeShape.EQUAL_POWER: "Equal power"}

_T = TypeVar("_T")
_W = TypeVar("_W", bound=QWidget)


def common(values: Sequence[_T]) -> tuple[bool, _T | None]:
    """Whether `values` all agree, and the value if they do."""
    if not values or any(value != values[0] for value in values[1:]):
        return False, None
    return True, values[0]


def show_number(field: NumericField, values: Sequence[float]) -> None:
    """The value several things share, or `—` where they differ."""
    same, value = common(values)
    if same and value is not None:
        field.set_value(value)
    else:
        field.set_mixed()


def show_check(box: CheckBox, values: Sequence[bool]) -> None:
    same, value = common(values)
    if same:
        box.setChecked(bool(value))
    else:
        box.set_mixed()


def dead(widget: _W, what: str, arrives: str) -> _W:
    """Drawn, disabled, and saying why and until when."""
    widget.setEnabled(False)
    widget.setToolTip(f"{what}\nNot built yet — {arrives}.")
    return widget


def set_on_all(targets: Sequence[Any], name: str, value: object) -> Command | None:
    """`name` set to `value` on every one of `targets` whose value differs -
    one edit however many, or `None` when none would change."""
    changes: list[Command] = [
        SetAttribute(target, name, value)
        for target in targets
        if getattr(target, name) != value
    ]
    if not changes:
        return None
    return changes[0] if len(changes) == 1 else Compound(changes)


class View(QWidget):
    """A heading and a form of fields, for one kind of selection."""

    def __init__(self, document: Document, heading: str) -> None:
        super().__init__()
        self._document = document
        self._heading = QLabel(heading)
        self._heading.setObjectName("PaneHeading")
        self._form = QFormLayout()
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setHorizontalSpacing(8)
        self._form.setVerticalSpacing(6)
        self._form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(8)
        column.addWidget(self._heading)
        column.addLayout(self._form)
        column.addStretch(1)

    def heading(self) -> str:
        return self._heading.text()

    def set_heading(self, text: str) -> None:
        self._heading.setText(text)

    def row(self, label: str, field: QWidget) -> QWidget:
        """A field and its label, in the form's order."""
        name = QLabel(label)
        name.setObjectName("FieldLabel")
        name.setBuddy(field)
        self._form.addRow(name, field)
        return field

    def labels(self) -> list[str]:
        """What the form's rows are called, top to bottom."""
        found = []
        for index in range(self._form.rowCount()):
            item = self._form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                found.append(widget.text())
        return found

    def show_values(self) -> None:
        """Read the model back into every field, committing nothing."""

    def refresh(self) -> None:
        """Show again what a format reads from outside the model - the
        ruler's unit."""
        self.show_values()

    def _push(self, command: Command | None) -> None:
        if command is not None:
            self._document.push(command)
        else:
            # Nothing changed, so nobody will be told: put back what the
            # field showed before it was typed over.
            self.show_values()


def numeric(
    value: float,
    *,
    minimum: float,
    maximum: float,
    step: float,
    unit: str = "",
    decimals: int = 1,
    signed: bool = False,
    tip: str = "",
    committed: Callable[[float], None] | None = None,
) -> NumericField:
    field = NumericField(
        value,
        minimum=minimum,
        maximum=maximum,
        step=step,
        format=Plain(unit, decimals, signed),
        decimals=decimals,
    )
    field.setToolTip(tip)
    if committed is not None:
        field.committed.connect(committed)
    return field


class ProjectView(View):
    """Nothing selected: the project's settings. The tempo and signature are
    live; the HRTF set, distance, master gain and limiter arrive with the
    binaural engine, and are drawn until then."""

    def __init__(self, document: Document) -> None:
        super().__init__(document, "Project")
        project = document.project
        self.tempo = numeric(
            project.bpm,
            minimum=TEMPO_FLOOR,
            maximum=TEMPO_CEILING,
            step=0.1,
            unit="BPM",
            tip="Tempo — drag, or click and type. The grid moves; clips do not.",
            committed=self._set_tempo,
        )
        self.row("Tempo", self.tempo)

        self.beats = numeric(
            project.time_signature[0],
            minimum=BEATS_FLOOR,
            maximum=BEATS_CEILING,
            step=0.05,
            decimals=0,
            tip="Beats in a bar",
            committed=lambda beats: self._set_signature(beats=int(beats)),
        )
        self.note = QComboBox()
        self.note.addItems([str(note) for note in NOTES])
        self.note.setToolTip("The note a beat is")
        self.note.activated.connect(
            lambda index: self._set_signature(note=int(self.note.itemText(index)))
        )
        signature = QWidget()
        line = QHBoxLayout(signature)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(self.beats, 1)
        line.addWidget(QLabel("/"))
        line.addWidget(self.note, 1)
        self.row("Signature", signature)

        self.hrtf = QComboBox()
        self.row(
            "HRTF set",
            dead(self.hrtf, "The HRTF set every channel is heard through", M4),
        )
        self.rolloff = numeric(0, minimum=0, maximum=10, step=0.01, decimals=2)
        self.row(
            "Distance rolloff",
            dead(self.rolloff, "How fast level falls with distance", M4),
        )
        self.master = numeric(
            0, minimum=-60, maximum=12, step=0.1, unit="dB", signed=True
        )
        self.row("Master gain", dead(self.master, "The master bus's gain", M4))
        self.limiter = CheckBox("Limiter")
        self.row("", dead(self.limiter, "The master bus's limiter", M4))

    def show_values(self) -> None:
        project = self._document.project
        self.tempo.set_value(project.bpm)
        beats, note = project.time_signature
        self.beats.set_value(beats)
        if self.note.findText(str(note)) < 0:
            self.note.addItem(str(note))  # a hand-edited file's
        self.note.setCurrentText(str(note))
        self.hrtf.clear()
        self.hrtf.addItem(project.hrtf.id)
        self.rolloff.set_value(project.distance.rolloff)
        self.master.set_value(project.master.gain_db)
        self.limiter.setChecked(project.master.limiter_on)

    def _set_tempo(self, bpm: float) -> None:
        self._push(set_on_all([self._document.project], "bpm", bpm))

    def _set_signature(
        self, *, beats: int | None = None, note: int | None = None
    ) -> None:
        project = self._document.project
        was_beats, was_note = project.time_signature
        signature = (
            beats if beats is not None else was_beats,
            note if note is not None else was_note,
        )
        self._push(set_on_all([project], "time_signature", signature))


class ClipView(View):
    """One clip or several: where each starts, how long it is, where in its
    sample it plays from, its gain, and its fades.

    The start is the selection's - the earliest - and a typed one moves them
    all by the same amount, as a drag does (D-97, D-102). Every other field
    is each clip's own, `—` where they differ, and a value set there goes to
    each as far as that clip can take it: a length stops at the neighbour
    and the sample (D-98), a crop offset at the sample's ends, and a fade at
    the other fade (D-101). The field then shows where the edit landed.
    """

    def __init__(self, document: Document, unit: Callable[[], Unit]) -> None:
        super().__init__(document, "Clip")
        self.source = QLabel()
        self.row("Source", self.source)

        def tempo() -> tuple[float, tuple[int, int]]:
            project = self._document.project
            return project.bpm, project.time_signature

        self.start = self._time(Position(tempo, unit), 0, "Where it starts")
        self.start.committed.connect(self._set_start)
        self.row("Start", self.start)
        self.length = self._time(Duration("s"), MIN_CLIP_LENGTH, "How long it plays")
        self.length.committed.connect(self._set_length)
        self.row("Length", self.length)
        self.offset = self._time(Duration("s"), 0, "Where in its sample it plays from")
        self.offset.committed.connect(self._set_offset)
        self.row("Crop offset", self.offset)
        self.gain = numeric(
            0,
            minimum=GAIN_FLOOR,
            maximum=GAIN_CEILING,
            step=0.1,
            unit="dB",
            signed=True,
            tip="Clip gain — drag, or click and type",
            committed=lambda value: self._push(
                set_on_all(self._clips(), "gain_db", value)
            ),
        )
        self.row("Gain", self.gain)

        self.fade_in, self.fade_in_shape = self._fade(Edge.START)
        self.fade_out, self.fade_out_shape = self._fade(Edge.END)

    # ----------------------------------------------------------- building

    def _time(
        self, format: Duration | Position, minimum: int, tip: str
    ) -> NumericField:
        field = NumericField(
            0,
            minimum=minimum,
            maximum=LONGEST,
            step=TIME_STEP,
            decimals=0,
            format=format,
        )
        field.setToolTip(f"{tip} — drag, or click and type")
        return field

    def _fade(self, edge: Edge) -> tuple[NumericField, QComboBox]:
        name = "Fade in" if edge is Edge.START else "Fade out"
        length = self._time(Duration("ms", decimals=0), 0, f"{name}: how long it lasts")
        length.committed.connect(
            lambda samples: self._set_fade(edge, length=int(samples))
        )
        length.setMinimumWidth(58)
        shape = QComboBox()
        shape.addItems(list(SHAPES.values()))
        shape.setPlaceholderText(MIXED)
        # The pane is narrow: the shape's name may be cut before the length is.
        shape.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        shape.setMinimumContentsLength(3)
        shape.setToolTip(f"{name}: its shape")
        shape.activated.connect(
            lambda index: self._set_fade(edge, shape=list(SHAPES)[index])
        )
        line = QWidget()
        both = QHBoxLayout(line)
        both.setContentsMargins(0, 0, 0, 0)
        both.setSpacing(6)
        both.addWidget(length, 1)
        both.addWidget(shape, 1)
        self.row(name, line)
        return length, shape

    # ------------------------------------------------------------ reading

    def _clips(self) -> list[Clip]:
        return self._document.selection.clips()

    def show_values(self) -> None:
        clips = self._clips()
        if not clips:
            return
        count = len(clips)
        self.set_heading("Clip" if count == 1 else f"{count} clips")
        names = {media.id: media.name for media in self._document.project.media_pool}
        same, media_id = common([clip.media_id for clip in clips])
        self.source.setText(
            names.get(media_id, media_id) if same and media_id is not None else MIXED
        )
        self.start.set_value(min(clip.start for clip in clips))
        show_number(self.length, [clip.length for clip in clips])
        show_number(self.offset, [clip.offset for clip in clips])
        show_number(self.gain, [clip.gain_db for clip in clips])
        for fades, length, shape in (
            ([clip.fade_in for clip in clips], self.fade_in, self.fade_in_shape),
            ([clip.fade_out for clip in clips], self.fade_out, self.fade_out_shape),
        ):
            show_number(length, [fade.length for fade in fades])
            same, chosen = common([fade.shape for fade in fades])
            shape.setCurrentIndex(
                list(SHAPES).index(chosen) if same and chosen is not None else -1
            )

    # ------------------------------------------------------------ editing

    def _set_start(self, start: float) -> None:
        clips = self._clips()
        delta = round(start) - min(clip.start for clip in clips)
        move = MoveClips(self._document.project, clips, delta)
        self._push(move if move.changes else None)

    def _set_length(self, length: float) -> None:
        edit = SetLengths(self._document.project, self._clips(), round(length))
        self._push(edit if edit.changes else None)

    def _set_offset(self, offset: float) -> None:
        edit = SlipClips(self._document.project, self._clips(), round(offset))
        self._push(edit if edit.changes else None)

    def _set_fade(
        self, edge: Edge, *, length: int | None = None, shape: FadeShape | None = None
    ) -> None:
        """The same fade of every clip: a length each as long as its room
        allows (D-101), or a shape. New `Fade`s, since they are mutable and a
        clip's is its own."""
        name = "fade_in" if edge is Edge.START else "fade_out"
        changes: list[Command] = []
        for clip in self._clips():
            fade: Fade = getattr(clip, name)
            wanted = replace(
                fade,
                length=fade.length
                if length is None
                else min(length, fade_room(clip, edge)),
                shape=fade.shape if shape is None else shape,
            )
            if wanted != fade:
                changes.append(SetAttribute(clip, name, wanted))
        self._push(
            None
            if not changes
            else changes[0]
            if len(changes) == 1
            else Compound(changes)
        )


class ChannelView(View):
    """One channel or several: what the header edits - name, colour, gain,
    mute, solo, bypass and snap - and the position and pan that later
    milestones bring, drawn until then.

    The header and the pane read the same channel after every change, so an
    edit in either shows in both. Several channels take every field but the
    name, which reads `—` and is disabled: one name for several channels is
    never wanted, and giving it loses every other name at once.
    """

    def __init__(self, document: Document) -> None:
        super().__init__(document, "Channel")
        self.name = QLineEdit()
        self.name.setObjectName("PaneText")
        self.name.setToolTip("The channel's name — type, then Enter")
        self.name.editingFinished.connect(self._rename)
        self.row("Name", self.name)

        self.colour = QToolButton()
        self.colour.setObjectName("ColourSwatch")
        self.colour.setToolTip("The channel's colour, from the theme's palette")
        self.colour.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.colour.setMenu(QMenu(self.colour))
        self.colour.menu().aboutToShow.connect(self.colour_menu)
        self.row("Colour", self.colour)

        self.gain = numeric(
            0,
            minimum=GAIN_FLOOR,
            maximum=GAIN_CEILING,
            step=0.1,
            unit="dB",
            signed=True,
            tip="Channel gain — drag, or click and type",
            committed=lambda value: self._set("gain_db", value),
        )
        self.row("Gain", self.gain)

        self.mute = CheckBox("Mute")
        self.solo = CheckBox("Solo")
        self.bypass = CheckBox("HRTF bypass")
        self.mute.setToolTip("Mute — mute wins over solo")
        self.solo.setToolTip("Solo — several can be soloed")
        self.bypass.setToolTip(
            "HRTF bypass  (B)\nStraight to the stereo bus, unprocessed — heard at M4"
        )
        for box, name in (
            (self.mute, "mute"),
            (self.solo, "solo"),
            (self.bypass, "hrtf_bypass"),
        ):
            box.clicked.connect(lambda on, name=name: self._set(name, bool(on)))
            self.row("", box)

        self.snap = QToolButton()
        self.snap.setObjectName("PaneSnap")
        self.snap.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.snap.setMenu(QMenu(self.snap))
        self.snap.menu().aboutToShow.connect(self.snap_menu)
        self.row("Snap", self.snap)

        self.position = [
            dead(
                numeric(0, minimum=-100, maximum=100, step=0.01, unit="m", decimals=2),
                f"{axis}: where the channel sits, in metres",
                M5,
            )
            for axis in ("X", "Y", "Z")
        ]
        for axis, field in zip(("X", "Y", "Z"), self.position, strict=True):
            self.row(f"Position {axis}", field)
        self.pan = numeric(0, minimum=-1, maximum=1, step=0.01, decimals=2)
        self._pan_row = self.row(
            "Pan", dead(self.pan, "Left or right, on the bypass path", M4)
        )

    def _channels(self) -> list[Channel]:
        return self._document.selection.channels()

    def show_values(self) -> None:
        channels = self._channels()
        if not channels:
            return
        count = len(channels)
        self.set_heading("Channel" if count == 1 else f"{count} channels")
        if not self.name.hasFocus():
            single = count == 1
            self.name.setEnabled(single)
            self.name.setText(channels[0].name if single else MIXED)
            self.name.setToolTip(
                "The channel's name — type, then Enter"
                if single
                else "Rename one channel at a time"
            )
        same, colour = common([channel.color for channel in channels])
        if same and colour is not None:
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(colour))
            self.colour.setIcon(QIcon(swatch))
            self.colour.setText("")
        else:
            self.colour.setIcon(QIcon())
            self.colour.setText(MIXED)
        show_number(self.gain, [channel.gain_db for channel in channels])
        show_check(self.mute, [channel.mute for channel in channels])
        show_check(self.solo, [channel.solo for channel in channels])
        show_check(self.bypass, [channel.hrtf_bypass for channel in channels])
        same, override = common([channel.snap_override for channel in channels])
        if not same:
            self.snap.setText(MIXED)
        elif override is None:
            self.snap.setText("Follows the project")
        else:
            self.snap.setText(snap_text(override).removeprefix("Snap "))
        for field, values in zip(
            self.position,
            (
                [c.position.x for c in channels],
                [c.position.y for c in channels],
                [c.position.z for c in channels],
            ),
            strict=True,
        ):
            show_number(field, values)
        show_number(self.pan, [channel.pan for channel in channels])
        # 04: pan only when bypassed - it means nothing on the spatial path.
        bypassed = all(channel.hrtf_bypass for channel in channels)
        self.pan.setVisible(bypassed)
        label = self._form.labelForField(self.pan)
        if label is not None:
            label.setVisible(bypassed)

    def colour_menu(self) -> QMenu:
        """The theme's channel palette, the shared colour checked."""
        menu = self.colour.menu()
        menu.clear()
        channels = self._channels()
        for number, colour in enumerate(theme.active().channels, start=1):
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(colour))
            action = QAction(QIcon(swatch), f"Colour {number}", menu)
            action.setCheckable(True)
            action.setChecked(all(c.color.upper() == colour.upper() for c in channels))
            action.triggered.connect(
                lambda _checked=False, colour=colour: self._set("color", colour)
            )
            menu.addAction(action)
        return menu

    def snap_menu(self) -> QMenu:
        """The header's snap menu, for every selected channel: what the first
        one does is checked, and a choice is made for all of them."""
        channels = self._channels()
        project = self._document.project
        override = channels[0].snap_override if channels else None

        def choose(chosen: SnapSetting | None) -> None:
            self._set("snap_override", chosen)

        return fill_snap_menu(
            self.snap.menu(),
            override if override is not None else project.snap,
            choose,
            following=override is None,
        )

    def _set(self, name: str, value: object) -> None:
        self._push(set_on_all(self._channels(), name, value))

    def _rename(self) -> None:
        channels = self._channels()
        text = self.name.text().strip()
        if len(channels) == 1 and text:
            self._set("name", text)
        else:
            self.show_values()


class Elided(QLabel):
    """One line, cut in the middle to fit rather than run past the pane's
    edge - a path's two ends are the parts worth reading. The tooltip has
    all of it."""

    def __init__(self) -> None:
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def full(self) -> str:
        return self._full

    def set_full(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.setText(text)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.fontMetrics().elidedText(
                    self._full, Qt.TextElideMode.ElideMiddle, self.width()
                ),
            )
        finally:
            painter.end()


class MediaView(View):
    """One sample or several: where its file is, what it was before
    resampling, how long it is, and all of it drawn. The audition button
    plays it straight to the output, or says why it cannot (F-8)."""

    def __init__(
        self,
        document: Document,
        peaks: Callable[[str], Pyramid | None],
        audition: Callable[[str], bool] | None,
        unavailable: str,
    ) -> None:
        super().__init__(document, "Sample")
        self._peaks = peaks
        self._audition = audition
        self._unavailable = unavailable
        self.path = Elided()
        self.row("Path", self.path)
        self.rate = QLabel()
        self.row("Source rate", self.rate)
        self.channels = QLabel()
        self.row("Channels", self.channels)
        self.length = QLabel()
        self.row("Duration", self.length)
        self.waveform = Waveform()
        self.waveform.setMinimumHeight(64)
        self.row("", self.waveform)
        self.hear = QToolButton()
        self.hear.setObjectName("Audition")
        self.hear.setText("Audition")
        self.hear.clicked.connect(self._hear)
        self.row("", self.hear)

    def _media(self) -> list[MediaFile]:
        return self._document.selection.media()

    def show_values(self) -> None:
        media = self._media()
        if not media:
            return
        count = len(media)
        self.set_heading(media[0].name if count == 1 else f"{count} samples")

        def shared(values: Sequence[object], shown: Callable[[Any], str]) -> str:
            same, value = common(list(values))
            return shown(value) if same else MIXED

        self.path.set_full(shared([m.path for m in media], str))
        self.rate.setText(
            shared(
                [m.source_rate for m in media],
                lambda rate: f"{rate:,} Hz".replace(",", " "),
            )
        )
        self.channels.setText(
            shared(
                [m.channels for m in media],
                lambda n: {1: "Mono", 2: "Stereo"}.get(n, str(n)),
            )
        )
        self.length.setText(shared([m.frames for m in media], duration_of))
        one = media[0] if count == 1 else None
        self.waveform.setVisible(one is not None)
        if one is not None:
            self.waveform.set_peaks(self._peaks(one.id), missing=one.missing)

        why = ""
        if count != 1:
            why = "Select one sample to hear it"
        elif one is not None and one.missing:
            why = "Its file is missing"
        elif self._audition is None:
            why = f"Cannot be heard: {self._unavailable or 'no audio output'}"
        self.hear.setEnabled(not why)
        self.hear.setToolTip(why or "Play it straight to the output")

    def _hear(self) -> None:
        media = self._media()
        if self._audition is not None and len(media) == 1:
            self._audition(media[0].id)


def duration_of(frames: int) -> str:
    """A sample's whole length, with the room the pool's column lacks:
    `1.400 s`, or `3:12.500` from a minute on."""
    if frames < 60 * SAMPLE_RATE:
        return Duration("s").show(frames)
    return clock(frames)
