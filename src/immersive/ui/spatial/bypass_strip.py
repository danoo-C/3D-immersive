"""The bypass strip (04, *Bypassed channels*; D-36, D-147).

A channel with HRTF bypass has no position, so it is on no canvas. It is
a chip here instead, under the top view: a dot in its colour, its name,
and a ⊘. The chips follow the project's channel order and wrap into as
many rows as they need, so every bypassed channel is shown, and the strip
is hidden, taking no room, when none is.

A click on a chip selects its channel as a click on its icon would, and
Ctrl toggles it. A click on its ⊘ un-bypasses it, as one edit, the one the
header's B button makes, and its icon is back on the canvases where its
position was kept. A selected chip is outlined as its icon would be
ringed, and the ⊘ under the pointer is lit.

A painted group's keys (D-92): `strip`, `chip`, `chip.text` and
`chip.glyph` in `spatial`, read when it paints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QHelpEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import QToolTip, QWidget

from immersive.core.document import Document
from immersive.core.edits import SetAttribute
from immersive.core.model import Channel
from immersive.core.selection import Kind
from immersive.ui.theme import group_color

#: A chip's height, and the room around and between chips, pixels.
CHIP_HEIGHT: Final = 22
MARGIN: Final = 6
GAP: Final = 6

#: Inside a chip: its padding, the dot's radius, the widest a name is
#: before it is elided, and the ⊘'s radius.
PADDING: Final = 8
DOT: Final = 4.0
NAME_WIDTH: Final = 140
GLYPH: Final = 5.0


@dataclass(frozen=True)
class Chip:
    """One bypassed channel's chip: where it is, and where its ⊘ is."""

    channel: Channel
    rect: QRectF
    glyph: QRectF


class BypassStrip(QWidget):
    """Every bypassed channel as a chip, wrapped into rows; hidden when
    there are none."""

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BypassStrip")
        self.setMouseTracking(True)
        self._document = document
        self._lit: Channel | None = None
        document.observe(self._project_changed)
        document.selection.observe(self.update)
        self._project_changed()

    def retheme(self) -> None:
        """A theme switch: the colours are read when it paints."""
        self.update()

    def bypassed(self) -> list[Channel]:
        return [c for c in self._document.project.channels if c.hrtf_bypass]

    def chips(self) -> list[Chip]:
        """Every chip, laid out across the strip's width: a chip that would
        pass the right edge starts the next row."""
        metrics = self.fontMetrics()
        made: list[Chip] = []
        x, y = float(MARGIN), float(MARGIN)
        right = self.width() - MARGIN
        for channel in self.bypassed():
            name = min(metrics.horizontalAdvance(channel.name), NAME_WIDTH)
            width = PADDING + 2 * DOT + GAP + name + GAP + 2 * GLYPH + PADDING
            if x > MARGIN and x + width > right:
                x, y = float(MARGIN), y + CHIP_HEIGHT + GAP
            rect = QRectF(x, y, width, CHIP_HEIGHT)
            glyph = QRectF(
                rect.right() - PADDING - 2 * GLYPH - 3,
                rect.top(),
                2 * GLYPH + 6,
                CHIP_HEIGHT,
            )
            made.append(Chip(channel, rect, glyph))
            x += width + GAP
        return made

    def chip_at(self, point: QPointF) -> Chip | None:
        return next((chip for chip in self.chips() if chip.rect.contains(point)), None)

    # ------------------------------------------------------------ changes

    def _project_changed(self) -> None:
        """A channel bypassed or back, renamed or recoloured: shown or
        hidden, refitted, repainted."""
        self.setVisible(bool(self.bypassed()))
        self._fit()
        self.update()

    def _fit(self) -> None:
        """As tall as its rows."""
        chips = self.chips()
        bottom = max((chip.rect.bottom() for chip in chips), default=0.0)
        height = int(bottom) + MARGIN if chips else 0
        if self.height() != height or self.minimumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    # ------------------------------------------------------------ drawing

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(group_color("spatial", "strip")))
        selection = self._document.selection
        metrics = self.fontMetrics()
        for chip in self.chips():
            rect, channel = chip.rect, chip.channel
            if channel in selection:
                painter.setPen(QPen(QColor(group_color("spatial", "selected")), 1.5))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(group_color("spatial", "chip")))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(channel.color))
            dot = QPointF(rect.left() + PADDING + DOT, rect.center().y())
            painter.drawEllipse(dot, DOT, DOT)
            painter.setPen(QColor(group_color("spatial", "chip.text")))
            name = QRectF(dot.x() + DOT + GAP, rect.top(), NAME_WIDTH, rect.height())
            painter.drawText(
                name,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(
                    channel.name, Qt.TextElideMode.ElideRight, NAME_WIDTH
                ),
            )
            self._draw_glyph(painter, chip, lit=channel is self._lit)
        painter.end()

    def _draw_glyph(self, painter: QPainter, chip: Chip, *, lit: bool) -> None:
        """⊘: a circle struck through, drawn rather than a font's glyph."""
        colour = (
            group_color("spatial", "selected")
            if lit
            else group_color("spatial", "chip.glyph")
        )
        painter.setPen(QPen(QColor(colour), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        centre = chip.glyph.center()
        painter.drawEllipse(centre, GLYPH, GLYPH)
        reach = GLYPH * 0.7
        painter.drawLine(
            QPointF(centre.x() - reach, centre.y() + reach),
            QPointF(centre.x() + reach, centre.y() - reach),
        )

    # -------------------------------------------------------------- mouse

    def mousePressEvent(self, event: QMouseEvent) -> None:
        chip = self.chip_at(event.position())
        if event.button() is not Qt.MouseButton.LeftButton or chip is None:
            super().mousePressEvent(event)
            return
        selection = self._document.selection
        if chip.glyph.contains(event.position()):
            self._document.push(SetAttribute(chip.channel, "hrtf_bypass", False))
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            selection.toggle(Kind.CHANNELS, chip.channel)
        elif chip.channel not in selection:
            selection.select(Kind.CHANNELS, [chip.channel])
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        chip = self.chip_at(event.position())
        lit = chip.channel if chip and chip.glyph.contains(event.position()) else None
        if lit is not self._lit:
            self._lit = lit
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._lit is not None:
            self._lit = None
            self.update()
        super().leaveEvent(event)

    def event(self, event: QEvent) -> bool:
        """A chip's tooltip: its whole name, and what its ⊘ does."""
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            chip = self.chip_at(QPointF(event.pos()))
            if chip is None:
                QToolTip.hideText()
            elif chip.glyph.contains(QPointF(event.pos())):
                QToolTip.showText(
                    event.globalPos(),
                    f"Un-bypass {chip.channel.name}: heard from where it was placed",
                    self,
                )
            else:
                QToolTip.showText(
                    event.globalPos(), f"{chip.channel.name}  — HRTF bypassed", self
                )
            return True
        return super().event(event)
