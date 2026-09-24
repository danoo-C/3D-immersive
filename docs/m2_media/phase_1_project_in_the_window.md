# M2 · Phase 1 — The project in the window

**Status:** in progress · **Plan:**
[plans/phase_1_project_in_the_window.md](plans/phase_1_project_in_the_window.md)

## Goal

The window holds a `Project`. File › New, Open, Save and Save As work through
M1's `.3dim` reader and writer, Edit › Undo and Redo drive M1's stack, and the
title says which project is open and whether it has unsaved changes. Opening a
project whose audio has gone opens it anyway and says so in the notice centre.

Nothing in this phase is new machinery. M1 built all of it headless, on
purpose, and no milestone was ever given the job of wiring it to the menus —
which is why five actions still say they arrive at M1. Every later phase in
this milestone edits a project the window has to be holding.

## Scope

**In:** the window owning one `Project` and one command stack; New, Open,
Save, Save As and their shortcuts; the file dialogs; Undo and Redo, enabled
only when there is something to undo or redo; the window title and its
unsaved-changes marker; the one confirmation the application is allowed —
discarding an unsaved project, on New, Open and Quit (*Accessibility and
feel* in [04](../04-ui-spec.md)); load problems — missing media first among
them — posted to the notice centre.

**Out:** importing audio → phase 6. The relink dialog → M8, before beta.
Recent projects and remembered window geometry → M8, after beta. Autosave and
crash recovery → M8 (F-49). Anything that draws the project's channels or
clips → M3, which is the first milestone with anything to draw them in.

## Acceptance

- [ ] New, Open, Save and Save As are enabled and do what they say. A project
      built in code, saved through the window and reopened through the window
      compares equal to the one that was saved.
- [ ] Undo and Redo are enabled exactly when the stack has something to undo
      or redo, and follow it after every edit, undo, redo, save and open.
- [ ] The title names the project — its file's stem, or a stated placeholder
      for one never saved — and marks unsaved changes. The marker clears on
      save and returns on the next edit.
- [ ] New, Open or Quit over unsaved changes asks once, and cancelling leaves
      the project and its undo history untouched. Nothing else in the phase is
      modal apart from the file dialogs themselves.
- [ ] Opening a project whose media has gone opens it, marks those files
      missing (D-72), and posts **one** `warn` notice whose detail lines name
      each missing file.
- [ ] A file that is not a readable project posts an `error` notice and leaves
      the project that was open exactly as it was.
- [ ] No action's tooltip names a milestone that is already complete, asserted
      by a test that reads the roadmap's status markers rather than a
      hand-kept list.

## Implements

F-1, F-3 (the report; the dialog is M8's), F-4, F-56, D-71, D-72. M1's
`core/io/project_io.py` and `core/commands.py` are the implementation; this
phase is their front door.

## Notes

Appended while building.
