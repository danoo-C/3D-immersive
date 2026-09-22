"""The application shell: menus, toolbar, splitter layout, status bar.

M0 builds the frame only — every region is a Placeholder. The layout and its
proportions come from docs/04-ui-spec.md, and the splitter structure there is
deliberate: a fixed layout with draggable splitters, not dockable panels
(D-15).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QMouseEvent
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from immersive import __version__
from immersive.ui import icons, theme
from immersive.ui.widgets.placeholder import Placeholder

WINDOW_TITLE = "3d immersive"

# Initial splitter sizes, in pixels. Qt distributes any surplus proportionally,
# so these set the relative weights as much as the literal widths.
_LEFT_COLUMN_W = 250
_RIGHT_COLUMN_W = 300
_TIMELINE_H = 260
_POOL_H = 380
_PARAMS_H = 220

# Why each disabled action is disabled, in the words its tooltip uses. They
# live here as constants so that a milestone landing updates one line per
# milestone rather than a dozen scattered strings - and so that a grep for
# "M3" finds everything the timeline milestone switches on. The milestones
# themselves are defined in docs/06-roadmap.md.
_M1 = "the project model and undo stack arrive at M1"
_M2 = "the media pool arrives at M2"
_M3 = "the timeline and transport arrive at M3"
_M5 = "the spatial views arrive at M5"
_M6 = "automation arrives at M6"
_M7 = "rendering arrives at M7"
_M8 = "the help surfaces arrive at M8"


def _quit_shortcut() -> QKeySequence:
    """Quit's key, with a fallback for the platforms Qt leaves empty.

    QKeySequence.StandardKey.Quit resolves to nothing under several Linux
    platform themes, which left the one action in the application that
    actually works as the only one with no shortcut at all.
    """
    standard = QKeySequence(QKeySequence.StandardKey.Quit)
    return standard if not standard.isEmpty() else QKeySequence("Ctrl+Q")


class _MenuBarHover(QObject):
    """Walk between menus by hovering, once one of them is already open.

    Every desktop does this, and Qt usually provides it without help - but the
    popup grabs the mouse while it is open, so on setups where that grab is not
    delivered back to the menu bar (WSLg among them) the behaviour silently
    goes missing. Doing it explicitly costs one event filter and removes the
    dependence on which compositor happens to be underneath.

    Note the deliberate limit: hovering does *not* open the first menu. A menu
    bar that springs open when the pointer crosses it on the way to the toolbar
    is the kind of helpfulness nobody asked for.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() is not QEvent.Type.MouseMove:
            return False
        bar = watched
        if not isinstance(bar, QMenuBar) or not _menu_is_open(bar):
            return False
        assert isinstance(event, QMouseEvent)
        hovered = bar.actionAt(event.position().toPoint())
        if hovered is not None and hovered is not bar.activeAction():
            bar.setActiveAction(hovered)
        return False


def _menu_is_open(bar: QMenuBar) -> bool:
    # QAction.menu() is typed as QObject in the PySide6 stubs, hence isinstance
    # rather than a None check.
    return any(
        isinstance(menu := action.menu(), QMenu) and menu.isVisible()
        for action in bar.actions()
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(icons.app_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1024, 680)

        self._build_menus()
        self._build_toolbar()
        self.setCentralWidget(self._build_layout())
        self._build_statusbar()

    # ----------------------------------------------------------------- menus

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.setMouseTracking(True)
        self._menu_hover = _MenuBarHover(self)
        bar.installEventFilter(self._menu_hover)

        file_menu = self._menu(bar, "&File")
        self._add(file_menu, "&New Project", "Ctrl+N", arrives=_M1)
        self._add(file_menu, "&Open Project…", "Ctrl+O", arrives=_M1)
        file_menu.addSeparator()
        self._add(file_menu, "&Save", "Ctrl+S", arrives=_M1)
        self._add(file_menu, "Save &As…", "Ctrl+Shift+S", arrives=_M1)
        file_menu.addSeparator()
        self._add(file_menu, "&Import Audio…", "Ctrl+I", arrives=_M2)
        file_menu.addSeparator()
        quit_action = self._add(file_menu, "&Quit", _quit_shortcut())
        quit_action.triggered.connect(self.close)

        edit_menu = self._menu(bar, "&Edit")
        # Spelled out rather than taken from QKeySequence.StandardKey: on Linux
        # and Windows StandardKey.Redo resolves to Ctrl+Y, and 04-ui-spec.md's
        # keyboard table promises Ctrl+Shift+Z. Qt maps "Ctrl+" onto Command on
        # macOS by itself, so writing it this way stays correct there too.
        self._add(edit_menu, "&Undo", "Ctrl+Z", arrives=_M1)
        self._add(edit_menu, "&Redo", "Ctrl+Shift+Z", arrives=_M1)
        edit_menu.addSeparator()
        self._add(edit_menu, "&Copy", "Ctrl+C", arrives=_M3)
        self._add(edit_menu, "&Paste", "Ctrl+V", arrives=_M3)
        self._add(edit_menu, "&Duplicate", "Ctrl+D", arrives=_M3)
        self._add(edit_menu, "De&lete", QKeySequence.StandardKey.Delete, arrives=_M3)
        self._add(edit_menu, "&Split at Playhead", "S", arrives=_M3)

        view_menu = self._menu(bar, "&View")
        self._add(view_menu, "Focus &Top View", "1", arrives=_M5)
        self._add(view_menu, "Focus &Front View", "2", arrives=_M5)
        self._add(view_menu, "Focus &3D View", "3", arrives=_M5)
        view_menu.addSeparator()
        self._add(view_menu, "Ruler: &Bars / Beats", arrives=_M3)
        self._add(view_menu, "Ruler: &Minutes / Seconds", arrives=_M3)

        transport_menu = self._menu(bar, "&Transport")
        self._add(transport_menu, "&Play / Pause", "Space", arrives=_M3)
        self._add(transport_menu, "&Stop", "Esc", arrives=_M3)
        self._add(transport_menu, "&Return to Start", "Return", arrives=_M3)
        self._add(transport_menu, "Toggle &Loop", "L", arrives=_M3)
        transport_menu.addSeparator()
        self._add(transport_menu, "Toggle HRTF &Bypass on Channel", "B", arrives=_M3)

        render_menu = self._menu(bar, "&Render")
        self._add(render_menu, "&Render Mix…", "Ctrl+R", arrives=_M7)
        self._add(render_menu, "Render &Stems…", arrives=_M7)

        help_menu = self._menu(bar, "&Help")
        self._add(help_menu, "&Documentation", arrives=_M8)
        self._add(help_menu, f"&About {WINDOW_TITLE}", arrives=_M8)

    def _menu(self, bar: QMenuBar, title: str) -> QMenu:
        """A menu whose action tooltips are actually shown.

        Qt suppresses tooltips inside a QMenu unless asked. Without this the
        explanations below exist in the object model and reach nobody, which
        is a worse failure than not writing them - it looks done.
        """
        menu = bar.addMenu(title)
        menu.setToolTipsVisible(True)
        return menu

    def _add(
        self,
        menu: QMenu,
        text: str,
        shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
        *,
        arrives: str | None = None,
    ) -> QAction:
        """Add an action, disabled unless it does something today.

        `arrives` names the milestone that makes the action real, and passing
        it is what disables the action. 04-ui-spec.md's Craft table requires a
        not-yet-implemented action to say *why* in its tooltip, and "not yet"
        without a "when" is not an answer to that. The same table requires the
        tooltip to carry the shortcut, in the form `Action  (Key)`.
        """
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)

        label = text.replace("&", "").rstrip("…")
        key = action.shortcut().toString()
        tooltip = f"{label}  ({key})" if key else label
        if arrives is not None:
            action.setEnabled(False)
            tooltip = f"{tooltip}\nNot built yet — {arrives}."
        action.setToolTip(tooltip)

        menu.addAction(action)
        return action

    # --------------------------------------------------------------- toolbar

    def _build_toolbar(self) -> None:
        bar = QToolBar("Transport")
        bar.setMovable(False)
        bar.setIconSize(QSize(16, 16))
        self.addToolBar(bar)

        # Tooltips carry the shortcut and say why the button is dead - a dead
        # button with no explanation is the whole reason M0 looked unfinished.
        transport = (
            ("transport_start", "Return to Start", "Return", _M3),
            ("play", "Play / Pause", "Space", _M3),
            ("stop", "Stop", "Esc", _M3),
            ("loop", "Toggle Loop", "L", _M3),
        )
        for name, text, shortcut, arrives in transport:
            bar.addAction(self._tool_action(name, text, shortcut, arrives))

        bar.addSeparator()
        # The playhead readout. Every comparable tool has one, and the ruler
        # alone cannot give you a value you can read off or type back in.
        self._position = self._chip("1.1.000", primary=True)
        self._position.setToolTip(
            "Playhead position, bars.beats.ticks\n"
            "Click the ruler label to switch to minutes:seconds.\n"
            f"Not live yet — {_M3}."
        )
        bar.addWidget(self._position)
        bar.addSeparator()
        bar.addWidget(self._chip("120.0 BPM"))
        bar.addWidget(self._chip("4/4"))
        bar.addSeparator()
        bar.addWidget(self._chip("Snap 1/16"))
        bar.addSeparator()

        for name, text, shortcut in (
            ("undo", "Undo", "Ctrl+Z"),
            ("redo", "Redo", "Ctrl+Shift+Z"),
        ):
            bar.addAction(self._tool_action(name, text, shortcut, _M1))

        bar.addSeparator()

        # A real control rather than a QLabel dressed as one. The label had a
        # border and padding, so it read as the one clickable thing in a
        # toolbar of visibly greyed buttons - the opposite of what it is. As a
        # disabled QToolButton it inherits the same disabled styling as its
        # neighbours, and the dot 04-ui-spec.md draws as "● ARM" is the arm
        # icon, tinted from the palette like every other one (D-50).
        self._arm = QToolButton()
        self._arm.setIcon(icons.icon("arm"))
        self._arm.setText("ARM")
        self._arm.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._arm.setCheckable(True)
        self._arm.setEnabled(False)
        self._arm.setToolTip(f"Automation write-arm  (F-32)\nNot built yet — {_M6}.")
        bar.addWidget(self._arm)

    def _tool_action(
        self, name: str, text: str, shortcut: str, arrives: str
    ) -> QAction:
        action = QAction(icons.icon(name), text, self)
        action.setToolTip(f"{text}  ({shortcut})\nNot built yet — {arrives}.")
        action.setEnabled(False)
        return action

    def _chip(self, text: str, *, primary: bool = False) -> QLabel:
        label = QLabel(text)
        colour = theme.color("text.primary" if primary else "text.secondary")
        label.setStyleSheet(f"color: {colour}; padding: 0 8px;")
        return label

    # ---------------------------------------------------------------- layout

    def _build_layout(self) -> QWidget:
        # Left column: media pool over the context-sensitive params pane.
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(Placeholder("Media Pool", "imported audio, drag to timeline"))
        left.addWidget(Placeholder("Parameters", "follows the current selection"))
        left.setSizes([_POOL_H, _PARAMS_H])

        # Workspace: two tabs (D-49). The editable ortho views share the first
        # because positioning means working in both at once - X/Y then X/Z is
        # one gesture split across two views. The read-only 3D view is for
        # reading the scene, never for editing, so it does not compete for the
        # same pixels.
        ortho = QSplitter(Qt.Orientation.Horizontal)
        ortho.addWidget(Placeholder("Top view", "X / Y — drag to position"))
        ortho.addWidget(Placeholder("Front view", "X / Z — drag for height"))
        ortho.setSizes([600, 600])

        workspace = QTabWidget()
        workspace.setDocumentMode(True)
        workspace.addTab(ortho, "Top / Front")
        workspace.addTab(Placeholder("3D view", "read-only, fixed camera"), "3D")
        workspace.setTabToolTip(0, "The editable orthographic views  (1, 2)")
        workspace.setTabToolTip(1, "Read-only isometric view  (3)")
        # No reference kept: the 1/2/3 actions stay disabled until M5, because
        # selecting the tab is only half of what "Focus Top View" says it does
        # and there is no view to focus yet. M5 wires both halves at once.

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

        for splitter in (left, ortho, upper, root):
            splitter.setHandleWidth(1)
            splitter.setChildrenCollapsible(False)

        return root

    # ------------------------------------------------------------- statusbar

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.showMessage("No project")

        self._xruns = QLabel("xruns 0")
        self._xruns.setStyleSheet(f"color: {theme.color('text.disabled')};")
        self._xruns.setToolTip("Audio dropouts since the stream started")
        bar.addPermanentWidget(self._xruns)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet(f"color: {theme.color('text.disabled')};")
        bar.addPermanentWidget(version)

        self.setStatusBar(bar)
