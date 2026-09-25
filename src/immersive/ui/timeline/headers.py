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

from collections.abc import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPalette,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from immersive.core.commands import Command
from immersive.core.document import Document
from immersive.core.edits import SetAttribute
from immersive.core.model import Channel, Project, audible, effective_snap
from immersive.ui.timeline.grid import snap_text
from immersive.ui.timeline.view import LANE_HEIGHT, TimelineView
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


class Chip(QWidget):
    """The channel's colour, as a small square."""

    SIZE = 12

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
    beside it. `text()` is still the whole name; so is the tooltip."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        # Take what is left of the row, and no more.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

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


class ChannelHeader(QFrame):
    """One channel's header. It edits the channel only through `push`."""

    def __init__(
        self,
        channel: Channel,
        push: Callable[[Command], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ChannelHeader")
        self.setFixedSize(HEADER_WIDTH, LANE_HEIGHT)
        self.channel = channel
        self._push = push

        self.chip = Chip()
        self.name = Name(channel.name)
        self.name.setObjectName("ChannelName")
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
            self._push(SetAttribute(self.channel, field, value))

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
                ChannelHeader(channel, self._document.push, self._clip)
                for channel in channels
            ]
            for header in self._headers:
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

    def wheelEvent(self, event: QWheelEvent) -> None:
        """A wheel over the headers scrolls what it would over the lanes."""
        self._view.wheelEvent(event)
