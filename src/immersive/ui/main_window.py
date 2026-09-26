"""The application shell: menus, toolbar, splitter layout, status bar.

M0 builds the frame only — every region is a Placeholder. The layout and its
proportions come from docs/04-ui-spec.md, and the splitter structure there is
deliberate: a fixed layout with draggable splitters, not dockable panels
(D-15).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from immersive import __version__
from immersive.audio.audition import Audition
from immersive.core.commands import Compound
from immersive.core.document import Document
from immersive.core.edits import (
    AddMedia,
    DuplicateClips,
    PasteClips,
    RemoveClips,
    SetAttribute,
    SplitClips,
)
from immersive.core.io import project_io
from immersive.core.io.media import Refused
from immersive.core.media_store import SUFFIXES, MediaStore, Prepared, admit, find_audio
from immersive.core.model import MediaFile, Project, SnapSetting
from immersive.core.relink import relink
from immersive.core.selection import Kind
from immersive.ui import icons, theme, theme_io, theme_menu
from immersive.ui.explorer.media_pool import MediaPool
from immersive.ui.importer import Importer
from immersive.ui.notices import NoticeLog, Severity
from immersive.ui.notices import worst as notices_worst
from immersive.ui.parameters.pane import ParametersPane
from immersive.ui.parameters.views import TEMPO_CEILING, TEMPO_FLOOR
from immersive.ui.theme_menu import ThemeMenu
from immersive.ui.time_axis import TimeAxis
from immersive.ui.timeline.grid import Unit, snap_text
from immersive.ui.timeline.panel import TimelinePanel
from immersive.ui.timeline.snap_menu import fill_snap_menu
from immersive.ui.units import Plain
from immersive.ui.widgets.notices import NoticeCount
from immersive.ui.widgets.numeric import NumericField
from immersive.ui.widgets.placeholder import Placeholder

WINDOW_TITLE = "3d immersive"

#: What the signature chip offers. Anything else is typed in the pane.
COMMON_SIGNATURES = ((2, 4), (3, 4), (4, 4), (5, 4), (6, 8), (7, 8), (12, 8))

#: What the Open and Save As dialogs show.
PROJECT_FILTER = f"3d immersive project (*{project_io.SUFFIX})"

#: What the Import Audio dialog shows: F-5's formats (D-93).
AUDIO_FILTER = "Audio ({})".format(
    " ".join(f"*{suffix}" for suffix in sorted(SUFFIXES))
)


class Unsaved(Enum):
    """The three answers to "save changes first?" - 04's one confirmation."""

    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


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
    #: A problem reported from PortAudio's thread, posted on the UI thread.
    #: Emitting a signal is the one thing that thread may do here.
    _audio_problem = Signal(str)

    def __init__(self, audition: Audition | None = None, unavailable: str = "") -> None:
        super().__init__()
        #: How samples are heard (F-8), or `None` with the reason in
        #: `unavailable`. A window built by a test has neither, and hears
        #: nothing: only a real launch goes looking for a sound card.
        self._audition = audition
        self._unavailable = unavailable
        #: Everything this session has reported (F-56, D-65). Built before
        #: the status bar, which draws it.
        self._notices = NoticeLog()
        self._audio_problem.connect(self._report_audio_problem)
        if audition is not None:
            audition.report = self._audio_problem.emit
        #: The project that is open (D-85). Every edit goes through it, and
        #: the window reads its state back after each one rather than keeping
        #: a second copy that could disagree.
        self._document = Document()
        #: The session's decoded audio and peaks, by media id - not the model,
        #: and not saved. Kept across Undo so Redo of an import is free.
        self._store = MediaStore()
        self._importer = Importer(self)
        self._importer.finished.connect(self._imported)
        #: Fills the store for a project opened from disk, which imports
        #: never touched: the same workers, and no edit.
        self._loader = Importer(self)
        self._loader.finished.connect(self._loaded)
        self._loading: list[MediaFile] = []
        self._loading_into: Project | None = None
        #: The project an import in flight is for. A different one by the
        #: time it finishes means the person opened another, and the samples
        #: must not land in it.
        self._importing_into: Project | None = None
        #: Which span of the timeline is on show, and at what zoom (D-94).
        #: Held here rather than by the timeline, because the curve editor at
        #: M6 observes the same one and neither panel may own it.
        self._axis = TimeAxis()
        #: Widgets that paint themselves from a token, and the token they use.
        #: Kept so a theme change can ask for the colour again (D-82).
        self._chips: list[tuple[QLabel, str]] = []
        self._icon_actions: list[tuple[QAction, str]] = []
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(icons.app_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1024, 680)

        self._build_menus()
        self._build_toolbar()
        self.setCentralWidget(self._build_layout())
        self._build_statusbar()
        self._document.observe(self._document_changed)
        self._document.selection.observe(self._selection_changed)
        self._document_changed()
        self._selection_changed()
        # Last, because it may report - and the notice centre it reports to
        # is built by _build_statusbar.
        self.restore_theme()

    # ----------------------------------------------------------------- menus

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.setMouseTracking(True)
        self._menu_hover = _MenuBarHover(self)
        bar.installEventFilter(self._menu_hover)

        file_menu = self._menu(bar, "&File")
        self._add(file_menu, "&New Project", "Ctrl+N").triggered.connect(
            self.new_project
        )
        self._add(file_menu, "&Open Project…", "Ctrl+O").triggered.connect(
            lambda: self.open_project()
        )
        file_menu.addSeparator()
        self._add(file_menu, "&Save", "Ctrl+S").triggered.connect(self.save_project)
        self._add(file_menu, "Save &As…", "Ctrl+Shift+S").triggered.connect(
            self.save_project_as
        )
        file_menu.addSeparator()
        self._add(file_menu, "&Import Audio…", "Ctrl+I").triggered.connect(
            self.import_files
        )
        self._add(file_menu, "Import &Folder…", "Ctrl+Shift+I").triggered.connect(
            self.import_folder
        )
        file_menu.addSeparator()
        quit_action = self._add(file_menu, "&Quit", _quit_shortcut())
        quit_action.triggered.connect(self.close)

        edit_menu = self._menu(bar, "&Edit")
        # Spelled out rather than taken from QKeySequence.StandardKey: on Linux
        # and Windows StandardKey.Redo resolves to Ctrl+Y, and 04-ui-spec.md's
        # keyboard table promises Ctrl+Shift+Z. Qt maps "Ctrl+" onto Command on
        # macOS by itself, so writing it this way stays correct there too.
        self._undo = self._history_action(edit_menu, "undo", "&Undo", "Ctrl+Z")
        self._redo = self._history_action(edit_menu, "redo", "&Redo", "Ctrl+Shift+Z")
        self._undo.triggered.connect(self._document.undo)
        self._redo.triggered.connect(self._document.redo)
        edit_menu.addSeparator()
        self._add(edit_menu, "Add &Channel").triggered.connect(
            lambda: self._timeline.add_channel()
        )
        edit_menu.addSeparator()
        # Ctrl+A in a text field selects its text: a line edit claims the
        # standard key before any window action sees it.
        self._add(edit_menu, "Select &All", "Ctrl+A").triggered.connect(
            lambda: self._timeline.view.select_all()
        )
        # Spelled out, as Redo is: the keyboard table is the specification
        # (D-68). A line edit claims all three for its text before any action
        # here does.
        self._cut = self._add(edit_menu, "Cu&t", "Ctrl+X")
        self._cut.triggered.connect(self.cut_clips)
        self._copy = self._add(edit_menu, "&Copy", "Ctrl+C")
        self._copy.triggered.connect(self.copy_clips)
        self._paste = self._add(edit_menu, "&Paste", "Ctrl+V")
        self._paste.triggered.connect(self.paste_clips)
        self._duplicate = self._add(edit_menu, "&Duplicate", "Ctrl+D")
        self._duplicate.triggered.connect(self.duplicate_clips)
        self._delete = self._add(edit_menu, "De&lete", QKeySequence.StandardKey.Delete)
        self._delete.triggered.connect(self.delete_clips)
        self._split = self._add(edit_menu, "&Split at Playhead", "S")
        self._split.triggered.connect(self.split_clips)

        view_menu = self._menu(bar, "&View")
        self._add(view_menu, "Focus &Top View", "1", arrives=_M5)
        self._add(view_menu, "Focus &Front View", "2", arrives=_M5)
        self._add(view_menu, "Focus &3D View", "3", arrives=_M5)
        view_menu.addSeparator()
        # One checked pair: the ruler counts in one unit at a time (F-19).
        self._ruler_units = QActionGroup(self)
        for text, unit in (
            ("Ruler: &Bars / Beats", Unit.BARS),
            ("Ruler: &Minutes / Seconds", Unit.TIME),
        ):
            action = self._add(view_menu, text)
            action.setCheckable(True)
            action.setChecked(unit is Unit.BARS)
            self._ruler_units.addAction(action)
            action.triggered.connect(
                lambda _checked=False, unit=unit: self.set_ruler_unit(unit)
            )
        view_menu.addSeparator()
        # M8 promotes this into Preferences; the menu is what M9 ships
        # (F-48). It lives under View because it changes how things look,
        # not what they are.
        self._theme_menu = ThemeMenu("&Theme", self, self.choose_theme)
        self._theme_menu.setToolTipsVisible(True)
        view_menu.addMenu(self._theme_menu)

        transport_menu = self._menu(bar, "&Transport")
        self._add(transport_menu, "&Play / Pause", "Space", arrives=_M3)
        self._add(transport_menu, "&Stop", "Esc", arrives=_M3)
        self._add(transport_menu, "&Return to Start", "Return", arrives=_M3)
        self._add(transport_menu, "Toggle &Loop", "L", arrives=_M3)
        transport_menu.addSeparator()
        self._bypass = self._add(transport_menu, "Toggle HRTF &Bypass on Channel", "B")
        self._bypass.triggered.connect(self.toggle_bypass)

        render_menu = self._menu(bar, "&Render")
        self._add(render_menu, "&Render Mix…", "Ctrl+R", arrives=_M7)
        self._add(render_menu, "Render &Stems…", arrives=_M7)

        help_menu = self._menu(bar, "&Help")
        self._add(help_menu, "&Documentation", arrives=_M8)
        self._add(help_menu, f"&About {WINDOW_TITLE}", arrives=_M8)

    def _history_action(
        self, menu: QMenu, icon: str, text: str, shortcut: str
    ) -> QAction:
        """Undo or Redo: one action, shown in the menu and on the toolbar.

        One object rather than two kept in step, so the menu and the toolbar
        cannot disagree about whether there is anything to undo. The icon is
        for the toolbar; menus in this application carry none.
        """
        action = self._add(menu, text, shortcut)
        action.setIcon(icons.icon(icon))
        action.setIconVisibleInMenu(False)
        self._icon_actions.append((action, icon))
        return action

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
        # The open project's tempo, signature and snap, read back after every
        # change the document reports, and each a control: the tempo dragged
        # or typed, the signature and the snap chosen from a menu (F-16). The
        # pane edits the same two, and any signature the menu does not list.
        self._tempo = NumericField(
            120.0,
            minimum=TEMPO_FLOOR,
            maximum=TEMPO_CEILING,
            step=0.1,
            format=Plain("BPM", 1),
        )
        self._tempo.setObjectName("TempoField")
        self._tempo.setFixedWidth(92)
        # Out of the focus chain, like the snap chip, so the window does not
        # open with a ring around it; a click still gives it the keyboard.
        self._tempo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._tempo.setToolTip(
            "Tempo — drag, or click and type. The grid moves; clips do not."
        )
        self._tempo.committed.connect(self._set_tempo)
        self._signature_chip = QToolButton()
        self._signature_chip.setObjectName("SignatureChip")
        self._signature_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._signature_chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._signature_chip.setMenu(QMenu(self._signature_chip))
        self._signature_chip.menu().aboutToShow.connect(self.signature_menu)
        self._signature_chip.setToolTip(
            "Time signature\nAny other in the parameters pane, with nothing selected."
        )
        self._snap_chip = QToolButton()
        self._snap_chip.setObjectName("SnapChip")
        # Like the buttons the toolbar makes for its actions: out of the
        # focus chain, so the window does not open with a ring around it.
        self._snap_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._snap_chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._snap_chip.setMenu(QMenu(self._snap_chip))
        self._snap_chip.menu().aboutToShow.connect(self.snap_menu)
        self._snap_chip.setToolTip(
            "Snap — the grid a drag lands on, and whether it snaps at all\n"
            "Hold Alt while dragging to place exactly."
        )
        bar.addWidget(self._tempo)
        bar.addWidget(self._signature_chip)
        bar.addSeparator()
        bar.addWidget(self._snap_chip)
        bar.addSeparator()

        bar.addAction(self._undo)
        bar.addAction(self._redo)

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
        # icons.icon() memoises the rendered QIcon, so a theme change needs
        # the action's icon set again rather than merely invalidated - phase
        # 1's Outcome flagged this and D-82 is where it gets paid for.
        self._icon_actions.append((action, name))
        return action

    def _chip(self, text: str, *, primary: bool = False) -> QLabel:
        """A toolbar readout, remembered by the token it is drawn in.

        The token rather than the colour, because D-82's walk has to be able
        to ask for it again under a different theme.
        """
        label = QLabel(text)
        token = "text.primary" if primary else "text.secondary"
        self._chips.append((label, token))
        label.setStyleSheet(f"color: {theme.color(token)}; padding: 0 8px;")
        return label

    # ---------------------------------------------------------------- layout

    def _build_layout(self) -> QWidget:
        # Left column: media pool over the context-sensitive params pane.
        left = QSplitter(Qt.Orientation.Vertical)
        self._pool = MediaPool(self._document, self._store, self.audition_media)
        self._pool.set_hearing(
            "Double-click to hear it"
            if self._audition is not None
            else f"Cannot be heard: {self._unavailable or 'no audio output'}"
        )
        left.addWidget(self._pool)
        self._parameters = ParametersPane(
            self._document,
            unit=lambda: self._timeline.unit(),
            peaks=self._store.peaks,
            audition=self.audition_media if self._audition is not None else None,
            unavailable=self._unavailable,
        )
        left.addWidget(self._parameters)
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
        self._timeline = TimelinePanel(self._document, self._axis, self._store)
        root.addWidget(self._timeline)
        root.setSizes([950 - _TIMELINE_H, _TIMELINE_H])
        root.setStretchFactor(0, 1)

        for splitter in (left, ortho, upper, root):
            splitter.setHandleWidth(1)
            splitter.setChildrenCollapsible(False)

        return root

    # ------------------------------------------------------------- statusbar

    def _build_statusbar(self) -> None:
        bar = QStatusBar()

        self._xruns = QLabel("xruns 0")
        self._xruns.setStyleSheet(f"color: {theme.color('text.disabled')};")
        self._xruns.setToolTip("Audio dropouts since the stream started")
        bar.addPermanentWidget(self._xruns)

        # 04-ui-spec.md, *Accessibility and feel*: left to right, the master
        # meter (M3), the notice count, the version.
        self._notice_count = NoticeCount(self._notices)
        bar.addPermanentWidget(self._notice_count)
        self._notices.observe(self._notices_changed)

        self._version = QLabel(f"v{__version__}")
        self._version.setStyleSheet(f"color: {theme.color('text.disabled')};")
        bar.addPermanentWidget(self._version)

        self.setStatusBar(bar)

    # ---------------------------------------------------------- document

    def document(self) -> Document:
        """The open project. Edits go through it, never around it (D-85)."""
        return self._document

    def new_project(self) -> bool:
        """File > New. False when the person chose to keep what was open."""
        if not self._may_discard():
            return False
        self._store.clear()
        self._document.new()
        return True

    def open_project(self, path: Path | None = None) -> bool:
        """File > Open. `path` skips the dialog, for a caller that has one.

        A file that will not open is an `error` notice and nothing else: the
        document leaves the open project exactly as it was (D-85). Media that
        is not on this machine is one `warn` notice for the whole open, with a
        line per file (F-3) - one open raising the count once per sample that
        moved would be counting the wrong thing.
        """
        if not self._may_discard():
            return False
        chosen = path if path is not None else self._choose_open_path()
        if chosen is None:
            return False
        try:
            self._document.open(chosen)
        except project_io.ProjectFileError as refused:
            self._report_failure(
                f"{chosen.name} could not be opened",
                [str(problem) for problem in refused.problems],
            )
            return False
        except OSError as unreadable:
            self._report_failure(
                f"{chosen.name} could not be opened", [_reason(unreadable)]
            )
            return False

        # Reaching here, the open succeeded: every failure returned above.
        self._store.clear()
        self._load_samples()

        missing = [
            media for media in self._document.project.media_pool if media.missing
        ]
        if missing:
            count = len(missing)
            self._notices.add(
                Severity.WARN,
                f"{chosen.name} opened with {count} media "
                f"file{'s' if count != 1 else ''} missing",
                [media.path for media in missing],
            )
        return True

    def save_project(self) -> bool:
        """File > Save. An untitled project asks where, through Save As."""
        path = self._document.path
        if path is None:
            return self.save_project_as()
        return self._written(path, self._document.save)

    def save_project_as(self) -> bool:
        """File > Save As. A name typed without a suffix gets `.3dim`.

        Otherwise a project saved as "mix" is written, and then hidden by the
        Open dialog's own filter the next time anyone looks for it.
        """
        chosen = self._choose_save_path()
        if chosen is None:
            return False
        if not chosen.suffix:
            chosen = chosen.with_suffix(project_io.SUFFIX)
        target = chosen
        return self._written(target, lambda: self._document.save_as(target))

    def audition_media(self, media_id: str) -> bool:
        """Play a sample straight to the output, replacing any other (F-8)."""
        audio = self._store.audio(media_id)
        if self._audition is None or audio is None:
            return False
        self._audition.play(audio.audio)
        return True

    def _report_audio_problem(self, message: str) -> None:
        self._notices.add(Severity.WARN, message)

    def timeline(self) -> TimelinePanel:
        return self._timeline

    def pool(self) -> MediaPool:
        return self._pool

    def store(self) -> MediaStore:
        """The session's decoded audio and peaks, by media id."""
        return self._store

    def importing(self) -> bool:
        """Whether workers are still preparing samples - imported or loaded."""
        return self._importer.busy or self._loader.busy

    def _load_samples(self) -> None:
        """Prepare the opened project's samples that are here, into the store.

        Not an edit: nothing in the model changes, so nothing is marked
        unsaved and no hash is written into an old project (D-89). Samples
        whose files have gone are not tried - they are already reported.
        """
        present = [
            media for media in self._document.project.media_pool if not media.missing
        ]
        if not present or self._loader.busy:
            return
        self._loading = present
        self._loading_into = self._document.project
        self._loader.start([Path(media.path) for media in present])

    def _loaded(self, results: list[Prepared | Refused]) -> None:
        loading, self._loading = self._loading, []
        into, self._loading_into = self._loading_into, None
        if into is not self._document.project:
            return
        trouble: list[str] = []
        for media, result in zip(loading, results, strict=True):
            if isinstance(result, Refused):
                trouble.append(str(result))
                continue
            self._store.keep(media.id, result)
            if media.hash and media.hash != result.hash:
                trouble.append(f"{media.name}: has changed since the project was saved")
        if trouble:
            self._notices.add(
                Severity.WARN,
                f"{len(trouble)} sample{'s' if len(trouble) != 1 else ''} "
                "did not load as saved",
                trouble,
            )
        self._pool.tree.viewport().update()
        self._timeline.media_changed()
        self._parameters.refresh()

    def import_files(self) -> bool:
        """File > Import Audio. Several files, prepared on workers."""
        return self.import_paths(self._choose_audio_files())

    def import_folder(self) -> bool:
        """File > Import Folder. Everything F-5 can read beneath it (D-93)."""
        folder = self._choose_folder()
        if folder is None:
            return False
        found = find_audio(folder)
        if not found:
            self._notices.add(
                Severity.INFO, f"No audio found in {folder.name}", [str(folder)]
            )
            return False
        return self.import_paths(found)

    def import_paths(self, paths: list[Path]) -> bool:
        """Prepare `paths` on workers; the pool fills when all are in (N-3)."""
        if not paths or self._importer.busy:
            return False
        self._importing_into = self._document.project
        self._importer.start(list(paths))
        return True

    def _imported(self, results: list[Prepared | Refused]) -> None:
        """On the UI thread, the only place the model is edited from.

        One import is one edit, so one Undo takes back a folder of forty.
        Everything that did not come in is one notice with a line each -
        success on its own is quiet, since the pool itself shows it.
        """
        into, self._importing_into = self._importing_into, None
        if into is not self._document.project:
            self._notices.add(
                Severity.INFO,
                "Import set aside: another project was opened while it ran",
                [str(result.path) for result in results],
            )
            return

        admission = admit(self._document.project, results)
        if admission.admitted:
            for entry, prepared in admission.admitted:
                self._store.keep(entry.id, prepared)
            self._document.push(
                AddMedia(
                    self._document.project, [entry for entry, _ in admission.admitted]
                )
            )
            self._timeline.media_changed()

        detail = [str(refusal) for refusal in admission.refused] + [
            f"{path.name}: already in the pool" for path in admission.already
        ]
        if detail:
            count = len(admission.admitted)
            self._notices.add(
                Severity.WARN if admission.refused else Severity.INFO,
                f"Imported {count} of {len(results)} "
                f"file{'s' if len(results) != 1 else ''}",
                detail,
            )

    def relink_media(self, media: MediaFile, path: Path) -> bool:
        """Point a sample at another file, and say what that did (D-90).

        M8's relink dialog is the caller in waiting. The same audio is quiet;
        different audio is allowed and is a `warn`, because the person should
        know the sample they placed has changed under their clips; a file that
        cannot stand in is an `error`, since what they asked for did not
        happen.
        """
        name = media.name
        result = relink(self._document, media, path)
        if isinstance(result, Refused):
            self._report_failure(f"{name} was not relinked", [str(result)])
            return False
        if result.same_audio is False:
            self._notices.add(
                Severity.WARN,
                f"{name} now points at different audio",
                [f"{path} is not the file this sample was imported from"],
            )
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        """Quit asks, like New and Open, and Cancel keeps the window."""
        if self._may_discard():
            if self._audition is not None:
                self._audition.close()
            event.accept()
        else:
            event.ignore()

    def _written(self, path: Path, write: Callable[[], None]) -> bool:
        """Run a save, and turn a failure into a notice rather than a crash."""
        try:
            write()
        except project_io.ProjectFileError as refused:
            self._report_failure(
                f"{path.name} was not saved",
                [str(problem) for problem in refused.problems],
            )
            return False
        except OSError as failed:
            self._report_failure(f"{path.name} was not saved", [_reason(failed)])
            return False
        return True

    def _report_failure(self, message: str, detail: list[str]) -> None:
        self._notices.add(Severity.ERROR, message, detail)

    def _may_discard(self) -> bool:
        """Whether the open project may be replaced or closed.

        ⚠️ **Save goes ahead only if the save worked.** A Save As dialog that
        was cancelled, or a write that failed, must not be followed by
        throwing away the project somebody just asked to keep.
        """
        if not self._document.is_dirty:
            return True
        answer = self._ask_about_unsaved()
        if answer is Unsaved.CANCEL:
            return False
        if answer is Unsaved.SAVE:
            return self.save_project()
        return True

    # --- the places this window waits for a person. Methods, so a
    # --- test replaces them; conftest.py fails any test that reaches the
    # --- real dialogs instead of hanging on them.

    def _ask_about_unsaved(self) -> Unsaved:
        """04's one confirmation. An instance and `exec()`, never the static
        `QMessageBox.question`, which runs its loop where no test can reach."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(WINDOW_TITLE)
        box.setText(f"Save changes to {self._document.title}?")
        box.setInformativeText("Your changes will be lost if you don't save them.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        box.setEscapeButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return {
            QMessageBox.StandardButton.Save: Unsaved.SAVE,
            QMessageBox.StandardButton.Discard: Unsaved.DISCARD,
        }.get(box.standardButton(box.clickedButton()), Unsaved.CANCEL)

    def _choose_open_path(self) -> Path | None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Open Project", self._dialog_directory(), PROJECT_FILTER
        )
        return Path(chosen) if chosen else None

    def _choose_save_path(self) -> Path | None:
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", self._dialog_directory(), PROJECT_FILTER
        )
        return Path(chosen) if chosen else None

    def _choose_audio_files(self) -> list[Path]:
        chosen, _ = QFileDialog.getOpenFileNames(
            self, "Import Audio", self._dialog_directory(), AUDIO_FILTER
        )
        return [Path(each) for each in chosen]

    def _choose_folder(self) -> Path | None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Import Folder", self._dialog_directory()
        )
        return Path(chosen) if chosen else None

    def _dialog_directory(self) -> str:
        path = self._document.path
        return str(path.parent) if path is not None else ""

    def _document_changed(self) -> None:
        """Read the document back into everything that shows it.

        The title uses Qt's `[*]` placeholder, so unsaved changes are marked
        the way each platform marks them - an asterisk on Windows and Linux, a
        dot in the close button on macOS - rather than one glyph imposed on
        all three.
        """
        document = self._document
        self.setWindowTitle(f"{document.title}[*] — {WINDOW_TITLE}")
        project = document.project
        self._tempo.set_value(project.bpm)
        self._signature_chip.setText("{}/{}".format(*project.time_signature))
        self._snap_chip.setText(snap_text(project.snap))
        self.setWindowModified(document.is_dirty)
        for action, able, nothing in (
            (self._undo, document.can_undo, "Nothing to undo."),
            (self._redo, document.can_redo, "Nothing to redo."),
        ):
            action.setEnabled(able)
            # 04, Craft: a disabled control says why. "Not built yet" is one
            # reason; having nothing to undo is the other.
            summary = action.toolTip().partition("\n")[0]
            action.setToolTip(summary if able else f"{summary}\n{nothing}")
        self._clipboard_changed()

    # ----------------------------------------------------------- theming

    def restore_theme(self) -> None:
        """Re-apply whatever the last session chose (D-83).

        Quiet when it works: a notice saying "Theme: VS Code Dark" on every
        launch is the kind of report that teaches people to stop reading
        them. A theme that has *gone* is the opposite - somebody deleted the
        file they were using, and an application that silently looks
        different is one they conclude is broken.
        """
        remembered = theme_menu.remembered()
        if remembered is None:
            self._theme_menu.set_current(None)
            self.apply_theme(theme_io.builtin())
            return

        if not remembered.is_file():
            # Apply it, do not merely record it. "Falls back to the built-in"
            # is a statement about what the window is painted in, and a
            # branch that only ticked the menu entry would leave whatever was
            # active on screen while claiming to have fallen back.
            self._theme_menu.set_current(None)
            self.apply_theme(theme_io.builtin())
            self._notices.add(
                Severity.WARN,
                f"{remembered.name} is no longer there — using the built-in theme",
                [str(remembered)],
            )
            return

        self._theme_menu.set_current(remembered)
        self.choose_theme(remembered, announce=False, remember=False)

    def choose_theme(
        self, path: Path | None, *, announce: bool = True, remember: bool = True
    ) -> None:
        """Load and apply the theme at `path`. `None` is the bundled one.

        Nothing here can fail in a way the user has to care about, which is
        F-47: a theme file that is missing, malformed or full of unknown keys
        still yields a usable `Theme`, and everything wrong with it goes to
        the notice centre instead of a dialog.

        `announce` and `remember` are both off when restoring a previous
        session's choice: it is not news, and writing back what was just read
        is a good way to turn a read bug into a stored one.
        """
        if remember:
            theme_menu.remember(path)

        if path is None:
            self.apply_theme(theme_io.builtin())
            if announce:
                self._notices.add(Severity.INFO, f"Theme: {theme_io.builtin().name}")
            return

        report = theme_io.load(path)
        self.apply_theme(report.theme)
        severity = (
            notices_worst(problem.severity for problem in report.problems)
            or Severity.INFO
        )
        headline = (
            f"Theme: {report.theme.name}"
            if report.applied
            else f"{path.name} could not be used"
        )
        if report.problems:
            headline = f"{headline} — {len(report.problems)} problem" + (
                "s" if len(report.problems) != 1 else ""
            )
        if announce or report.problems:
            self._notices.add(
                severity, headline, [str(problem) for problem in report.problems]
            )

    def apply_theme(self, chosen: theme.Theme) -> None:
        """Repaint the running application in `chosen` (D-82).

        ⚠️ **The order is the decision, not an implementation detail.** The
        active theme has to land first, then the icon caches have to be
        dropped, then the application stylesheet, and only then the walk -
        because every widget in that walk re-reads its colours through the
        accessor, and one that runs before `use()` has landed gets the colour
        it already had.

        **A theme that is already applied is not applied again.** Qt re-polishes
        every widget on every `setStyleSheet`, identical sheet or not, and a
        fresh window's `restore_theme()` asks for exactly the theme
        `build_application()` has just applied - which was half the cost of
        building a window, for nothing that changes on screen. Both halves of
        the check are needed: the active theme can be right while the
        application still wears another's sheet, and then it has to be
        painted. The sheet is compared only once the theme matches, so a real
        switch does exactly the work, in exactly the order, described above.
        """
        app = QApplication.instance()
        if (
            chosen == theme.active()
            and isinstance(app, QApplication)
            and app.styleSheet() == theme.stylesheet(chosen)
        ):
            return

        theme.use(chosen)
        icons.icon.cache_clear()
        icons.app_icon.cache_clear()

        if isinstance(app, QApplication):
            app.setStyleSheet(theme.stylesheet(chosen))

        for widget in [self, *self.findChildren(QWidget)]:
            repaint = getattr(widget, "retheme", None)
            if callable(repaint):
                repaint()

    def retheme(self) -> None:
        """Re-read everything this window paints itself with.

        The window's own share of the walk: the chips and status labels hold
        inline stylesheets, and the icons are memoised renderings that have
        to be asked for again rather than merely invalidated.
        """
        self.setWindowIcon(icons.app_icon())
        for action, name in self._icon_actions:
            action.setIcon(icons.icon(name))
        self._arm.setIcon(icons.icon("arm"))
        for label, token in self._chips:
            label.setStyleSheet(f"color: {theme.color(token)}; padding: 0 8px;")
        for label in (self._xruns, self._version):
            label.setStyleSheet(f"color: {theme.color('text.disabled')};")

    def toggle_bypass(self) -> None:
        """B: HRTF bypass on every selected channel, as one edit. If any is
        off they all go on; if all are on they all go off - so one press
        never leaves the selection split."""
        channels = self._document.selection.channels()
        if not channels:
            return
        on = not all(channel.hrtf_bypass for channel in channels)
        self._document.push(
            Compound(
                [
                    SetAttribute(channel, "hrtf_bypass", on)
                    for channel in channels
                    if channel.hrtf_bypass != on
                ]
            )
        )

    def snap_menu(self) -> QMenu:
        """The snap chip's menu, filled for the project's setting as it is
        now; each choice is one command."""
        project = self._document.project

        def choose(chosen: SnapSetting | None) -> None:
            if chosen is not None and chosen != project.snap:
                self._document.push(SetAttribute(project, "snap", chosen))

        return fill_snap_menu(self._snap_chip.menu(), project.snap, choose)

    def _set_tempo(self, bpm: float) -> None:
        # The field commits only a value that differs from the one it shows,
        # which is the project's.
        self._document.push(SetAttribute(self._document.project, "bpm", bpm))

    def signature_menu(self) -> QMenu:
        """The signature chip's menu: the common ones, the project's checked,
        each one command. Any other is set in the pane."""
        menu = self._signature_chip.menu()
        menu.clear()
        project = self._document.project
        for signature in COMMON_SIGNATURES:
            action = menu.addAction("{}/{}".format(*signature))
            action.setCheckable(True)
            action.setChecked(signature == project.time_signature)
            action.triggered.connect(
                lambda _checked=False, chosen=signature: self._set_signature(chosen)
            )
        return menu

    def _set_signature(self, signature: tuple[int, int]) -> None:
        project = self._document.project
        if signature != project.time_signature:
            self._document.push(SetAttribute(project, "time_signature", signature))

    def set_ruler_unit(self, unit: Unit) -> None:
        """What the ruler counts in, and so what the pane's positions read."""
        self._timeline.set_unit(unit)
        self._parameters.refresh()

    def parameters(self) -> ParametersPane:
        return self._parameters

    def split_clips(self) -> None:
        """S: every selected clip under the playhead in two, as one edit;
        the tails join the selection beside their heads."""
        selection = self._document.selection
        split = SplitClips(
            self._document.project, selection.clips(), self._timeline.playhead()
        )
        if split.changes:
            self._document.push(split)
            selection.add(Kind.CLIPS, split.tails)

    def duplicate_clips(self) -> None:
        """Ctrl+D: the selection copied to just after itself, and the copies
        selected, so pressing it again carries the run on."""
        selection = self._document.selection
        duplicate = DuplicateClips(self._document.project, selection.clips())
        if duplicate.changes:
            self._document.push(duplicate)
            selection.select(Kind.CLIPS, duplicate.copies)

    def delete_clips(self) -> None:
        """Delete: every selected clip, as one edit."""
        remove = RemoveClips(self._document.project, self._document.selection.clips())
        if remove.changes:
            self._document.push(remove)

    def copy_clips(self) -> None:
        """Ctrl+C: copies of the selected clips onto the clipboard (D-99).
        Not an edit - the project is as it was, and nothing is unsaved."""
        clips = self._document.selection.clips()
        if not clips:
            return
        self._document.clipboard.hold(self._document.project, clips)
        self._clipboard_changed()

    def cut_clips(self) -> None:
        """Ctrl+X: Copy, and then Delete as one edit. Undo puts the clips
        back and leaves the clipboard as it is."""
        clips = self._document.selection.clips()
        if not clips:
            return
        self._document.clipboard.hold(self._document.project, clips)
        self._document.push(RemoveClips(self._document.project, clips))

    def paste_clips(self) -> None:
        """Ctrl+V: the clipboard at the playhead on the focused channel, as
        one edit (D-100); what was pasted becomes the selection, so it can
        be moved at once."""
        document = self._document
        clipboard = document.clipboard
        if not clipboard.pastable(document.project):
            return
        paste = PasteClips(
            document.project,
            clipboard.held(),
            clipboard.lane(document.project, self._timeline.view.focused()),
            self._timeline.playhead(),
            theme.active().channels,
        )
        document.push(paste)
        document.selection.select(Kind.CLIPS, paste.copies)

    def _clipboard_changed(self) -> None:
        """Paste is enabled exactly when the clipboard can be pasted - after
        a Copy, and after any edit, since an Undo can take a copied clip's
        sample out of the pool (D-99)."""
        document = self._document
        able = document.clipboard.pastable(document.project)
        if able:
            why = ""
        elif document.clipboard:
            why = "\nA copied clip's sample is no longer in the pool."
        else:
            why = "\nCut or copy a clip first."
        summary = self._paste.toolTip().partition("\n")[0]
        self._paste.setEnabled(able)
        self._paste.setToolTip(summary + why)

    def _selection_changed(self) -> None:
        """What acts on the selection is enabled exactly when it can act."""
        kind = self._document.selection.kind
        for action, able, wanted in (
            (self._bypass, kind is Kind.CHANNELS, "a channel"),
            (self._cut, kind is Kind.CLIPS, "a clip"),
            (self._copy, kind is Kind.CLIPS, "a clip"),
            (self._split, kind is Kind.CLIPS, "a clip"),
            (self._duplicate, kind is Kind.CLIPS, "a clip"),
            (self._delete, kind is Kind.CLIPS, "a clip"),
        ):
            action.setEnabled(able)
            summary = action.toolTip().partition("\n")[0]
            action.setToolTip(summary if able else f"{summary}\nSelect {wanted} first.")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Esc clears the selection while the transport is stopped (04,
        *Selection*). Until phase 9 it always is: Transport > Stop, which
        owns Esc, is disabled, and a disabled action's shortcut lets the key
        through to here. Phase 9's Stop must do the same when stopped."""
        if event.key() == Qt.Key.Key_Escape:
            self._document.selection.clear()
            event.accept()
            return
        super().keyPressEvent(event)

    def notices(self) -> NoticeLog:
        """This session's notice log, for anything that needs to report.

        M2's missing media is the next caller after the theme picker (F-3).
        """
        return self._notices

    def _notices_changed(self) -> None:
        """The status line carries the newest; the count carries the rest."""
        if (latest := self._notices.latest()) is not None:
            self.statusBar().showMessage(latest.message)
        self._notice_count.refresh()


def _reason(error: OSError) -> str:
    """What the filesystem said, without Python's `[Errno 2]` wrapping."""
    return error.strerror or str(error)
