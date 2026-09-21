# M1 · Phase 4 — Undo stack

**Status:** ✅ complete · **Plan:**
[plans/phase_4_undo_stack.md](plans/phase_4_undo_stack.md)

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

- [x] Every concrete edit round-trips: `do()` then `undo()` leaves a project
      equal to the one before, by the equality
      [phase 1](phase_1_dataclasses.md) established. Checked for each edit, not
      for a representative one.
- [x] Redo after undo restores exactly the `do()` result, and a **new edit
      after an undo discards the redo branch** — the standard behaviour, stated
      because the alternative (a redo tree) is a defensible design that this
      is deliberately not.
- [x] A compound edit undoes as one step, not several. The motivating case is
      D-23's magnetic drop, where placing a clip also trims its neighbour:
      one `Ctrl+Z` must put both back.
- [x] **Continuous gestures coalesce into one command**
      ([02](../02-architecture.md), *Undo*). Dragging a clip through fifty
      intermediate positions leaves one entry on the stack, whose `undo()`
      returns to where the drag started rather than to the forty-ninth
      position.
- [x] An edit that would break a [phase 1](phase_1_dataclasses.md) invariant —
      overlapping clips, `offset + length` past the end of the media — is
      refused, and refusing leaves **the project and the stack unchanged**. A
      half-applied command is worse than a rejected one.
- [x] Unlimited depth within a session (F-4): a thousand edits undo back to the
      empty project. Memory is not a stated constraint and is not pretended to
      be one here, but the test says what "unlimited" was taken to mean.
- [x] The stack knows whether the project is **dirty** — unchanged since the
      last save point — because [phase 5](phase_5_project_io.md) and the
      "discard an unsaved project" confirmation in
      [04](../04-ui-spec.md) both need it, and the stack is the only thing that
      can answer honestly.

> **Amended before building.** This line said "refused before it mutates
> anything", which taken literally means predicting whether a command would
> break an invariant without running it — forcing every command to re-derive
> the rules it might violate, which is the duplication
> [phase 1](phase_1_dataclasses.md)'s central `validate()` exists to prevent.
> The implementation applies, validates, and rolls back on failure. The
> property that matters is unchanged and is what the line now states; nothing
> observes the intermediate state, because the audio thread reads a snapshot
> rather than the model ([02](../02-architecture.md)). Reasoning in
> [the plan](plans/phase_4_undo_stack.md).

## Implements

F-4. D-14, and the *Undo* section of
[02-architecture.md](../02-architecture.md), which owns the coalescing rule.
D-23 supplies the compound-edit case.

## Notes

**Done. Every acceptance line passes**, one of them after being amended before
any code was written — see the note above *Implements*.

### Apply, validate, roll back

The amended line is the centre of this phase. Refusing an edit *before*
applying it would force every command to re-derive the rules it might break,
which is the duplication [phase 1](phase_1_dataclasses.md)'s central
`validate()` exists to prevent. `UndoStack.push` instead runs the command,
validates the whole project, and calls `undo()` if anything is wrong — so a
refused edit leaves the project, the stack and the redo branch exactly as they
were, which is testable and is the property the line was actually asking for.

The price is a full `validate()` per push. Measured in the plan: 0.08 ms at
the 100-clip project N-4 names, 1.01 ms at 1 600 clips, and 12.6 ms — three
quarters of a 60 fps frame — at 20 000. The mitigation if M3 ever needs it is
scoping `validate()` to the channel an edit touched, **not** a flag that skips
checking: a flag that can be turned off is a flag that will be off.

### Seven edits, chosen by shape

| Command | Shape |
|---|---|
| `AddChannel` / `RemoveChannel` | insert into and remove from an ordered list |
| `AddClip` / `RemoveClip` | the same, where the position is *derived* from the sort order rather than passed in |
| `SetAttribute` | one field on one dataclass, checked against `dataclasses.fields` at construction |
| `MoveClip` | a field that merges with itself during a drag |
| `Compound` | several edits that undo as one, in reverse |

`AddClip`/`RemoveClip` are two more than the plan's table listed. They are the
same shape as the channel pair, and they were written because D-23's magnetic
drop — the compound edit's motivating case — is about clips, and testing it
with channels would have tested an analogy instead of the case.

**Lists are searched by identity, never by value.** `list.index` compares by
value and phase 1's dataclasses compare by value, so two channels a user has
not yet told apart are the same channel to `index()`. Removing one would
remove the other, indistinguishably, until undo put it back in the wrong
place.

### The mutations were named in the plan before the tests existed

Phase 3's practice, repeated. All five named mutations are caught on the first
pass, as are two extra ones added afterwards to stress the suite further:

| mutation | caught by |
|---|---|
| merge keeps the *latest* before-value instead of the original | `test_a_drag_inside_a_gesture_is_one_entry_ending_where_it_started` |
| the redo branch survives a new edit | `test_a_new_edit_discards_the_redo_branch` |
| `Compound.undo` runs forward instead of reversed | `test_a_compound_undoes_in_reverse_even_when_the_project_cannot_show_it` |
| rollback leaves the stack grown | `test_an_edit_that_would_break_an_invariant_is_refused` |
| `mark_saved` compares by depth, with no orphan check | `test_an_orphaned_save_point_is_dirty_for_ever` |
| extra: `_index_of` searches by value | `test_removing_a_channel_picks_by_identity_not_by_equality` |
| extra: `AddClip` inserts before an equal start rather than after | **nothing — see below** |

⚠️ **One mutation survives, and it is unreachable rather than untested.** A
clip must have positive length and may not begin before its predecessor ends,
so two clips on one channel can never share a start in a project `validate()`
accepts — which means `bisect_left` and `bisect_right` agree on every input
that can occur. `test_two_clips_can_never_share_a_start_on_one_channel` records
the reasoning rather than papering over it with a test that would only be
asserting the mutation. This is the same category as
[phase 2](phase_2_curve_evaluation.md)'s bisection bracket.

### Two things a later reader will trip over

**Commands capture their indices at construction, not at `do()`.** That is the
point of holding targets rather than looking them up by id, and it is also the
sharp edge: building a `Compound` whose later members depend on what earlier
members did means the indices were computed against the *old* list. It is
correct for everything here, and M3 should build compounds in the order they
apply rather than assembling them out of order.

**`is_dirty`, `can_undo` and `can_redo` are read through functions in the
tests.** mypy narrows a property to a literal at the first assertion and then
declares the opposite assertion — and everything after it — unreachable, which
is precisely wrong for flags whose whole job is to change on the next line.
Three one-line helpers at the top of `tests/test_commands.py`, with the reason
attached.

### Inherited by M3

| | |
|---|---|
| `UndoStack(project)` | `push`, `undo`, `redo`, `can_undo`, `can_redo`, `len()` |
| `stack.gesture()` | a context manager; merging happens only inside one, and nothing merges across a boundary or reaches back past its start. Nesting is safe |
| `InvalidEdit` | carries every `Problem`, not just the first, because a dialogue that reports one at a time is five dialogues |
| `mark_saved()` / `is_dirty` | what [phase 5](phase_5_project_io.md) and 04's "discard an unsaved project" confirmation both need |
| `Command` | subclass and implement `do`/`undo`; `merge_with` returns `False` unless a command opts in, so a new M3 edit cannot start coalescing by accident |

Unlimited depth is asserted at a thousand edits, which undo back to a project
equal to the one before them. Nothing trims the stack behind your back.
