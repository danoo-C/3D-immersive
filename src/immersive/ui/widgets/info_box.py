"""The info box: at the right end of the transport toolbar, what is under way.

The activities in `ui/activity.py`, drawn (D-116). The first begun is shown -
its label, a thin bar, and a ✕ if it can be cancelled - with *+n more* when
others run and a tooltip naming every one. With nothing to show the box is
hidden, through its toolbar action: a widget in a `QToolBar` is shown and
hidden by the action the toolbar made for it, not by `setVisible`.

It looks again when told of a change, and once more when the next activity
reaches `SHOW_AFTER`, by a single-shot timer - so an activity that begins and
then says nothing still appears, and nothing polls while nothing runs.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from immersive.ui import icons
from immersive.ui.activity import Activities, Activity

#: The box's width when the toolbar has room, and the least it gives way to
#: when it has not. Never set by its label, so a label changing never moves
#: the toolbar. The window's narrowest, 1024 px, leaves the box about 170 px
#: past the ARM button; below the least, Qt would fold it into the toolbar's
#: overflow menu, where a long import could not be seen.
WIDTH = 260
NARROWEST = 150

#: The bar's steps. Not the activity's own numbers: `QProgressBar` holds a
#: 32-bit int, and an import counted in bytes passes 2 GB.
STEPS = 1000


def describe(activity: Activity) -> str:
    """One line of the tooltip."""
    fraction = activity.fraction
    if fraction is None:
        return activity.label
    return f"{activity.label} — {math.floor(fraction * 100)}%"


class InfoBox(QFrame):
    """The first activity shown, and how many more."""

    def __init__(self, activities: Activities, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoBox")
        self.setMinimumWidth(NARROWEST)
        self.setMaximumWidth(WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._activities = activities
        self._action: QAction | None = None
        self._text = ""

        self._label = QLabel()
        self._label.setObjectName("InfoLabel")
        self._more = QLabel()
        self._more.setObjectName("InfoMore")
        self._cancel = QToolButton()
        self._cancel.setObjectName("InfoCancel")
        self._cancel.setAutoRaise(True)
        self._cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cancel.setToolTip("Cancel")
        self._cancel.setIcon(icons.icon("cancel"))
        # No taller than the toolbar's own buttons, so the box never makes
        # the toolbar grow when it appears.
        self._cancel.setFixedSize(20, 20)
        self._cancel.setIconSize(QSize(12, 12))
        self._cancel.clicked.connect(self.cancel)
        self._bar = QProgressBar()
        self._bar.setObjectName("InfoBar")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._label, 1)
        row.addWidget(self._more)
        row.addWidget(self._cancel)
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 1, 2, 2)
        column.setSpacing(1)
        column.addLayout(row)
        column.addWidget(self._bar)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        activities.observe(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ reading

    def showing(self) -> Activity | None:
        """The activity the box shows, if it shows one."""
        shown = self._activities.shown()
        return shown[0] if shown else None

    def label(self) -> str:
        return self._text

    def more(self) -> str:
        return self._more.text() if self._more.isVisibleTo(self) else ""

    def can_cancel(self) -> bool:
        return self._cancel.isVisibleTo(self)

    def bar(self) -> QProgressBar:
        return self._bar

    # ------------------------------------------------------------ keeping

    def attach(self, action: QAction) -> None:
        """The toolbar's action for this box, which shows and hides it."""
        self._action = action
        self.refresh()

    def refresh(self) -> None:
        """Draw what is shown now, and look again when the next is due."""
        wait = self._activities.next_shown_in()
        if wait is None:
            self._timer.stop()
        else:
            self._timer.start(max(1, math.ceil(wait * 1000)))

        shown = self._activities.shown()
        if not shown:
            self.setToolTip("")
            self._set_visible(False)
            return
        first = shown[0]
        self._text = first.label
        self._elide()
        others = len(shown) - 1
        self._more.setText(f"+{others} more")
        self._more.setVisible(others > 0)
        self._cancel.setVisible(first.cancel is not None)
        fraction = first.fraction
        if fraction is None:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, STEPS)
            self._bar.setValue(round(fraction * STEPS))
        self.setToolTip("\n".join(describe(each) for each in shown))
        self._set_visible(True)

    def cancel(self) -> None:
        """The ✕: stop the activity shown, if it can be stopped. The work
        finishes its own activity once it has."""
        first = self.showing()
        if first is not None and first.cancel is not None:
            first.cancel()

    def retheme(self) -> None:
        """The ✕ is a memoised rendering, asked for again on a theme change."""
        self._cancel.setIcon(icons.icon("cancel"))

    # ------------------------------------------------------------ internal

    def sizeHint(self) -> QSize:
        return QSize(WIDTH, super().sizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self._label.width(), 1)
        metrics = self._label.fontMetrics()
        self._label.setText(
            metrics.elidedText(self._text, Qt.TextElideMode.ElideRight, width)
        )
        self._label.setToolTip(self._text)

    def _set_visible(self, on: bool) -> None:
        if self._action is not None:
            self._action.setVisible(on)
        else:
            self.setVisible(on)
