"""The application shell: menus, toolbar, splitter layout, status bar.

M0 builds the frame only — every region is a Placeholder. The layout and its
proportions come from docs/04-ui-spec.md, and the splitter structure there is
deliberate: a fixed layout with draggable splitters, not dockable panels
(D-15).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

from immersive import __version__
from immersive.ui import theme
from immersive.ui.widgets.placeholder import Placeholder

WINDOW_TITLE = "3d immersive"

# Initial splitter sizes, in pixels. Qt distributes any surplus proportionally,
# so these set the relative weights as much as the literal widths.
_LEFT_COLUMN_W = 250
_RIGHT_COLUMN_W = 300
_TIMELINE_H = 260
_POOL_H = 380
_PARAMS_H = 220


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1500, 950)
        self.setMinimumSize(1024, 680)

        self._build_menus()
        self._build_toolbar()
        self.setCentralWidget(self._build_layout())
        self._build_statusbar()

    # ----------------------------------------------------------------- menus

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self._add(file_menu, "&New Project", QKeySequence.StandardKey.New)
        self._add(file_menu, "&Open Project…", QKeySequence.StandardKey.Open)
        file_menu.addSeparator()
        self._add(file_menu, "&Save", QKeySequence.StandardKey.Save)
        self._add(file_menu, "Save &As…", QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self._add(file_menu, "&Import Audio…", "Ctrl+I")
        file_menu.addSeparator()
        quit_action = self._add(file_menu, "&Quit", QKeySequence.StandardKey.Quit)
        quit_action.setEnabled(True)
        quit_action.triggered.connect(self.close)

        edit_menu = bar.addMenu("&Edit")
        self._add(edit_menu, "&Undo", QKeySequence.StandardKey.Undo)
        self._add(edit_menu, "&Redo", QKeySequence.StandardKey.Redo)
        edit_menu.addSeparator()
        self._add(edit_menu, "&Duplicate", "Ctrl+D")
        self._add(edit_menu, "De&lete", QKeySequence.StandardKey.Delete)
        self._add(edit_menu, "&Split at Playhead", "S")

        view_menu = bar.addMenu("&View")
        self._add(view_menu, "Focus &Top View", "1")
        self._add(view_menu, "Focus &Front View", "2")
        self._add(view_menu, "Focus &3D View", "3")
        view_menu.addSeparator()
        self._add(view_menu, "Ruler: &Bars / Beats")
        self._add(view_menu, "Ruler: &Minutes / Seconds")

        transport_menu = bar.addMenu("&Transport")
        self._add(transport_menu, "&Play / Pause", "Space")
        self._add(transport_menu, "&Return to Start", "Return")
        self._add(transport_menu, "Toggle &Loop", "L")
        transport_menu.addSeparator()
        self._add(transport_menu, "Toggle HRTF &Bypass on Channel", "B")

        render_menu = bar.addMenu("&Render")
        self._add(render_menu, "&Render Mix…", "Ctrl+R")
        self._add(render_menu, "Render &Stems…")

        help_menu = bar.addMenu("&Help")
        self._add(help_menu, "&Documentation")
        self._add(help_menu, f"&About {WINDOW_TITLE}")

    def _add(
        self,
        menu: object,
        text: str,
        shortcut: QKeySequence.StandardKey | str | None = None,
    ) -> QAction:
        """Add a disabled placeholder action. M0 wires up nothing but Quit."""
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setEnabled(False)
        menu.addAction(action)  # type: ignore[attr-defined]
        return action

    # --------------------------------------------------------------- toolbar

    def _build_toolbar(self) -> None:
        bar = QToolBar("Transport")
        bar.setMovable(False)
        self.addToolBar(bar)

        for label in ("|<", ">", "[]", "loop"):
            action = QAction(label, self)
            action.setEnabled(False)
            bar.addAction(action)

        bar.addSeparator()
        bar.addWidget(self._chip("120.0 BPM"))
        bar.addWidget(self._chip("4/4"))
        bar.addSeparator()
        bar.addWidget(self._chip("Snap 1/16"))
        bar.addSeparator()

        for label in ("undo", "redo"):
            action = QAction(label, self)
            action.setEnabled(False)
            bar.addAction(action)

        bar.addSeparator()
        arm = QLabel("  ARM  ")
        arm.setStyleSheet(
            f"color: {theme.TEXT_DIM}; border: 1px solid {theme.BORDER};"
            " border-radius: 4px; padding: 3px 6px;"
        )
        arm.setToolTip("Automation write-arm (F-32) — not wired up yet")
        bar.addWidget(arm)

    def _chip(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.TEXT_LO}; padding: 0 8px;")
        return label

    # ---------------------------------------------------------------- layout

    def _build_layout(self) -> QWidget:
        # Left column: media pool over the context-sensitive params pane.
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(Placeholder("Media Pool", "imported audio, drag to timeline"))
        left.addWidget(Placeholder("Parameters", "follows the current selection"))
        left.setSizes([_POOL_H, _PARAMS_H])

        # Workspace: two editable ortho views plus the read-only 3D view (D-5).
        workspace = QSplitter(Qt.Orientation.Horizontal)
        workspace.addWidget(Placeholder("Top view", "X / Y — drag to position"))
        workspace.addWidget(Placeholder("Front view", "X / Z — drag for height"))
        workspace.addWidget(Placeholder("3D view", "read-only, fixed camera"))
        workspace.setSizes([520, 340, 340])

        upper = QSplitter(Qt.Orientation.Horizontal)
        upper.addWidget(left)
        upper.addWidget(workspace)
        upper.addWidget(
            Placeholder("Keyframe Editor", "curves, axis-linked to timeline")
        )
        upper.setSizes([_LEFT_COLUMN_W, 950, _RIGHT_COLUMN_W])
        upper.setStretchFactor(1, 1)

        root = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(upper)
        root.addWidget(Placeholder("Timeline", "channels, clips, ruler, playhead"))
        root.setSizes([950 - _TIMELINE_H, _TIMELINE_H])
        root.setStretchFactor(0, 1)

        for splitter in (left, workspace, upper, root):
            splitter.setHandleWidth(1)
            splitter.setChildrenCollapsible(False)

        return root

    # ------------------------------------------------------------- statusbar

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.showMessage("No project")

        self._xruns = QLabel("xruns 0")
        self._xruns.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self._xruns.setToolTip("Audio dropouts since the stream started")
        bar.addPermanentWidget(self._xruns)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet(f"color: {theme.TEXT_DIM};")
        bar.addPermanentWidget(version)

        self.setStatusBar(bar)
