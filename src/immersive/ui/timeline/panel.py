"""The timeline panel: the ruler over the lanes, the headers beside them,
and where the playhead is.

Four cells. The corner stays put; the ruler follows the lanes sideways and
the headers follow them up and down; the lanes scroll both ways:

    corner   | ruler
    headers  | lanes

It keeps the playhead until phase 9's transport does, and tells both
widgets when it moves. It does not keep the time axis: the window does, and
hands it in, because the curve editor at M6 observes the same one and
neither panel may own it (D-94).
"""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QWidget

from immersive.core.document import Document
from immersive.core.time import SAMPLE_RATE
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
    """Channels, clips, ruler and playhead - the ruler and the grid so far."""

    def __init__(
        self, document: Document, axis: TimeAxis, parent: QWidget | None = None
    ) -> None:
        super().__init__("Timeline", parent)
        self._document = document
        self._axis = axis
        self._playhead = 0

        self.ruler = Ruler(document, axis)
        self.view = TimelineView(document, axis)
        self.headers = ChannelHeaders(document, self.view)
        self.corner = QWidget()
        self.corner.setObjectName("TimelineCorner")
        self.corner.setFixedSize(HEADER_WIDTH, self.ruler.height())

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

        self.ruler.clicked.connect(self.set_playhead)
        document.observe(self._project_changed)
        self._project_changed()
        self.retheme()

    @property
    def axis(self) -> TimeAxis:
        return self._axis

    def playhead(self) -> int:
        return self._playhead

    def set_playhead(self, sample: int) -> None:
        self._playhead = max(sample, 0)
        self.ruler.set_playhead(self._playhead)
        self.view.set_playhead(self._playhead)

    def _project_changed(self) -> None:
        """The view and the ruler read the tempo when they paint, and repaint
        on their own; what is left is how far there is to scroll."""
        self._axis.set_extent(extent_for(self._document.project.length))

    def unit(self) -> Unit:
        return self.ruler.unit

    def set_unit(self, unit: Unit) -> None:
        self.ruler.set_unit(unit)
