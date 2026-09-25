"""The project that is open: its model, its undo stack and the file it came from.

M1 built these as three headless pieces and nothing held them together - which
file a project came from, whether it has been saved since, what a failed open
has to leave alone. Those are one object's job, and it is this one (D-85).

It lives in `core/` rather than on the window because all of that is logic,
not presentation. N-5 keeps it testable with no Qt, and the things that need
an owner of the open project that is not a widget are already queued: M2's
import pushes commands from a worker's result, and M3's engine has to hear
when the project changes.

**Edits go through the document, never straight to its stack.** Observers are
told after every change the document makes, so a push that went around it
would leave Undo greyed out after an edit and the title claiming there was
nothing to save - which is the one lie that loses work.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from immersive.core.commands import Command, UndoStack
from immersive.core.io import project_io
from immersive.core.model import Problem, Project
from immersive.core.selection import Selection

#: What a document is called until it has a file.
UNTITLED = "Untitled"


class Document:
    """One open project, the stack that edits it, and where it lives."""

    def __init__(self) -> None:
        self._project = Project()
        self._stack = UndoStack(self._project)
        self._path: Path | None = None
        self._observers: list[Callable[[], None]] = []
        #: What is selected in this project (D-96), pruned after every change
        #: - which is also what empties it on New and Open, since nothing of
        #: the old project is in the new one.
        self._selection = Selection()

    # ------------------------------------------------------------- reading

    @property
    def project(self) -> Project:
        return self._project

    @property
    def selection(self) -> Selection:
        return self._selection

    @property
    def path(self) -> Path | None:
        """The file this project was last opened from or saved to."""
        return self._path

    @property
    def title(self) -> str:
        """The file's stem, or `UNTITLED` for a project never saved."""
        return self._path.stem if self._path is not None else UNTITLED

    @property
    def is_dirty(self) -> bool:
        return self._stack.is_dirty

    @property
    def can_undo(self) -> bool:
        return self._stack.can_undo

    @property
    def can_redo(self) -> bool:
        return self._stack.can_redo

    def observe(self, callback: Callable[[], None]) -> None:
        """Call `callback` after anything about the document changes.

        Plain callbacks, not Qt signals, for the reason D-81 gives for the
        notice log: this has to work with no `QApplication`.
        """
        self._observers.append(callback)

    # ------------------------------------------------------------- editing

    def push(self, command: Command) -> None:
        """Apply `command` through the stack. A refused edit changes nothing."""
        self._stack.push(command)
        self._changed()

    def undo(self) -> bool:
        undone = self._stack.undo()
        if undone:
            self._changed()
        return undone

    def redo(self) -> bool:
        redone = self._stack.redo()
        if redone:
            self._changed()
        return redone

    # --------------------------------------------------------------- files

    def new(self) -> None:
        """An empty, untitled, clean project with no history."""
        self._replace(Project(), None)

    def open(self, path: str | os.PathLike[str]) -> list[Problem]:
        """Replace the open project with the one at `path`.

        ⚠️ **Nothing is replaced until the load has succeeded.** A file that
        is not a project raises `ProjectFileError` and one that cannot be read
        raises its `OSError`, both from `load` - before a single field here
        has changed, so the project that was open is still open, with its
        history and its unsaved changes intact.

        Returns what was wrong but survivable, which today means media that is
        not on this machine (F-3). The project is open either way.
        """
        result = project_io.load(path)
        self._replace(result.project, Path(path).absolute())
        return result.problems

    def save(self) -> None:
        """Write to the file this document already has.

        A document with no file has nowhere to go, and deciding where is a
        question for the person, so that is a `save_as` the caller asks for.
        """
        if self._path is None:
            raise ValueError("an untitled document is saved with save_as")
        self._write(self._path)
        self._changed()

    def save_as(self, path: str | os.PathLike[str]) -> None:
        """Write to `path`, which is where every later `save` goes.

        The path changes only once the write has succeeded: a Save As that
        failed must not leave the next Save aimed at a file that was never
        written.
        """
        target = Path(path).absolute()
        self._write(target)
        self._path = target
        self._changed()

    # ------------------------------------------------------------ internal

    def _write(self, path: Path) -> None:
        """Write and mark saved. Not observed: the caller has more to change."""
        project_io.save(self._project, path)
        self._stack.mark_saved()

    def _replace(self, project: Project, path: Path | None) -> None:
        """A new project gets a new stack: history does not cross projects.

        Keeping the old stack would let Undo reach into a project that is no
        longer open and edit objects nobody can see.
        """
        self._project = project
        self._stack = UndoStack(project)
        self._path = path
        self._changed()

    def _changed(self) -> None:
        # Pruned first: a widget reading the selection during this notice
        # must not find a clip the change has just taken away (D-96).
        self._selection.prune(self._project)
        for callback in list(self._observers):
            callback()
