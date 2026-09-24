# M2 · Phase 1 — The project in the window

**Status:** ✅ complete · **Plan:**
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

- [x] New, Open, Save and Save As are enabled and do what they say. A project
      built in code, saved through the window and reopened through the window
      compares equal to the one that was saved.
- [x] Undo and Redo are enabled exactly when the stack has something to undo
      or redo, and follow it after every edit, undo, redo, save and open.
- [x] The title names the project — its file's stem, or a stated placeholder
      for one never saved — and marks unsaved changes. The marker clears on
      save and returns on the next edit.
- [x] New, Open or Quit over unsaved changes asks once, and cancelling leaves
      the project and its undo history untouched. Nothing else in the phase is
      modal apart from the file dialogs themselves.
- [x] Opening a project whose media has gone opens it, marks those files
      missing (D-72), and posts **one** `warn` notice whose detail lines name
      each missing file.
- [x] A file that is not a readable project posts an `error` notice and leaves
      the project that was open exactly as it was.
- [x] No action's tooltip names a milestone that is already complete, asserted
      by a test that reads the roadmap's status markers rather than a
      hand-kept list.

## Implements

F-1, F-3 (the report; the dialog is M8's), F-4, F-56, D-71, D-72. M1's
`core/io/project_io.py` and `core/commands.py` are the implementation; this
phase is their front door.

## Notes

Appended while building.

**Four steps, in the planned order, and every File and Edit action that was
waiting on M1 now works.** The window holds a document; the document holds
the project, its stack and its file; and the window keeps no copy of any of
it, reading the document back after every change it is told about.

### D-85: the open project is a document in `core/`, not state on a window

Everything hard in this phase turned out to be logic: a failed open leaving
the open project, its history and its unsaved edits exactly as they were;
Save As changing where the next Save writes only once the write has worked; a
new project getting a new stack so Undo cannot edit a project nobody can
see. Eighteen tests settle those headless, in about a tenth of a second
between them. The window's own tests are about what the window adds —
dialogs, the prompt, the title, notices — and nothing else.

Observers are told **once** per change, not at least once. `save_as` first
told them twice — once for the write, once for the new name — which is
harmless for a title and would be a doubled engine snapshot at M3.

### ⚠️ Every window the suite ever built was still alive at the end of it

`deleteLater()` deletes only when the event loop next turns, and nothing in a
test turns it. So no window was ever freed — and building a window applies
the theme, which re-polishes every widget in every window still alive. Each
window cost more than the one before: building one took four seconds late in
a run. A probe released eight windows in a row and found all eight alive.

The suite had been paying for this without it looking like one problem:
559 tests in three seconds on 23 September, a minute by the end of M9, and
three minutes once this phase added twenty window tests. An autouse fixture now releases
every parentless top-level widget after each test and delivers the posted
deletions by hand. **832 tests in eight seconds.** The practical consequence
is that a mutation sweep can run the whole suite per mutation, which this
phase's did.

### A modal dialog in an offscreen test hangs the suite with no failure

Offscreen, nobody can click, so a real `exec()` waits forever. Every place
the window waits for a person is now a method a test replaces, and
`conftest.py` turns any test that reaches a real dialog into a failure
naming the problem. The guard reaches only what goes through Python — a
dialog's `exec()`, `QFileDialog`'s static choosers — and **not
`QMessageBox.question`**, which runs its loop in C++. That was found by a
probe that hung while the guard was being written, so the prompt builds a
box and calls `exec()`. The guard caught two of this phase's own tests on
their first run, both of which had forgotten that a dirty project asks
before it opens another.

### Two reasons a control can be disabled

`04`'s Craft rule was that a disabled control says why, and until now the
only reason was that it had not been built. Undo with nothing to undo is
disabled for a different reason, so it says *Nothing to undo.* — and the
shell's test now asserts that a disabled action has *a* reason on the line
after its name, rather than the one reason there used to be.

### The check that would have caught this phase's reason for existing

A test reads `06`'s ✅ markers and fails on any tooltip promising something at
a milestone already marked complete. It walks every action and every widget,
and it has two companions: one fails if the roadmap's headings change shape
and the markers stop being found, and one hands the checker the tooltip Save
carried until this phase and asserts it is caught. When M2 is marked
complete, this is what forces the media pool's tooltip to go with it.

### Two things learned about M1's file on the way past

`{"schema_version": 1}` on its own opens as an empty project, because every
key the schema knows has a default. That is consistent with D-73 and was
written into a test as a file that would not open before anyone checked.
And a Save As aimed at a directory to make it fail succeeded — the directory
had no suffix, so it got `.3dim`, which is the rule the next test asserts.

### What the mutation sweep found

Fifteen mutations named in the plan and three added once the code existed —
`push` not telling observers, the title losing Qt's `[*]`, and an enabled
Undo keeping its *nothing to undo* reason. **None survived**, each killed by
the whole suite rather than by a chosen file.
