# Plan — M1 · Phase 4 — Undo stack

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

A `Command` protocol with `do()` and `undo()`, concrete edits in
`core/edits.py`, and an `UndoStack` that is the only thing allowed to run
them. After this phase nothing mutates the model except through it, which is
what D-14 made day-one work: retrofitting undo means rewriting every editing
path, and there is never a better moment than before there are any.

**Inverse operations, not snapshots.** Each command captures what it needs to
reverse itself at `do()` time — the old value of a field, the index a channel
was removed from. That is why [phase 1](../phase_1_dataclasses.md) chose
mutable dataclasses; storing a copy of the project per edit would make F-4's
"unlimited depth" a memory leak with a nice name.

**Commands hold their targets.** A command is constructed against the objects
it edits and then has no arguments. The alternative — passing the project into
`do()` — reads tidier and forces every command to re-find its target by id on
each call, which is both slower and a second place for "which clip did you
mean" to go wrong.

## The edits, chosen to cover the shapes rather than the surface

M3 will need dozens; this phase wants one of each *kind* of mutation, because
those are what the stack has to handle correctly.

| Command | Shape it covers |
|---|---|
| `AddChannel` / `RemoveChannel` | insert into and remove from an ordered list |
| `SetAttribute` | change one field on one object |
| `MoveClip` | change a field, and **merge** with itself during a drag |
| `Compound` | several edits that must undo as one |

`SetAttribute(target, name, value)` is deliberately generic and deliberately
the only stringly-typed thing here. The alternative is a class per field —
`RenameChannel`, `SetChannelGain`, `SetChannelMute` — which is twenty classes
that differ by one attribute name and give nothing back. It is checked at
construction against the target's real fields, so a typo fails where it is
written rather than at undo time.

## ⚠️ One acceptance line needs rewording

The phase doc says an invalid edit is "refused **before it mutates anything**".
Taken literally that means predicting whether a command would break an
invariant without running it — which forces every command to re-derive the
rules it might violate, and that duplication is exactly what
[phase 1](../phase_1_dataclasses.md)'s central `validate()` exists to prevent.

The plan is **apply, validate, and roll back on failure**. The property that
matters is preserved exactly: a refused edit leaves the project and the stack
unchanged, which is testable. Nothing observes the intermediate state — the
audio thread reads a snapshot rather than the model
([02](../../02-architecture.md), *Crossing from UI to audio*), so there is no
reader to see it.

Proposed wording: *"is refused, and refusing leaves the project and the stack
unchanged."* Amending explicitly, per [09](../../09-workflow.md).

## ⚠️ Validating every push has a cliff, and it is worth knowing where

`validate()` walks the whole project. Measured:

| clips | `validate()` | share of a 60 fps frame |
|---|---|---|
| 80 | 0.08 ms | 0.5% |
| 400 | 0.28 ms | 1.7% |
| 1 600 | 1.01 ms | 6.1% |
| 6 400 | 3.91 ms | 23.5% |
| 20 000 | 12.59 ms | **75.6%** |

At the scale the specification actually names — N-4 talks about a 100-clip
project — this is 0.08 ms and not worth a thought. A drag pushing sixty
commands a second at 1 600 clips spends 6% of each frame checking itself,
which is a fair price for catching a buggy command before it corrupts
someone's project.

At 20 000 clips it is not affordable, and the honest thing is to say where the
line is rather than discover it in M3. **The mitigation, if M3 ever needs it,
is scoping**: a clip move can only break invariants on its own channel, so
`validate()` gains an optional subset rather than the stack gaining a way to
skip checking. Not built now — a flag that can be turned off is a flag that
will be off, and there is no evidence yet that it is needed.

## Coalescing

`stack.gesture()` as a context manager. Inside it, a pushed command that can
merge with the one below it replaces it instead of stacking; outside it,
nothing merges.

Explicit rather than inferred. The tempting alternative is to merge any two
consecutive compatible commands, which silently welds together two separate
things a user did — nudge a clip, pause, nudge it again — into one undo step.
A gesture has a beginning and an end that the UI already knows about, because
they are mouse-down and mouse-up.

The merge keeps the **original** before-value and the **latest** after-value,
so undoing a fifty-step drag returns to where the drag started rather than to
its forty-ninth position.

## Steps

1. **The protocol and the stack.** `do`/`undo`; push, undo, redo; the redo
   branch discarded by a new edit.
   *Test:* a new edit after an undo discards the redo branch — the standard
   behaviour, asserted because a redo *tree* is a defensible alternative that
   this deliberately is not. Unlimited depth: a thousand edits undo back to
   the empty project.

2. **The concrete edits.** One per shape from the table above.
   *Test:* every one round-trips — `do()` then `undo()` leaves a project equal
   to the one before, by [phase 1](../phase_1_dataclasses.md)'s equality.
   Checked for each, not for a representative one. `SetAttribute` rejects an
   unknown field at construction.

3. **Compound.** Several edits, one stack entry, undone in reverse.
   *Test:* D-23's magnetic drop is the motivating case — placing a clip also
   trims its neighbour, and one `Ctrl+Z` must put both back. Asserted with a
   compound whose second member fails, which must leave the first undone too.

4. **Coalescing.** The gesture context manager and `merge_with`.
   *Test:* fifty `MoveClip`s inside one gesture leave one stack entry whose
   undo returns to the drag's start. The same fifty outside a gesture leave
   fifty. Two gestures never merge across their boundary.

5. **Validation and the dirty flag.** Apply-validate-rollback; `mark_saved()`
   and `is_dirty`.
   *Test:* an edit that would overlap two clips is refused, the project is
   unchanged, and the stack has not grown. Dirty is false after
   `mark_saved()`, true after an edit, false again after undoing back to the
   save point — and **true forever** after the save point is orphaned by a new
   edit on a different branch, because the stack can no longer prove the
   project matches what was written.

Five steps, inside the six [09](../../09-workflow.md) allows.

## Files

```
src/immersive/core/commands.py   new — Command, UndoStack, Compound
src/immersive/core/edits.py      new — the concrete edits
tests/test_commands.py           new
tests/test_edits.py              new
phase_4_undo_stack.md            amended — the refusal wording
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A test asserts a mechanism without distinguishing it | The phase 2 failure, again | Mutations named now, run against the finished suite: merge keeps the *latest* before-value instead of the original; redo branch survives a new edit; `Compound.undo` runs forward instead of reversed; rollback leaves the stack grown; `mark_saved` compares by length instead of position |
| A command that half-applies and then raises | The project is corrupt and undo cannot fix it, which is worse than refusing | `Compound` undoes its already-applied members on failure; step 3 asserts it with a deliberately failing second member |
| Merging welds two separate user actions together | An undo that reverses more than the user did — the most annoying possible undo bug | Merging happens only inside an explicit gesture, and step 4 asserts that two gestures do not merge across their boundary |
| The dirty flag lies after an orphaned save point | Someone loses work believing it was saved | Orphaned save point means permanently dirty, asserted. Claiming clean when unprovable is the only failure here that loses data |
| `SetAttribute` typos | A silent no-op, or an attribute invented on the object | Checked against `dataclasses.fields` at construction, so it fails at the call site |

The genuine unknown is **whether the audio thread needs anything from this at
all**. 02 says structural changes reach the engine as an atomic snapshot swap
rather than by the engine reading the model, so undo should be invisible to it
— a snapshot is rebuilt and swapped exactly as for any other edit. If that
turns out wrong, it is an M4 discovery about the snapshot boundary rather than
about this stack, and nothing here would need to change.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Cut, copy and paste (F-50, D-58) | M3 — the commands exist here, the clipboard does not |
| Selection (D-57) | M3; commands here take explicit targets, not "whatever is selected" |
| The full set of edits M3 needs | M3, built on these shapes |
| Persisting the stack across a restart | Nowhere — F-4 says "within a session", deliberately |
| A visible undo history | Not planned |
| Which snapshot the engine reads | M4 |

## Outcome

**Every acceptance line passes.** 75 tests across `test_commands.py` and
`test_edits.py`, 457 in the suite.

**The amendment was the right call and was cheap because it happened here.**
Apply-validate-rollback preserves the property the acceptance line was
actually asking for — a refused edit leaves the project, the stack *and* the
redo branch untouched — without every command re-deriving the rules it might
break. Catching it while planning cost a paragraph; catching it after writing
seven commands would have cost seven rewrites.

**Naming the mutations in advance worked again.** All five are caught on the
first pass, as are two extra ones added afterwards. The table is in
[the phase Notes](../phase_4_undo_stack.md). Two phases running now, and the
mechanism is the same as phase 3's: having a concrete failure in mind while
writing an assertion is what separates a test that mentions a behaviour from
one that distinguishes it.

⚠️ **One extra mutation survives and should not be "fixed".** `AddClip` using
`bisect_left` instead of `bisect_right` is undetectable, because two clips on
one channel can never share a start in a project `validate()` accepts. Pinned
by a test that asserts the *reason* rather than the behaviour, so a later
reader does not mistake it for a gap. Same category as
[phase 2](phase_2_curve_evaluation.md)'s bisection bracket — the second time
this milestone has found a mutation that is unreachable rather than untested,
which is worth knowing about as a category.

**What the plan got wrong.** Two things, both small.

It listed four commands and seven were written: `AddClip` and `RemoveClip`
were added because D-23's magnetic drop — the compound edit's whole motivating
case — is about clips, and demonstrating it with channels would have tested an
analogy rather than the case. The plan's "one of each *shape*" framing was
right; it just miscounted which shapes the acceptance criteria needed.

It said nothing about how lists find their targets. `list.index` compares by
value and phase 1's dataclasses compare by value, so removing one of two
equal-looking channels would remove the wrong one — invisibly, until undo put
it back in the wrong place. `_index_of` searches by identity. That was a
decision the plan should have made rather than discovered.

**The quantitative question it asked was worth asking.** `validate()` on every
push is 0.08 ms at the scale N-4 names and 12.6 ms at 20 000 clips. The number
is now written down with the mitigation that goes with it, instead of being
rediscovered as a stutter in M3.

**Inherited by M3:** `UndoStack`, `stack.gesture()`, `InvalidEdit`,
`mark_saved`/`is_dirty`, and the seven commands. Details in the phase Notes,
including the one sharp edge — commands capture their indices at construction,
so a compound must be assembled in the order it applies.
