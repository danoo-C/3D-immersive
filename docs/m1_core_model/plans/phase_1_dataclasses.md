# Plan — M1 · Phase 1 — Dataclasses

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

Plain mutable dataclasses, one module for the model and one for curves, with
the field names taken literally from the Entities block of
[03-data-model.md](../../03-data-model.md). No properties that hide storage, no
inheritance, no base class — the whole value of this layer is that reading it
and reading `03` are the same activity.

**Mutable, not frozen.** The command pattern mutates the model in place (D-14),
and a frozen dataclass would force every edit to rebuild a tree of objects, at
which point undo would be storing snapshots rather than inverse operations.
Immutability is a real property of the *engine snapshot* on the audio side
([02](../../02-architecture.md), *Crossing from UI to audio*), which is a
different object built from this one, and conflating the two would make
[phase 4](../phase_4_undo_stack.md) considerably worse.

**Invariants are validated, not enforced in `__post_init__`.** A constructor
that raises makes an invalid state unrepresentable, which sounds strictly
better and is not: a command mid-edit legitimately passes through states that
do not satisfy the whole rule set, and a raising constructor turns each of
those into a workaround. Instead `validate(project)` returns *every* problem it
finds, with enough detail to name the offending clip. That shape is what
[phase 5](../phase_5_project_io.md) needs to report a bad file, and what
[phase 4](../phase_4_undo_stack.md) needs to refuse an edit before applying it.

**Derived facts are functions, not fields.** `Project.length` (D-53) and the
solo rule (D-62) are computed from the channel list every time. They are cheap
at M1 sizes, and a cached copy is a second home for a fact that
[doc-system.md](../../doc-system.md) §2 says should have one.

## ⚠️ The spec is ambiguous about ids, and this phase has to settle it

`03`'s Entities block says `MediaFile.id` is a **uuid**. Its JSON example uses
`"m-3f2a"`, `"c-01"`, `"k-01"` — and those are not a scheme at all, they are
mnemonics written by hand for the example: the clip on the *Kick* channel is
`k-01` and the one on *Backing mix* is `b-01`. `Clip.id` and `Channel.id` are
given no type at all.

So there is no current answer, and two documents point in different
directions. The options:

| | |
|---|---|
| **Full `uuid4`** | Collision-free with no bookkeeping. 36 characters in every clip, which makes a `.3dim` noisy to read and to diff — against D-13, which chose JSON to be diffable, and against [phase 5](../phase_5_project_io.md)'s hand-edited fixture |
| **Short `<kind>-<hex>`** | Readable and diffable, matches the example's spirit. Needs uniqueness to be minted carefully and checked, because a hand-edited file can duplicate one |

**Recommendation: short ids, `m-`/`c-`/`k-` plus 8 hex digits**, minted with a
retry against the ids already in the project, and uniqueness asserted by the
validator. The retry is what makes 8 digits safe — a bare 32-bit space has a
birthday collision around 1% at ten thousand clips, which is too close, but
"generate, check, regenerate" has no such bound and costs nothing at these
sizes. The validator has to check uniqueness regardless, because a
hand-editable format means a human can introduce a duplicate that no minting
strategy would have.

Either way **`03` has to stop saying two things**, and that correction is part
of this phase rather than a tidy-up afterwards.

**Keyframes get no id** — `03` identifies them by `t` within their curve and
requires `t` to be unique. That is a real constraint with a consequence M6
inherits: moving a keyframe onto another's time is a collision, not a
reordering. This phase states the rule; M6 decides what the UI does about it.

## Steps

1. **Value types and the curve containers.** `SnapSetting`, `HrtfRef`,
   `Distance`, `Master`, `Fade`, `Position`, then `Keyframe` and `Curve` in
   `core/curves.py` — shapes only, no evaluation.
   *Test:* every field in `03`'s listing for these types exists with that name;
   a `Curve` keeps its keyframes sorted by `t` with `t` unique, and says so
   when it does not.

2. **The entity spine.** `MediaFile`, `Clip`, `Channel`, `Project` in
   `core/model.py`. Field names literally as `03` lists them, with no
   `Channel.index` (D-61).
   *Test:* a table-driven check that walks `03`'s Entities block and asserts
   each entity has exactly the listed fields — so the documentation and the
   code cannot drift without a failure. Plus the absence of `index`, asserted
   rather than assumed.

3. **Ids.** The minting function, the prefixes, the collision retry, and the
   `03` correction that removes the contradiction above.
   *Test:* ten thousand ids minted into one project are unique; minting against
   a project that already contains the next candidate returns a different one;
   the format matches what `03` will now say.

4. **Derived facts.** `Project.length` (D-53), the audibility rule from solo
   and mute (D-62), and a named vocabulary for the `automation` keys so M4 and
   M6 cannot typo `"pos.x"`.
   *Test:* length is the last clip end across all channels, zero when empty,
   and unaffected by automation extending past it. Solo is additive; a muted
   soloed channel stays silent; bypassed channels obey solo like any other.

5. **The validator, and equality.** `validate(project)` returning every
   problem with its location. Then confirm equality does what
   [phase 5](../phase_5_project_io.md) will lean on.
   *Test:* each invariant has a project that breaks it and a message that names
   the offender — overlapping clips, `offset + length` past `MediaFile.frames`,
   a `media_id` with no media, a duplicate id, a curve with repeated `t`.
   Equality: two identically built projects compare equal, and changing any
   single field makes them unequal. `tests/test_layering.py` passes with
   `core/` populated, and its vacuity guard still passes.

Five steps, inside the six [09-workflow.md](../../09-workflow.md) allows.

## Files

```
src/immersive/core/model.py      new — the entity spine, ids, derived facts
src/immersive/core/curves.py     new — Keyframe and Curve as containers
tests/test_model.py              new
tests/test_curves.py             new
docs/03-data-model.md            amended — the id scheme, once it is decided
```

Nothing under `ui/`, nothing under `audio/`, no Qt, no `sounddevice` — which is
N-5, and which `tests/test_layering.py` has been waiting since M0 to check
against something.

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The id question is settled here badly and every later milestone inherits it | Ids appear in every command, every file, every reference | Raised above with a recommendation rather than decided in passing; `03` is corrected either way so the contradiction does not outlive this phase |
| Equality quietly ignores something | [Phase 5](../phase_5_project_io.md)'s round-trip passes while losing data, and the milestone's "compared equal" becomes meaningless | Step 5 changes each field in turn and asserts inequality, rather than testing equality once and trusting it |
| The documentation-walking test in step 2 is brittle against `03`'s formatting | A doc reflow breaks the build for no reason | Parse the fenced block by field name only, ignoring comments and alignment; if that proves fragile, fall back to an explicit list *in the test* with a comment pointing at `03` — a duplicated list that fails loudly beats a clever parser that fails confusingly |
| Float equality after a JSON round-trip | Phase 5 fails for reasons that look like a model bug | Python's `json` writes floats with `repr`, which round-trips float64 exactly. Asserted in phase 5 rather than assumed, and noted here because the obvious defensive move — comparing with a tolerance — would mask real data loss |
| `Project.length` recomputed per call becomes a hot path | Nothing at M1; possibly something at M3 | Leave it. A cache is a second home for a fact, and M3 will know whether it needs one |

The genuine unknown is **how much of `03`'s Rules section belongs in the
validator versus in the commands that would violate it**. Clips never
overlapping is an invariant of a *valid* project, but it is also something a
specific command (D-23's magnetic drop) actively maintains. This phase puts
every rule in the validator, on the grounds that phase 5 has to check a file
nobody's commands ever touched — and phase 4 can then reuse it rather than
re-deriving each rule at the point of edit.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Curve evaluation, interpolation, the bezier solve | [phase 2](../phase_2_curve_evaluation.md) |
| Bars:beats conversion, snapping | [phase 3](../phase_3_time_and_snapping.md) |
| Any mutation that is not construction | [phase 4](../phase_4_undo_stack.md) — this phase builds projects, it does not edit them |
| Reading or writing `.3dim` | [phase 5](../phase_5_project_io.md) |
| Opening, decoding or resampling audio | M2. `MediaFile` holds metadata and nothing here touches a sound file |
| Selection (D-57) | M3 |
| The implicit 32-sample edge fade (D-42) | M4's scheduler — it is applied at playback and deliberately not stored, which `03`'s Rules already say |

## Outcome

**Every acceptance line passes.** Full verdicts and the inherited interfaces
are in [the phase Notes](../phase_1_dataclasses.md).

**The id question was the right thing to raise.** It was settled as short
`<kind>-<8 hex>` with a minting retry, and `03` now has an *Ids* section
instead of a contradiction. Worth noting that the contradiction was not a
close call between two defensible schemes — the example's ids were not a
scheme at all, so there was nothing to implement until this phase decided.

**What the plan got right.** The documentation-walking test, which it proposed
with a named fallback in case it proved brittle. It did not, and it is what
found the id problem in the first place. And validating rather than raising in
`__post_init__`: `validate()` returning every problem with its location is
already the shape phases 4 and 5 want, and a raising constructor would have had
to be unpicked to get there.

**What it got wrong.** Nothing structural, but it under-specified two things
that turned out to need decisions of their own:

- **`Handles` uses `outgoing`/`incoming`, not `out`/`in`.** `in` is a Python
  keyword. The plan said field names come from `03` literally and did not
  notice that one of them cannot. `project_io` maps them back.
- **It did not anticipate `03` needing a formatting change.** `Channel` listed
  `id, name` and `gain_db, mute, solo` on single lines, which no
  field-per-line parser can read. Split, and the diagram is no worse for it.

**One gap handed to [phase 5](../phase_5_project_io.md) rather than guessed
at.** `MediaFile` has no `missing` flag. F-3 wants a load to mark media it
could not find, but that is session state — it depends on the machine, not the
file — and putting it in the Entities block would make the
documentation-walking test assert that a non-persisted field is part of the
format. Phase 5 adds it with a reason and amends `03`.
