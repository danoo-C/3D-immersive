"""The notice surface: a status-bar line, an unread count, and the list.

The *Notices* section of docs/04-ui-spec.md, drawn. The model it draws is
`ui/notices.py`, which holds no Qt (D-81) — this file is the half that does.

**One surface, not a dialog per caller.** A modal for a cosmetic theme typo
is the behaviour F-47 exists to prevent, and nothing here is modal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from immersive.ui import theme
from immersive.ui.notices import Notice, NoticeLog, Severity

#: A glyph per severity, because 04-ui-spec.md's *Accessibility and feel*
#: says no information is carried by colour alone - and a count that is only
#: distinguishable as red or amber fails that on the one widget whose whole
#: job is to be noticed. The shapes differ, not just the hue.
_GLYPH = {
    Severity.ERROR: "✕",
    Severity.WARN: "⚠",
    Severity.INFO: "•",
}

#: The token each severity is drawn in. `info` is deliberately quiet: it
#: reports that something happened, and something that happened correctly
#: should not compete with something that did not.
_TOKEN = {
    Severity.ERROR: "error",
    Severity.WARN: "warn",
    Severity.INFO: "text.secondary",
}


class NoticeList(QFrame):
    """Everything reported this session, newest first.

    A popup rather than a dialog: it closes when you look away, like every
    other notification list, and nothing in this application is modal except
    discarding an unsaved project.
    """

    def __init__(self, log: NoticeLog, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._log = log
        self.setObjectName("NoticeList")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._body = QWidget()
        self._rows = QVBoxLayout(self._body)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidget(self._body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(scroll)

        self.setMinimumWidth(360)
        self.setMaximumHeight(320)
        self.retheme()

    def rows(self) -> list[QLabel]:
        """The row widgets, newest first. Named so a test can read them."""
        found: list[QLabel] = []
        for index in range(self._rows.count()):
            item = self._rows.itemAt(index)
            if item is not None and isinstance(row := item.widget(), QLabel):
                found.append(row)
        return found

    def populate(self) -> None:
        """Rebuild the rows from the log.

        Rebuilt rather than appended to, because the list is short by
        construction and a rebuild cannot drift out of step with the model.
        Per-notice *actions* - Relink…, Reveal, Choose device… - are M8's
        (D-65); this builds the surface they will hang off.
        """
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()

        notices = self._log.newest_first()
        if not notices:
            self._rows.addWidget(self._row(None))
            return
        for notice in notices:
            self._rows.addWidget(self._row(notice))

    def _row(self, notice: Notice | None) -> QLabel:
        if notice is None:
            label = QLabel("Nothing reported this session")
            label.setStyleSheet(
                f"color: {theme.color('text.disabled')}; padding: 10px;"
            )
            return label

        detail = "\n".join(f"    {line}" for line in notice.detail)
        label = QLabel(
            f"{_GLYPH[notice.severity]}  {notice.at:%H:%M:%S}  {notice.message}"
            + (f"\n{detail}" if detail else "")
        )
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {theme.color(_TOKEN[notice.severity])};"
            f" border-bottom: 1px solid {theme.color('border')};"
            f" padding: 6px 10px;"
        )
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return label

    def retheme(self) -> None:
        self.setStyleSheet(
            f"#NoticeList {{"
            f" background: {theme.color('surface.raised')};"
            f" border: 1px solid {theme.color('border')};"
            f" }}"
        )
        self.populate()


class NoticeCount(QToolButton):
    """The unread count, beside the xrun counter. Invisible at zero.

    The same rule the xrun counter already follows, and for the same reason:
    a zero that is always on screen is a thing people stop seeing, which
    costs exactly the attention the widget exists to hold.

    A `QToolButton` rather than a `QLabel` dressed as one - the lesson the
    ARM chip taught in M0. It is clickable, so it has to look and behave like
    something clickable.
    """

    def __init__(self, log: NoticeLog, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log = log
        self.setObjectName("NoticeCount")
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._list = NoticeList(log, self)
        self.clicked.connect(self.open_list)
        self.refresh()

    def refresh(self) -> None:
        """Take the count, the glyph and the colour from the log."""
        unread = self._log.unread
        severity = self._log.unread_severity()
        if not unread or severity is None:
            self.setText("")
            self.hide()
            return

        self.setText(f"{_GLYPH[severity]} {unread}")
        self.setToolTip(
            f"{unread} unread notice{'s' if unread != 1 else ''}\nClick to read"
        )
        self.setStyleSheet(
            f"#NoticeCount {{ color: {theme.color(_TOKEN[severity])};"
            f" padding: 0 8px; border: none; }}"
        )
        self.show()

    def open_list(self) -> None:
        """Show everything reported, and mark it read."""
        self._list.populate()
        self._list.adjustSize()
        corner = self.mapToGlobal(self.rect().topLeft())
        self._list.move(
            corner.x() - self._list.width() + self.width(),
            corner.y() - self._list.height(),
        )
        self._list.show()
        self._log.mark_read()
        self.refresh()

    def retheme(self) -> None:
        self._list.retheme()
        self.refresh()
