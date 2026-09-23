"""An empty labelled panel.

M0 scaffolding: every region of the layout is one of these until the real
widget replaces it. Keeping them uniform makes the proportions of the shell
easy to judge before any content exists.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from immersive.ui import theme


class Placeholder(QFrame):
    """A titled, empty panel standing in for a region of the UI."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Placeholder")
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = theme.color("surface.panel")
        self.setStyleSheet(
            f"#Placeholder {{ background-color: {body}; border: none; }}"
        )

        # A header bar rather than a caption floating in the middle of an empty
        # box: it is where the real panel's title will live, so the shell reads
        # as unfinished rather than as badly laid out.
        header = QLabel(title.upper())
        header.setObjectName("PanelHeader")
        # 04-ui-spec.md, Craft: small caps, text.secondary on surface.raised,
        # with a one-pixel bottom border.
        header.setStyleSheet(
            f"#PanelHeader {{"
            f" color: {theme.color('text.secondary')};"
            f" background: {theme.color('surface.raised')};"
            f" border-bottom: 1px solid {theme.color('border')};"
            f" font-size: 10px; font-weight: 600; letter-spacing: 1.2px;"
            f" padding: 6px 10px;"
            f" }}"
        )
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addStretch(1)

        if subtitle:
            hint = QLabel(subtitle)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color: {theme.color('text.disabled')}; font-size: 11px;"
            )
            layout.addWidget(hint)

        layout.addStretch(1)
