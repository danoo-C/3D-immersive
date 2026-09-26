"""The timeline panel: the ruler over the lanes, the headers beside them,
and where the playhead is.

Four cells. The corner stays put; the ruler follows the lanes sideways and
the headers follow them up and down; the lanes scroll both ways:

    corner   | ruler
    headers  | lanes

It shows the playhead and tells both widgets when it moves; while playing,
the window moves it from the engine at every tick. What a person does to it
in the ruler - a click or a drag - it passes on as `sought`, for the window
to seek the engine there. A loop region drawn in the ruler is one edit to
the project here, and `loop_drawn` says so, for the transport to start
looping (D-108). It does not keep the time axis: the window does, and hands
it in, because the curve editor at M6 observes the same one and neither
panel may own it (D-94).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QToolButton, QWidget

from immersive.core.document import Document
from immersive.core.edits import AddChannel, SetAttribute
from immersive.core.media_store import MediaStore
from immersive.core.model import LoopRegion, new_channel
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.grid import Unit
from immersive.ui.timeline.headers import HEADER_WIDTH, ChannelHeaders
from immersive.ui.timeline.ruler import Ruler
from immersive.ui.timeline.view import TimelineView
from immersive.ui.widgets.placeholder import Panel

#: However short the project, this much timeline can be scrolled over - an
#: empty project still has somewhere to put the first clip.
EXTENT_FLOOR = SAMPLE_RATE * 60 * 10

#: How far past the last clip the timeline can be scrolled: room to put the
#: next one after it.
EXTENT_BEYOND = SAMPLE_RATE * 60


def extent_for(length: int) -> int:
    """The timeline that can be scrolled over, for a project this long."""
    return max(length + EXTENT_BEYOND, EXTENT_FLOOR)


class TimelinePanel(Panel):
    """Channels, clips, ruler and playhead."""

    #: The playhead put somewhere by a person, clicking or dragging in the
    #: ruler: a sample, as `object` for the 32-bit reason the ruler gives.
    sought = Signal(object)
    #: A loop region was drawn, and is now the project's.
    loop_drawn = Signal()

    def __init__(
        self,
        document: Document,
        axis: TimeAxis,
        store: MediaStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Timeline", parent)
        self._document = document
        self._axis = axis
        self._playhead = 0

        self.ruler = Ruler(document, axis)
        self.view = TimelineView(
            document, axis, store.peaks if store is not None else None
        )
        self.headers = ChannelHeaders(document, self.view)
        # The corner holds Add channel, so it is in reach however far the
        # lanes are scrolled.
        self.corner = QToolButton()
        self.corner.setObjectName("AddChannel")
        self.corner.setText("Add channel")
        self.corner.setToolTip("Add Channel — below the last, coloured in turn")
        self.corner.setFixedSize(HEADER_WIDTH, self.ruler.height())
        self.corner.clicked.connect(self.add_channel)

        cells = QWidget()
        grid = QGridLayout(cells)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.corner, 0, 0)
        grid.addWidget(self.ruler, 0, 1)
        grid.addWidget(self.headers, 1, 0)
        grid.addWidget(self.view, 1, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(1, 1)
        self.body().addWidget(cells, 1)

        self.ruler.clicked.connect(self._sought)
        self.ruler.dragged.connect(self._sought)
        self.ruler.looped.connect(self._draw_loop)
        document.observe(self._project_changed)
        self._project_changed()
        self.retheme()

    @property
    def axis(self) -> TimeAxis:
        return self._axis

    def playhead(self) -> int:
        return self._playhead

    def set_playhead(self, sample: int) -> None:
        """Show the playhead at `sample`. Seeks nothing."""
        self._playhead = max(sample, 0)
        self.ruler.set_playhead(self._playhead)
        self.view.set_playhead(self._playhead)

    def set_looping(self, on: bool) -> None:
        """Whether the loop region is drawn as looping."""
        self.ruler.set_looping(on)
        self.view.set_looping(on)

    def _sought(self, sample: int) -> None:
        self.set_playhead(sample)
        self.sought.emit(self._playhead)

    def _draw_loop(self, start: int, end: int) -> None:
        project = self._document.project
        region = LoopRegion(start, end)
        if region != project.loop:
            self._document.push(SetAttribute(project, "loop", region))
        self.loop_drawn.emit()

    def _project_changed(self) -> None:
        """The view and the ruler read the tempo when they paint, and repaint
        on their own; what is left is how far there is to scroll."""
        self._axis.set_extent(extent_for(self._document.project.length))

    def media_changed(self) -> None:
        """The session's samples changed - peaks arrived, or went."""
        self.view.media_changed()

    def add_channel(self) -> None:
        """A new channel below the last, named and coloured in turn."""
        project = self._document.project
        channel = new_channel(project, theme.active().channels)
        self._document.push(AddChannel(project, channel))

    def unit(self) -> Unit:
        return self.ruler.unit

    def set_unit(self, unit: Unit) -> None:
        self.ruler.set_unit(unit)
