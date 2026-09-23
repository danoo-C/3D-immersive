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

        # A header bar rather than a caption floating in the middle of an empty
        # box: it is where the real panel's title will live, so the shell reads
        # as unfinished rather than as badly laid out.
        self._header = QLabel(title.upper())
        self._header.setObjectName("PanelHeader")
        self._header.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addStretch(1)

        self._hint: QLabel | None = None
        if subtitle:
            self._hint = QLabel(subtitle)
            self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._hint.setWordWrap(True)
            layout.addWidget(self._hint)

        layout.addStretch(1)
        self.retheme()

    def retheme(self) -> None:
        """Re-read every colour this widget paints itself with (D-82).

        Three inline stylesheets, set at construction, which is why this
        method has to exist: D-76 made the *accessors* read at call time and
        nothing made a widget re-read what it had already baked in. The theme
        picker walks the tree calling this, and a widget that does not have
        it stays visibly the old colour - which is the point of making the
        protocol a capability rather than a subscription.
        """
        self.setStyleSheet(
            f"#Placeholder {{"
            f" background-color: {theme.color('surface.panel')};"
            f" border: none;"
            f" }}"
        )
        # 04-ui-spec.md, Craft: small caps, text.secondary on surface.raised,
        # with a one-pixel bottom border.
        self._header.setStyleSheet(
            f"#PanelHeader {{"
            f" color: {theme.color('text.secondary')};"
            f" background: {theme.color('surface.raised')};"
            f" border-bottom: 1px solid {theme.color('border')};"
            f" font-size: 10px; font-weight: 600; letter-spacing: 1.2px;"
            f" padding: 6px 10px;"
            f" }}"
        )
        if self._hint is not None:
            self._hint.setStyleSheet(
                f"color: {theme.color('text.disabled')}; font-size: 11px;"
            )
