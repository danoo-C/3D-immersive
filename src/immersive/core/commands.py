"""The command pattern, and the only thing allowed to run it.

After this module exists, nothing mutates the model except through an
`UndoStack`. That is D-14's day-one requirement, and the reason for it is
narrow: retrofitting undo means rewriting every editing path, so there is never
a better moment than before there are any.

Commands store **inverse operations, not snapshots** — the old value of a
field, the index a channel came out of. Storing a copy of the project per edit
would turn F-4's "unlimited depth" into a memory leak with a nice name, and it
is why model.py's dataclasses are mutable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from immersive.core.model import Problem, Project, validate


class Command(ABC):
    """One reversible mutation.

    A command is constructed against the objects it edits and then takes no
    arguments. The alternative — passing the project into `do()` — reads
    tidier and forces every command to re-find its target by id on each call,
    which is slower and a second place for "which clip did you mean" to go
    wrong.
    """

    @abstractmethod
    def do(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...

    def merge_with(self, other: Command) -> bool:
        """Absorb `other` into this command. False when they cannot merge.

        Called only inside a gesture, and only against a command already
        applied — so an implementation absorbs the *later* target value while
        keeping its own original, which is what makes undoing a fifty-step
        drag return to where the drag started.
        """
        return False


class InvalidEdit(Exception):
    """An edit was refused because it would have left the project invalid."""

    def __init__(self, problems: Sequence[Problem]):
        super().__init__("; ".join(str(problem) for problem in problems))
        self.problems = list(problems)


class Compound(Command):
    """Several edits that are one entry on the stack.

    D-23 is the motivating case: dropping a clip onto an occupied span also
    trims the clip already there, and one `Ctrl+Z` has to put both back.
    """

    def __init__(self, members: Sequence[Command], label: str = "") -> None:
        self.members = list(members)
        self.label = label

    def do(self) -> None:
        applied: list[Command] = []
        try:
            for member in self.members:
                member.do()
                applied.append(member)
        except Exception:
            # A half-applied compound is worse than a refused one: the project
            # is left in a state no single undo can reach.
            for member in reversed(applied):
                member.undo()
            raise

    def undo(self) -> None:
        for member in reversed(self.members):
            member.undo()


class UndoStack:
    """Runs commands, remembers them, and knows whether anything is unsaved."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self._done: list[Command] = []
        self._undone: list[Command] = []
        #: Where in `_done` the project was last written. `None` means the
        #: save point was discarded with a redo branch and can never be
        #: reached again, so the project is permanently unsaved.
        self._saved_at: int | None = 0
        self._depth = 0
        self._gesture_start = 0

    # ------------------------------------------------------------- running

    def push(self, command: Command) -> None:
        """Apply `command`, keep it, and discard any redo branch.

        Applies first and rolls back if the result is invalid, rather than
        predicting whether it would be. Predicting means every command
        re-deriving the rules it might break, which is the duplication
        model.validate() exists to prevent. Nothing observes the intermediate
        state — the audio thread reads a snapshot, not the model.
        """
        command.do()
        problems = validate(self.project)
        if problems:
            command.undo()
            raise InvalidEdit(problems)

        if self._saved_at is not None and self._saved_at > len(self._done):
            # The save point lives in the branch this edit is about to throw
            # away. Claiming "saved" afterwards would be a lie that loses work.
            self._saved_at = None
        self._undone.clear()

        inside_gesture = self._depth and len(self._done) > self._gesture_start
        if inside_gesture and self._done[-1].merge_with(command):
            return
        self._done.append(command)

    def undo(self) -> bool:
        if not self._done:
            return False
        command = self._done.pop()
        command.undo()
        self._undone.append(command)
        return True

    def redo(self) -> bool:
        if not self._undone:
            return False
        command = self._undone.pop()
        command.do()
        self._done.append(command)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    def __len__(self) -> int:
        return len(self._done)

    # ------------------------------------------------------------ gestures

    @contextmanager
    def gesture(self) -> Iterator[None]:
        """Coalesce the commands pushed inside into one stack entry.

        Explicit rather than inferred. Merging any two consecutive compatible
        commands would silently weld together two separate things somebody did
        — nudge a clip, pause, nudge it again — into one undo step. A gesture
        already has a beginning and an end the UI knows about: mouse-down and
        mouse-up.
        """
        self._depth += 1
        if self._depth == 1:
            self._gesture_start = len(self._done)
        try:
            yield
        finally:
            self._depth -= 1

    # --------------------------------------------------------------- dirty

    def mark_saved(self) -> None:
        """Record that the project as it stands has been written to disk."""
        self._saved_at = len(self._done)

    @property
    def is_dirty(self) -> bool:
        """Whether the project differs from what was last written.

        Position, not depth: undoing one edit and doing a different one leaves
        the same number of commands on the stack and a different project.
        """
        return self._saved_at is None or self._saved_at != len(self._done)
