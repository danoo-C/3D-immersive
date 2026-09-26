"""A line of text that keeps Enter and Esc for itself.

A line edit claims the keys that type or edit text before any window
shortcut sees them, but not Enter and Esc: to Qt those are a dialog's. In
this window they are the transport's - Return to Start and Stop - so a field
that commits on Enter or cancels on Esc would hand them to the transport
instead, and typing a name then pressing Enter would send the playhead to
the start. A field that uses them claims them, and only while it has the
keyboard.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

#: What a field that commits and cancels keeps from the window's shortcuts.
KEPT = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)


def claims(event: QEvent) -> bool:
    """Whether `event` asks for one of the keys a field keeps."""
    return (
        event.type() == QEvent.Type.ShortcutOverride
        and isinstance(event, QKeyEvent)
        and event.key() in KEPT
    )


class TextField(QLineEdit):
    """A line edit that keeps Enter and Esc from the window's shortcuts."""

    def event(self, event: QEvent) -> bool:
        if claims(event):
            event.accept()
            return True
        return super().event(event)
