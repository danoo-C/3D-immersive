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
from typing import Any, TypeVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from immersive.core.commands import Command, Compound
from immersive.core.document import Document
from immersive.core.edits import SetAttribute
from immersive.ui.units import Plain
from immersive.ui.widgets.check import CheckBox
from immersive.ui.widgets.numeric import NumericField

#: Why a field is drawn but dead, by the milestone that brings it.
M4 = "the binaural engine arrives at M4"
M5 = "the spatial views arrive at M5"

#: The tempo's ends and its resolution (D-104).
TEMPO_FLOOR, TEMPO_CEILING = 20.0, 999.0

#: How many beats a bar may have, and which note a beat may be (D-104).
BEATS_FLOOR, BEATS_CEILING = 1, 32
NOTES = (1, 2, 4, 8, 16)

_T = TypeVar("_T")


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


def dead(widget: QWidget, what: str, arrives: str) -> QWidget:
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
        self._form.setHorizontalSpacing(10)
        self._form.setVerticalSpacing(6)
        self._form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 10)
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


class Summary(View):
    """A kind whose view is not built yet: what is selected, and nothing to
    edit. Replaced in the steps that build each."""

    def __init__(self, document: Document, heading: str) -> None:
        super().__init__(document, heading)
