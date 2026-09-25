"""The channel headers: one per lane, down the left of the timeline.

Each header is a small frame of real controls - the colour chip, the name,
the gain, M, S and HRTF bypass, and the snap indicator (04, *Timeline*) -
and every one of them edits the channel through the document, one command
per gesture.

**The column is placed, not scrolled.** Each header sits at its lane's y
minus the view's vertical scroll value, read from the view's own scrollbar.
Two scroll areas kept in step would need their ranges to match, and they do
not: the lanes have a horizontal scrollbar beneath them and the headers do
not. One value read by both cannot disagree - the reasoning D-94 used for
the ruler, on the other axis.

**Headers are updated in place, and rebuilt only when the list changes.**
After every change the document reports, the column compares the channels
it shows with the project's, by identity. The same channels in the same
order re-read themselves; anything else rebuilds the column. Rebuilding on
every change would throw away a gain someone is in the middle of typing
whenever anything else in the project changed.

Colours come from the `channel` group in the stylesheet, except the chip,
which is the channel's own colour: data, stored in the project, like a
waveform's samples.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFocusEvent,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from immersive.core.document import Document
from immersive.core.edits import MoveChannel, RemoveChannel, SetAttribute
from immersive.core.model import Channel, Project, audible, effective_snap
from immersive.ui import theme
from immersive.ui.timeline.grid import snap_text
from immersive.ui.timeline.metrics import LANE_HEIGHT
from immersive.ui.timeline.view import TimelineView
from immersive.ui.widgets.numeric import NumericField

#: The headers column's width, and so the corner's above it.
HEADER_WIDTH = 220

#: Channel gain in dB. Below the floor is what mute is for, and a fader that
#: reaches minus infinity spends its most-used range in its last pixels.
GAIN_FLOOR = -60.0
GAIN_CEILING = 12.0

#: What a channel silenced by somebody else's solo says, beside its name -
#: never by colour alone (04, *Accessibility and feel*).
SILENCED = "silenced"


#: How far a press on a header has to move before it is a drag.
DRAG_THRESHOLD = 4


class Chip(QWidget):
    """The channel's colour, as a small square. A click offers the palette."""

    SIZE = 12
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        #: The channel's colour, from the project; nothing is drawn until
        #: there is one.
        self._colour: str | None = None

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.update()

    def colour(self) -> str | None:
        return self._colour

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._colour is None:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._colour))
            painter.drawRoundedRect(QRect(0, 0, self.SIZE, self.SIZE), 3, 3)
        finally:
            painter.end()


class Name(QLabel):
    """The channel's name, ending in an ellipsis when the header is too
    narrow for it rather than cut through a letter and into the controls
    beside it. `text()` is still the whole name; so is the tooltip. A
    double-click asks for it to be renamed."""

    renaming = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        # Take what is left of the row, and no more.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            self.renaming.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def shown(self) -> str:
        """What is drawn: the name, or as much of it as fits and an ellipsis."""
        return self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width()
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            self.style().drawItemText(
                painter,
                self.contentsRect(),
                int(self.alignment()),
                self.palette(),
                self.isEnabled(),
                self.shown(),
                QPalette.ColorRole.WindowText,
            )
        finally:
            painter.end()


class RenameField(QLineEdit):
    """The name, open for typing in place. Enter or leaving it keeps what
    was typed; Esc keeps nothing. Either way it says so once."""

    finished = Signal(object)  # the new name, or None for Esc

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ChannelRename")
        self._done = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(self.text())
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._finish(self.text())
        super().focusOutEvent(event)

    def _finish(self, text: str | None) -> None:
        if not self._done:
            self._done = True
            self.finished.emit(text)


class ChannelHeader(QFrame):
    """One channel's header. It edits the channel only through the document,
    one command per gesture."""

    def __init__(
        self,
        channel: Channel,
        document: Document,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ChannelHeader")
        self.setFixedSize(HEADER_WIDTH, LANE_HEIGHT)
        self.channel = channel
        self._document = document
        self._renaming: RenameField | None = None

        self.chip = Chip()
        self.chip.clicked.connect(self._offer_colours)
        self.name = Name(channel.name)
        self.name.setObjectName("ChannelName")
        self.name.renaming.connect(self.rename)
        self.silenced = QLabel(SILENCED)
        self.silenced.setObjectName("ChannelQuiet")
        self.silenced.setToolTip("Another channel is soloed, so this one is not heard")
        self.snap = QLabel()
        self.snap.setObjectName("ChannelSnap")

        self.gain = NumericField(
            channel.gain_db,
            minimum=GAIN_FLOOR,
            maximum=GAIN_CEILING,
            step=0.1,
            unit="dB",
            signed=True,
        )
        self.gain.setFixedWidth(84)
        self.gain.setToolTip("Channel gain — drag, or click and type")
        self.gain.committed.connect(lambda value: self._set("gain_db", value))

        self.mute = self._toggle("M", "Mute", "Mute  — mute wins over solo")
        self.solo = self._toggle("S", "Solo", "Solo  — several can be soloed")
        self.bypass = self._toggle(
            "⊘",
            "Bypass",
            "HRTF bypass  (B)\nStraight to the stereo bus, unprocessed — heard at M4",
        )
        self.mute.clicked.connect(lambda on: self._set("mute", on))
        self.solo.clicked.connect(lambda on: self._set("solo", on))
        self.bypass.clicked.connect(lambda on: self._set("hrtf_bypass", on))

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self.chip)
        top.addWidget(self.name, 1)
        top.addWidget(self.silenced)
        top.addWidget(self.snap)
        bottom = QHBoxLayout()
        bottom.setSpacing(2)
        bottom.addWidget(self.gain)
        bottom.addStretch(1)
        for button in (self.mute, self.solo, self.bypass):
            bottom.addWidget(button)
        rows = QVBoxLayout(self)
        rows.setContentsMargins(8, 6, 6, 6)
        rows.setSpacing(4)
        rows.addLayout(top)
        rows.addLayout(bottom)

    def _toggle(self, text: str, name: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setCheckable(True)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _set(self, field: str, value: object) -> None:
        if getattr(self.channel, field) != value:
            self._document.push(SetAttribute(self.channel, field, value))

    # --------------------------------------------------------- renaming

    def rename(self) -> RenameField:
        """Open the name for typing, in place, with all of it selected."""
        if self._renaming is None:
            field = RenameField(self.channel.name, self)
            field.setGeometry(self.name.geometry().adjusted(-3, -2, 3, 2))
            field.finished.connect(self._renamed)
            field.show()
            field.setFocus(Qt.FocusReason.MouseFocusReason)
            field.selectAll()
            self._renaming = field
        return self._renaming

    def renaming(self) -> RenameField | None:
        return self._renaming

    def _renamed(self, text: str | None) -> None:
        """Keep a new name; an empty one or Esc keeps the old."""
        field, self._renaming = self._renaming, None
        if field is not None:
            field.deleteLater()
        if text is not None and text.strip():
            self._set("name", text.strip())

    # ---------------------------------------------------------- menus

    def colour_menu(self) -> QMenu:
        """The active theme's channel palette, the current colour checked.

        Built here and opened with `popup` rather than `exec`, which would
        wait for a person - and hang any test that reached it.
        """
        menu = QMenu(self)
        for number, colour in enumerate(theme.active().channels, start=1):
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(colour))
            action = QAction(QIcon(swatch), f"Colour {number}", menu)
            action.setCheckable(True)
            action.setChecked(colour.upper() == self.channel.color.upper())
            action.triggered.connect(
                lambda _checked=False, colour=colour: self._set("color", colour)
            )
            menu.addAction(action)
        return menu

    def context_menu(self) -> QMenu:
        """Rename and Remove. Built here and popped up, as the palette is."""
        menu = QMenu(self)
        menu.addAction("Rename…").triggered.connect(self.rename)
        menu.addAction("Remove Channel").triggered.connect(self._remove)
        return menu

    def _offer_colours(self) -> None:
        self.colour_menu().popup(self.chip.mapToGlobal(QPoint(0, self.chip.height())))

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu().popup(event.globalPos())
        event.accept()

    def _remove(self) -> None:
        self._document.push(RemoveChannel(self._document.project, self.channel))

    def show_channel(self, project: Project, *, silenced: bool) -> None:
        """Read the channel back into every control, committing nothing."""
        channel = self.channel
        self.chip.set_colour(channel.color)
        self.chip.setToolTip(f"{channel.name}'s colour")
        self.name.setText(channel.name)
        self.name.setToolTip(channel.name)
        self.gain.set_value(channel.gain_db)
        for button, on in (
            (self.mute, channel.mute),
            (self.solo, channel.solo),
            (self.bypass, channel.hrtf_bypass),
        ):
            button.setChecked(on)
        self.silenced.setVisible(silenced)

        own = channel.snap_override is not None
        snap = effective_snap(project, channel)
        self.snap.setText(snap_text(snap).removeprefix("Snap ") if own else "snap")
        self.snap.setProperty("overriding", own)
        self.snap.setToolTip(
            f"This channel snaps to {snap_text(snap).removeprefix('Snap ')}, "
            "overriding the project"
            if own
            else f"Snaps as the project does: {snap_text(project.snap)}"
        )
        # A dynamic property only reaches the stylesheet when re-polished.
        self.snap.style().unpolish(self.snap)
        self.snap.style().polish(self.snap)


class ChannelHeaders(QWidget):
    """The column of headers, placed against the view's vertical scroll."""

    def __init__(
        self, document: Document, view: TimelineView, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ChannelHeaders")
        self.setFixedWidth(HEADER_WIDTH)
        self._document = document
        self._view = view
        #: Clips the headers to the lanes' height, which the view's horizontal
        #: scrollbar makes shorter than this column.
        self._clip = QWidget(self)
        self._headers: list[ChannelHeader] = []
        #: The header being dragged, and where on it the press landed.
        self._dragging: tuple[ChannelHeader, QPointF] | None = None
        self._press: tuple[ChannelHeader, QPointF] | None = None
        view.verticalScrollBar().valueChanged.connect(self._place)
        view.verticalScrollBar().rangeChanged.connect(self._place)
        document.observe(self.sync)
        self.sync()

    def headers(self) -> list[ChannelHeader]:
        return list(self._headers)

    def sync(self) -> None:
        """Show the project's channels: in place if they are the ones shown,
        in the same order; rebuilt otherwise."""
        project = self._document.project
        channels = project.channels
        if len(self._headers) != len(channels) or any(
            header.channel is not channel
            for header, channel in zip(self._headers, channels, strict=True)
        ):
            for header in self._headers:
                header.deleteLater()
            self._headers = [
                ChannelHeader(channel, self._document, self._clip)
                for channel in channels
            ]
            for header in self._headers:
                header.installEventFilter(self)
                header.show()
        soloing = any(channel.solo for channel in channels)
        for header, heard in zip(self._headers, audible(channels), strict=True):
            silenced = soloing and not heard and not header.channel.mute
            header.show_channel(project, silenced=silenced)
        self._place()

    def _place(self) -> None:
        scroll = self._view.verticalScrollBar().value()
        self._clip.setGeometry(0, 0, HEADER_WIDTH, self._view.viewport().height())
        for index, header in enumerate(self._headers):
            header.move(0, index * LANE_HEIGHT - scroll)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place()

    # ------------------------------------------------------ reordering

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """A header dragged up or down is moved there, in one command.

        The header follows the pointer while it moves, and the release puts
        its channel at the lane under it - one `MoveChannel`, however many
        lanes the drag passed through on the way.
        """
        if not isinstance(watched, ChannelHeader) or not isinstance(event, QMouseEvent):
            return False
        kind = event.type()
        if kind is QEvent.Type.MouseButtonPress:
            if event.button() is Qt.MouseButton.LeftButton:
                self._press = (watched, event.position())
            return False
        if kind is QEvent.Type.MouseMove and self._press is not None:
            header, grabbed = self._press
            moved = event.position() - grabbed
            if self._dragging is None and abs(moved.y()) < DRAG_THRESHOLD:
                return False
            self._dragging = (header, grabbed)
            header.raise_()
            header.move(0, header.y() + round(moved.y()))
            return True
        if kind is QEvent.Type.MouseButtonRelease and self._press is not None:
            self._press = None
            if self._dragging is None:
                return False
            header, _ = self._dragging
            self._dragging = None
            self._drop(header)
            return True
        return False

    def _drop(self, header: ChannelHeader) -> None:
        """Put the dragged channel at the lane its header's middle is over."""
        channels = self._document.project.channels
        scroll = self._view.verticalScrollBar().value()
        middle = header.y() + LANE_HEIGHT / 2 + scroll
        target = min(max(int(middle // LANE_HEIGHT), 0), len(channels) - 1)
        origin = next(i for i, c in enumerate(channels) if c is header.channel)
        if target != origin:
            self._document.push(
                MoveChannel(self._document.project, header.channel, target)
            )
        self._place()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """A wheel over the headers scrolls what it would over the lanes."""
        self._view.wheelEvent(event)
