"""A number that can be dragged or typed, and commits once (04, *Parameters
pane*: "drag-scrubbable and accept typed values with units").

**Two modes, told apart by whether the pointer moved.** At rest the field is
read-only and shows its value with its unit. A press that moves more than a
few pixels scrubs - right or up for more, Shift for a tenth of the rate - and
the release commits. A press that never moves opens the field for typing,
with everything selected; Enter or leaving the field commits what was typed,
and Esc puts back what was there.

**One gesture, one `committed`.** The caller turns that into one command, so
a drag through forty values is one Undo, as *Undo* in 02-architecture.md
asks of every continuous gesture. Hearing a value while it is dragged is the
engine's command ring (M3 phase 8), not a stream of undo entries.

A value outside the range is clamped, and the field shows the clamped value,
which is how it says so. Text that is not a number puts the old value back.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from immersive.ui.units import parse, show

#: How far a press has to move before it is a drag rather than a click.
THRESHOLD = 3

#: What Shift does to the rate of a drag.
FINE = 0.1


class NumericField(QLineEdit):
    """A value between `minimum` and `maximum`, in `unit`, `step` per pixel."""

    #: Once per gesture, with the value it ended on - and only if it changed.
    committed = Signal(float)

    def __init__(
        self,
        value: float,
        *,
        minimum: float,
        maximum: float,
        step: float,
        unit: str = "",
        decimals: int = 1,
        signed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NumericField")
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._unit = unit
        self._decimals = decimals
        self._signed = signed
        self._value = self._clamped(value)
        #: Where a press began and the value it began from, until release.
        self._press: tuple[QPointF, float] | None = None
        self._scrubbing = False
        #: Where the scrub has got to, committed on release.
        self._scrubbed = self._value
        self._rest()

    # ------------------------------------------------------------- reading

    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        """Show `value` without committing it - the model changed, not the
        person. Ignored while someone is typing, whose text wins."""
        self._value = self._clamped(value)
        if self.isReadOnly():
            self.setText(self._shown(self._value))

    # ------------------------------------------------------------ the mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.isReadOnly() and event.button() is Qt.MouseButton.LeftButton:
            self._press = (event.position(), self._value)
            self._scrubbing = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None:
            super().mouseMoveEvent(event)
            return
        start, value = self._press
        moved = event.position() - start
        if not self._scrubbing and abs(moved.x()) + abs(moved.y()) < THRESHOLD:
            return
        self._scrubbing = True
        rate = self._step * (
            FINE if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        )
        # Right is more and up is more, so either direction of drag works.
        self._scrubbed = self._clamped(value + (moved.x() - moved.y()) * rate)
        self.setText(self._shown(self._scrubbed))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._press is None:
            super().mouseReleaseEvent(event)
            return
        self._press = None
        if self._scrubbing:
            self._scrubbing = False
            self._commit(self._scrubbed)
        else:
            self._type()
        event.accept()

    # ---------------------------------------------------------- the keyboard

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.isReadOnly():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._commit(parse(self.text(), self._unit))
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._rest()
                event.accept()
                return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        if not self.isReadOnly():
            self._commit(parse(self.text(), self._unit))
        super().focusOutEvent(event)

    def event(self, event: QEvent) -> bool:
        """At rest the field claims no shortcut: it is a value to drag, not
        text being typed. A read-only line edit still takes `Ctrl+C` for its
        text, and this field keeps its focus after Enter, so without this a
        Copy pressed next would copy "-3.0 dB" rather than the selected clips.
        While it is being typed into it takes what any text field takes."""
        if event.type() == QEvent.Type.ShortcutOverride and self.isReadOnly():
            event.ignore()
            return False
        return super().event(event)

    # ------------------------------------------------------------ internal

    def _type(self) -> None:
        """Open the field for typing, with its value selected to replace."""
        self.setReadOnly(False)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.selectAll()

    def _rest(self) -> None:
        """Back to showing the value, read-only and ready to be dragged."""
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setText(self._shown(self._value))
        self.deselect()

    def _commit(self, typed: float | None) -> None:
        """End the gesture on `typed`, clamped; tell the caller if it changed.
        `None` - text that was not a number - ends it on the old value."""
        before = self._value
        if typed is not None:
            self._value = self._clamped(typed)
        self._rest()
        if self._value != before:
            self.committed.emit(self._value)

    def _clamped(self, value: float) -> float:
        return round(min(max(value, self._minimum), self._maximum), self._decimals)

    def _shown(self, value: float) -> str:
        return show(value, self._unit, decimals=self._decimals, signed=self._signed)
