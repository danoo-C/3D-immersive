"""The parameters pane: the selection, as fields (04, *Parameters pane*).

It shows one view at a time - a clip's, a channel's, a sample's, or the
project's when nothing is selected - and follows the document's selection
(D-96) rather than keeping one of its own.

**Rebuilt only when the kind changes.** After every change the document or
the selection reports, the pane asks its view to read the model back in
place. Only a change of kind builds a new view. Rebuilding on every change
would throw away a value somebody is in the middle of typing whenever
anything else in the project changed - phase 2's rule for the headers.

**It collapses to its header**, which says which way it will go. Collapsed,
it gives its room to the pool above it; opened again, it takes back the
height it had - which the splitter remembers without being asked.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from immersive.core.document import Document
from immersive.core.selection import Kind
from immersive.ui.parameters.views import ProjectView, Summary, View
from immersive.ui.timeline.grid import Unit
from immersive.ui.widgets.placeholder import Panel

TITLE = "Parameters"

#: What the header ends in, open and collapsed - a shape, not only a colour.
OPEN, SHUT = "▾", "▸"

#: As tall as Qt lets a widget be: what the pane's height is capped at open.
_UNBOUNDED = 16_777_215


class ParametersPane(Panel):
    """The view for what is selected, under a header that collapses it."""

    def __init__(
        self,
        document: Document,
        *,
        unit: Callable[[], Unit],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(TITLE, parent)
        self._document = document
        self._unit = unit
        self._view: View | None = None
        #: The kind the view was built for; `None` is the project's.
        self._kind: Kind | None = None
        self._collapsed = False

        self._scroll = QScrollArea()
        self._scroll.setObjectName("ParametersScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body().addWidget(self._scroll, 1)

        header = self.header()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.installEventFilter(self)
        self._show_header()

        document.observe(self._changed)
        document.selection.observe(self._changed)
        self._changed()
        self.retheme()

    # ------------------------------------------------------------ reading

    def view(self) -> View:
        assert self._view is not None
        return self._view

    def collapsed(self) -> bool:
        return self._collapsed

    # ------------------------------------------------------------ changing

    def refresh(self) -> None:
        """Something the fields show changed outside the model - the ruler's
        unit - so show them again."""
        self.view().refresh()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        # Capped at its header's height, the splitter gives the rest to the
        # pool; uncapped, it hands the height back by itself.
        if collapsed:
            self._scroll.hide()
            self.setMaximumHeight(self.header().sizeHint().height())
        else:
            self.setMaximumHeight(_UNBOUNDED)
            self._scroll.show()
        self._collapsed = collapsed
        self._show_header()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.header() and event.type() is QEvent.Type.MouseButtonPress:
            self.set_collapsed(not self._collapsed)
            return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------ internal

    def _show_header(self) -> None:
        header = self.header()
        header.setText(f"{TITLE.upper()}  {SHUT if self._collapsed else OPEN}")
        header.setToolTip(
            "Click to open the parameters"
            if self._collapsed
            else "Click to collapse the parameters and give the pool the room"
        )

    def _changed(self) -> None:
        kind = self._document.selection.kind
        if self._view is None or kind is not self._kind:
            self._kind = kind
            self._view = self._build(kind)
            self._scroll.setWidget(self._view)
        self._view.show_values()

    def _build(self, kind: Kind | None) -> View:
        document = self._document
        if kind is None:
            return ProjectView(document)
        count = len(document.selection)
        noun = {Kind.CLIPS: "clip", Kind.CHANNELS: "channel", Kind.MEDIA: "sample"}[
            kind
        ]
        return Summary(document, f"{count} {noun}{'s' if count != 1 else ''}")
