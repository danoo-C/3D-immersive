# M1 · Phase 4 — Undo stack

**Status:** not started · **Plan:** not written yet

## Goal

`core/commands.py` holds a `Command` with `do()` and `undo()` and a stack that
manages them; `core/edits.py` holds the first concrete ones. After this phase
**nothing mutates the model except a command** — which is the whole reason
D-14 made this day-one work rather than a later feature. Retrofitting undo
means rewriting every editing path, so there is never a good moment to add it
except before there are any.

## Scope

**In:** the `Command` protocol; the undo/redo stack with unlimited depth within
a session (F-4); coalescing a continuous gesture into one command; a first set
of concrete edits covering each shape of mutation — add/remove from a list,
change a field, and a compound edit that must undo as one.

**Out:** clipboard operations (F-50, D-58) → M3. Selection (D-57) → M3;
commands here take explicit targets rather than "whatever is selected". A UI
undo history → never planned. Persisting the stack across a restart — F-4 says
"within a session" and that is deliberate.

## Acceptance

- [ ] Every concrete edit round-trips: `do()` then `undo()` leaves a project
      equal to the one before, by the equality
      [phase 1](phase_1_dataclasses.md) established. Checked for each edit, not
      for a representative one.
- [ ] Redo after undo restores exactly the `do()` result, and a **new edit
      after an undo discards the redo branch** — the standard behaviour, stated
      because the alternative (a redo tree) is a defensible design that this
      is deliberately not.
- [ ] A compound edit undoes as one step, not several. The motivating case is
      D-23's magnetic drop, where placing a clip also trims its neighbour:
      one `Ctrl+Z` must put both back.
- [ ] **Continuous gestures coalesce into one command**
      ([02](../02-architecture.md), *Undo*). Dragging a clip through fifty
      intermediate positions leaves one entry on the stack, whose `undo()`
      returns to where the drag started rather than to the forty-ninth
      position.
- [ ] An edit that would break a [phase 1](phase_1_dataclasses.md) invariant —
      overlapping clips, `offset + length` past the end of the media — is
      refused before it mutates anything, and refusing leaves the stack
      untouched. A half-applied command is worse than a rejected one.
- [ ] Unlimited depth within a session (F-4): a thousand edits undo back to the
      empty project. Memory is not a stated constraint and is not pretended to
      be one here, but the test says what "unlimited" was taken to mean.
- [ ] The stack knows whether the project is **dirty** — unchanged since the
      last save point — because [phase 5](phase_5_project_io.md) and the
      "discard an unsaved project" confirmation in
      [04](../04-ui-spec.md) both need it, and the stack is the only thing that
      can answer honestly.

## Implements

F-4. D-14, and the *Undo* section of
[02-architecture.md](../02-architecture.md), which owns the coalescing rule.
D-23 supplies the compound-edit case.

## Notes

Appended while building.
