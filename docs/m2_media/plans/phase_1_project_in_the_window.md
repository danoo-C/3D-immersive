# Plan — M2 · Phase 1 — The project in the window

**Written:** 2026-09-24 · **Status:** ✅ complete

## Approach

M1 left three headless pieces — `Project`, `UndoStack`, and `project_io`'s
`save` and `load` — and nothing that holds them together as *the project
that is open*. Which file it came from, whether it has been saved since, what
a failed open must leave alone: those are one object's job, and today they
are nobody's.

**That object is a Qt-free `core/document.py`, not state on `MainWindow`.**
The alternative is shorter today and costs twice later. Everything this phase
has to get right — a failed open leaving the open project exactly as it was,
Save As changing where the next Save writes, the stack resetting on open so
Undo cannot reach into the previous project — is logic, not presentation, and
N-5 says `core/` is testable with no Qt. Tested through a window, each of those
costs a `MainWindow` at about two seconds apiece. And phase 6's import pushes
commands from a worker's result, and M3's engine has to be told when the
project changes: both need an owner of the open project that is not a widget.

The window becomes the document's front door: dialogs, the one confirmation,
the title, and turning the document's problems into notices.

## Three things the phase doc does not settle

### How the window learns the document changed

Plain callbacks, as the notice log does (D-81's reasoning, one module over):
`Document.observe(callback)`, called after every push, undo, redo, save, open
and new. The rule that makes it sufficient is that **edits go through the
document**, never straight to its stack — a push that bypassed it would leave
Undo greyed out after an edit, which the tests look for.

### The title, and where "unsaved" shows

`Untitled[*] — 3d immersive`, or the file's stem in place of *Untitled*, using
Qt's `[*]` placeholder and `setWindowModified`. Qt then marks unsaved changes
the way each platform does — an asterisk on Windows and Linux, a dot in the
close button on macOS — which is better than one glyph imposed on all three.

### The confirmation

Save, Discard or Cancel, asked on New, Open and Quit when the document is
dirty, and never when it is clean. **Save** saves — through Save As if the
project has never been saved — and goes ahead only if that actually worked: a
cancelled Save As dialog or a failed write must not be followed by throwing the
project away. This is the one confirmation `04` allows, and it gets written
into `04` beside the rule that allows it.

## Steps

1. **The document, headless.** `core/document.py`: a `Document` holding the
   project, its stack and its path; `new`, `open`, `save`, `save_as`, `push`,
   `undo`, `redo`; `title` and `is_dirty`; observers. `open` builds the new
   project and stack completely before replacing anything, and returns the
   load's survivable problems. A decision row for the document, and `02`
   gains the module.
   *Test:* a new document is clean and untitled; an edit dirties it and a save
   cleans it; `save_as` changes where the next `save` writes; a failed open —
   malformed, unreadable — raises and leaves project, stack, path and dirtiness
   exactly as they were; after an open, Undo cannot reach the previous project;
   missing media comes back as problems; observers fire once per change;
   **`core/document.py` imports no Qt**.

2. **Undo, Redo and the title.** One `QAction` each for Undo and Redo, shared
   by the menu and the toolbar so they cannot disagree. Enabled from the
   document, and when disabled for want of anything to undo their tooltip
   says so — `04`'s rule is that a disabled control explains itself, and
   "nothing to undo" is an explanation. The title and its `[*]`.
   *Test:* both actions follow push, undo, redo, save and open; the toolbar's
   action is the menu's; the title names the project and the modified flag
   follows the document.

3. **New, Open, Save, Save As.** File dialogs behind two small methods a test
   replaces; `.3dim` appended when a Save As name has no suffix; the
   Save/Discard/Cancel prompt on New and Open, and on Quit through
   `closeEvent`; a failed open posts an `error` notice carrying the load's
   problems and changes nothing; missing media posts **one** `warn` notice with
   a line per file. Success is quiet: the title's marker clearing is the
   feedback, and a notice on every `Ctrl+S` is the kind people learn to stop
   reading. The status bar's standing "No project" goes, because there is now
   always one.
   *Test:* every branch of the prompt, including Save whose dialog is
   cancelled; open failures of both kinds; missing media as one notice;
   quitting clean is not asked, quitting dirty is, and Cancel keeps the window.

4. **The tooltips stop lying.** `_M1` is deleted with the actions it
   described. A test reads `06`'s status markers and fails if any tooltip
   says something arrives at a milestone already marked complete — the check
   that would have caught this phase's reason for existing.
   *Test:* that test, and that it fails against a tooltip naming M1.

## Files

```
docs/01-requirements.md                    amended — a decision row for the document
docs/doc-system.md                         amended — the D high-water mark
docs/02-architecture.md                    amended — core/document.py
docs/04-ui-spec.md                         amended — the confirmation's three
                                             choices, and the title
docs/m2_media/phase_1_*.md                 amended — Notes
src/immersive/core/document.py             new
src/immersive/ui/main_window.py            amended — the document, dialogs,
                                             prompt, title, Undo/Redo
tests/test_document.py                     new — headless
tests/test_project_in_the_window.py        new — gui
tests/test_main_window.py                  amended — disabled actions now
                                             explain themselves either way
tests/test_layering.py                     amended if core/document.py is not
                                             already covered by the core walk
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A modal dialog in a test blocks forever offscreen | a hung suite with no failure message | every dialog is reached through a method the tests replace; a test asserts no `QMessageBox` or `QFileDialog` is constructed during the suite's own flows |
| An edit pushed straight to the stack, bypassing the document | Undo stays greyed after an edit, the title stays clean, and a Quit loses work without asking | the stack is not exposed for pushing; the window reads the document's state after every observer call rather than tracking its own |
| `closeEvent` behaving differently under test | Quit tested through a path real quitting does not take | drive it through `window.close()`, which is what the Quit action calls |
| Relative media paths after Save As to another directory | a project that opens with every sample missing | D-71 already makes paths absolute in memory and relative on write; asserted end to end by saving to a second directory and reopening |

**Mutations named in advance**, run against the finished suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `open` replaces the project before the load has succeeded | a malformed file wipes the open project |
| `open` keeps the old stack | Undo after an open edits a project that is no longer open |
| `save` does not call `mark_saved` | the title stays dirty after every save, and Quit always asks |
| `save_as` does not update the path | the next Save writes the old file |
| observers not called after `undo` | Undo stays enabled with nothing left to undo |
| the toolbar's Undo a separate action | the menu and the toolbar disagree |
| the prompt skipped when dirty | New throws away work without asking |
| the prompt shown when clean | the application nags |
| Cancel in the prompt goes ahead anyway | the prompt is decoration |
| Save chosen in the prompt, Save As then cancelled, and it goes ahead | the project is discarded after the user asked to keep it |
| `closeEvent` accepts after Cancel | Quit loses work |
| missing media posted once per file | one open raises the count by every sample that moved |
| missing media not posted | F-3's report half, gone |
| a failed open posted as `warn` | "the project did not open" reads as a caveat |
| `.3dim` not appended to a bare Save As name | a project saved as `mix` that the Open dialog's filter then hides |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Importing audio | phase 6 |
| The relink dialog | M8, before beta (D-84) |
| Recent projects, remembered window geometry | M8, after beta |
| Autosave and the recovery offer | M8 (F-49) |
| Showing channels and clips | M3 |
| Naming the command in Undo's text ("Undo Move Clip") | nothing has a user-facing command name yet; M3 is the first milestone with commands a user issues one at a time |

## Outcome

Four steps in the planned order, all seven acceptance boxes ticked, eighteen
mutations and no survivor. 832 tests, and the suite takes eight seconds
rather than three minutes.

### What the plan got right

**Putting the document in `core/`.** Every rule the phase exists for is
asserted headless, and the window's tests are about the window. It also
made the mutation sweep sharp: half the mutations are in `document.py` and
each was killed by a test that names the rule it broke.

**The Save-that-did-not-save case.** Named in the Approach, in a risk row
and as a mutation before any code existed, and it is the one branch of the
prompt a quick implementation gets wrong.

**Dialogs behind replaceable methods.** A risk row said a modal dialog would
hang the suite. It would have, and it would have done it silently.

### What the plan did not see

**That the suite had been leaking every window it built.** Nothing in the
plan's risk table is about test speed, because nothing suggested it was a
problem rather than the cost of a GUI. It was a leak, and the leak was
quadratic: fixing it took the suite from 185 seconds to 8.

**That the guard has a hole.** The risk row assumed every modal dialog could
be intercepted; `QMessageBox.question` cannot. Found by a probe hanging, and
recorded in the guard's docstring so the next dialog does not use it.

**That the disabled-control rule had a second case.** The plan said Undo's
tooltip would explain itself; it did not see that the shell's existing test
encoded "disabled means not built", and would have to be taught otherwise.

### Deviations

| Planned | Actual |
|---|---|
| `test_layering.py` amended if `document.py` was not covered | not needed — the core walk uses `rglob`, so every new module is covered on arrival |
| Nothing about `project_io` | gained `SUFFIX`, beside `theme_io.SUFFIX`, because the format's suffix belongs to the format |
| Nothing about the suite's speed | an autouse fixture that frees every window after each test, in its own commit |

### What phase 2 needs to know

**Edits go through `window.document()`**, never to a stack directly — phase
6's import pushes its command there. **A dialog is a method a test
replaces**, and never `QMessageBox.question`. `open_project(path)` takes a
path for callers that already have one, which M8's recent projects will be.
And the suite is fast enough to run whole for every mutation, so there is no
longer a reason to choose target files.
