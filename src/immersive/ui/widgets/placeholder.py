"""An empty labelled panel.

M0 scaffolding: every region of the layout is one of these until the real
widget replaces it. Keeping them uniform makes the proportions of the shell
easy to judge before any content exists.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from immersive.ui import theme


class Placeholder(QFrame):
    """A titled, empty panel standing in for a region of the UI."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Placeholder")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"#Placeholder {{ background-color: {theme.BG_1};"
            f" border: 1px solid {theme.BORDER}; }}"
        )

        name = QLabel(title.upper())
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            f"color: {theme.TEXT_LO}; font-size: 11px;"
            " font-weight: 600; letter-spacing: 1.5px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(name)

        if subtitle:
            hint = QLabel(subtitle)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
            layout.addWidget(hint)

        layout.addStretch(1)
