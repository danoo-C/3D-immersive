# M1 · Phase 1 — Dataclasses

**Status:** ✅ complete · **Plan:**
[plans/phase_1_dataclasses.md](plans/phase_1_dataclasses.md)

## Goal

Every entity in the Entities block of
[03-data-model.md](../03-data-model.md) exists as a plain Python dataclass in
`core/model.py` and `core/curves.py`, with the invariants from that document's
*Rules* section enforced where enforcing them is cheap and checked by test
where it is not. A project can be constructed in code and interrogated; nothing
can evaluate, convert or persist it yet.

This is the phase that makes the M0 import-graph test stop passing vacuously.

## Scope

**In:** `Project`, `Channel`, `Clip`, `MediaFile`, `Curve`, `Keyframe`, and the
small value types beside them (`SnapSetting`, `HrtfRef`, the distance and
master settings, fades). Curve and Keyframe as *containers* only. Derived
length (D-53). The solo rule (D-62). Channel order as list order, with no
stored `index` (D-61). The clip invariants: never overlapping on a channel,
`offset + length` within `MediaFile.frames`.

**Out:** curve *evaluation* → [phase 2](phase_2_curve_evaluation.md). Time
conversion and snapping → [phase 3](phase_3_time_and_snapping.md). Any mutation
that is not a `Command` → [phase 4](phase_4_undo_stack.md); until then the
model is built by construction, not by editing. Serialisation →
[phase 5](phase_5_project_io.md). Opening an audio file — ever, in this
milestone: `MediaFile` holds metadata, and M2 decodes.

## Acceptance

- [x] Every entity and field in [03](../03-data-model.md)'s Entities block
      exists, with the same names, and a test walks that list rather than
      trusting a reading of it.
- [x] `Project.length` is **derived** from the last clip end and is not a
      stored field (D-53). Zero for an empty project; automation past the last
      clip does not extend it.
- [x] There is no `Channel.index` anywhere, asserted (D-61). Reordering is a
      list operation and nothing else has to be kept in step.
- [x] Solo is additive, non-soloed channels are silent while any solo is on,
      and an explicit mute still wins on its own channel (D-62). Expressed as a
      pure function over the channel list, so M3 and M4 share one answer.
- [x] Clips on one channel never overlap and `offset + length` never exceeds
      `MediaFile.frames` — checked by a validator that returns *what* is wrong,
      not just that something is. Phase 5 needs the reasons to report them.
- [x] `hrtf_bypass` is a plain bool, `pan` exists alongside the `pos.*` curves,
      and toggling bypass in either direction destroys no automation (F-42).
      A dataclass cannot get this wrong, but a test says so before anything
      later can.
- [x] Two projects built identically compare equal, and comparison ignores
      nothing that matters — the milestone's own acceptance ends in "compared
      equal", so the comparison is load-bearing rather than incidental.
- [x] `tests/test_layering.py` still passes with `core/` no longer empty, and
      its vacuity guard still passes too.

## Implements

The Entities and Rules sections of [03-data-model.md](../03-data-model.md).
F-10, F-12, F-42. D-6, D-11, D-53, D-61, D-62, and the bypass family D-32
through D-35. The module layout and the empty-`__init__` rule are D-29 and the
*Repository layout* section of [02-architecture.md](../02-architecture.md).

## Notes

**Done. Every acceptance line passes**, and the phase found one thing wrong
with the specification before it wrote a line of the model.

⚠️ **`03` contradicted itself about ids, and nothing in it was
implementable.** The Entities block said `MediaFile.id` was a uuid; the JSON
example used `m-3f2a`, `c-01`, `k-01` — which turned out not to be a scheme at
all but mnemonics written by hand, the clip on *Kick* being `k-01` and the one
on *Backing mix* `b-01`. `Clip.id` and `Channel.id` had no type given.

Settled as **`<kind>-<8 hex digits>`**, unique across the whole project rather
than within a kind, minted by checking against what the project already holds
and regenerating on a clash. Short because a `.3dim` is meant to be diffable
and hand-editable (D-13, F-2) and 36 characters in every clip works against
both; eight digits are safe *because* of the retry — a bare 32-bit space has
roughly a 1% birthday collision at ten thousand clips, which is too close to
rely on. `03` now has an *Ids* section and its example uses real ones.

**Keyframes deliberately have no id.** They are identified by `t`, which is why
`t` must be unique, and the consequence belongs to M6: dragging a keyframe onto
another's time is a collision, not a reordering.

**The documentation-walking test earned its place.** `test_model.py` parses
`03`'s Entities block and asserts each dataclass has exactly the fields listed
there, in order. It is what caught the id problem, and it is what stops the
document and the model drifting from here on. It cost one change to `03`:
`Channel` listed `id, name` and `gain_db, mute, solo` on single lines, which
are now one field per line — a diagram that is also machine-readable, at no
cost to reading it.

The plan flagged this test as a brittleness risk and named its fallback (an
explicit list in the test file). Not needed: matching only `├── <name>` and
ignoring everything after it is forgiving enough to survive a reflow.

**Equality is tested by breaking it seventeen times.** The milestone's own
acceptance ends in "compared equal" and
[phase 5](phase_5_project_io.md) leans on it entirely, so testing equality once
and trusting it is exactly how a round trip silently loses a field. Every field
that carries data — including nested ones, list order, and a keyframe's bezier
handles — is changed in turn and asserted to break equality.

**`tests/test_layering.py` stops passing vacuously here.** It has carried its
own guard against that since M0 because `core/` was empty. Confirmed by
injecting `from PySide6.QtGui import QColor` into `model.py` and watching it
fail with *"core/ must stay pure (N-5)"*, then removing it.

**Inherited by the rest of M1:**

| | |
|---|---|
| ids | `m-`/`c-`/`k-` + 8 hex, `mint_id` takes an optional `Random` so tests are deterministic |
| `validate()` | returns `list[Problem]`, each with a `where` like `channels[0].clips[1]` and a message naming the offender |
| `audible()` | the solo rule as a function over the channel list, so M3 and M4 share one answer |
| `Interpolatable` | the automation key vocabulary, so M4 and M6 cannot typo `"pos.x"` |
| `Handles` | `outgoing` / `incoming`, because `in` is a keyword — phase 5 maps them back to `in`/`out` |

One thing phase 5 will need and does not have: `MediaFile` has no `missing`
flag. F-3 wants a load to mark media it could not find, but that is *session*
state rather than project data — it depends on the machine, not the file — so
it does not belong in the Entities block as it stands. Phase 5 adds it and
amends `03`, rather than this phase guessing at the shape.
