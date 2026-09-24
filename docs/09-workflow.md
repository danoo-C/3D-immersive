# 09 — Development Workflow

How a milestone gets built. The numbered documents `00`–`08` describe the
*product*; this one describes the *process*, and it is the only document that
grows while work is happening.

Its companion is [doc-system.md](doc-system.md), which governs how the
documents themselves are written, numbered and changed. The split: that file
owns the containers, this one owns the sequencing.

## The shape

Each milestone gets a directory, created when that milestone starts and not
before:

```
docs/
  06-roadmap.md                    ← milestone level. The index of truth.
  m1_core_model/
    README.md                      ← this milestone's phase list and status
    phase_1_dataclasses.md         ← what this phase is
    phase_2_curve_evaluation.md
    phase_3_undo_stack.md
    plans/
      phase_1_dataclasses.md       ← how it will be built
      phase_2_curve_evaluation.md
```

Three levels, each answering a different question:

| Level | Lives in | Answers | Written when |
|---|---|---|---|
| **Milestone** | `06-roadmap.md` | What are we building, in what order, and why this order | Once, up front. Already done. |
| **Phase** | `<milestone>/phase_N_*.md` | What is this slice, and how do we know it is finished | At the start of the milestone |
| **Plan** | `<milestone>/plans/phase_N_*.md` | What are the actual steps, files and risks | Immediately before building that phase |

The split between a phase and its plan is the part worth holding onto. **A
phase is a contract; a plan is a route.** The phase says what must be true when
you are done and does not change once agreed. The plan says how you intend to
get there and is expected to be wrong in places — it gets amended while you
work. Collapsing them into one document loses the ability to tell "we changed
our mind about the goal" from "we found a better way to the same goal", and
those need to be distinguishable six months later.

## Naming

Lowercase, underscores, no spaces — the project is cross-platform and some of
those filesystems are case-insensitive.

```
docs/<milestone_id>_<short_name>/
docs/<milestone_id>_<short_name>/phase_<n>_<short_name>.md
docs/<milestone_id>_<short_name>/plans/phase_<n>_<short_name>.md
```

A plan **mirrors its phase's filename exactly**. That is the whole convention
for pairing them: `plans/phase_2_curve_evaluation.md` belongs to
`phase_2_curve_evaluation.md`, and a plan with no matching phase is a mistake.

Reserved directory names, matching [06-roadmap.md](06-roadmap.md). A directory
exists only once its milestone has started, so a blank row below is a
milestone nobody has opened yet:

| | |
|---|---|
| `m0_scaffolding/` | complete — built before this system existed, no phase docs |
| `s0_listening_spike/` | complete — the throwaway spike; got a directory like anything else |
| `m1_core_model/` | complete |
| `m2_media/` | **in progress** |
| `m3_timeline/` | |
| `m4_binaural_engine/` | |
| `m5_spatial_workspace/` | |
| `m6_automation/` | |
| `m7_render/` | |
| `m8_polish_and_ship/` | |
| `m9_theming/` | complete — built after M1, not last; see [06](06-roadmap.md) |

## Sizing a phase

A phase is **one sitting's worth of work with a single testable outcome** —
roughly one to a handful of commits. If a phase needs more than about six
steps in its plan, it is two phases.

The test: can you write the acceptance checklist before writing any code, and
is every line of it something a test or a screenshot can settle? If the
acceptance is "the model is nicer", it is not a phase yet.

## Naming the mutations

Every plan since M1 phase 2 ends with a table of **mutations named before the
tests are written** — specific ways this code could be broken — which are then
applied one at a time against the finished suite. A mutation nothing notices
is a test that asserts a mechanism without distinguishing it, which is exactly
what that phase found in two of its own tests and why the habit exists.

It is in every plan and was in no document, so: the shape of it.

1. **Name them in the plan**, before the tests exist. A list written afterwards
   is written to flatter the tests that got written.
2. Apply each one, run the phase's tests, restore, and record caught or
   survived.
3. A survivor is one of two things, and saying which is the point. Either a
   **missing test** — write it — or an **equivalent mutation**, one the code's
   own invariants make unreachable. Pin an equivalent one with a test that
   asserts *why* it cannot fire, rather than quietly dropping it from the
   list. M1 phase 4's unreachable `bisect` edge and M9 phase 1's group-value
   fallback are the worked examples.

⚠️ **Run them with `PYTHONDONTWRITEBYTECODE=1`, and purge `__pycache__` first.**
A mutation the same byte length as the original, restored within the same
second, leaves a `.pyc` that Python still considers valid — the cache is
keyed on mtime to the second plus size, and neither changed. The *next* run
then silently tests the previous mutation against the restored source. Found
in M9 phase 1, where `#252526` became `#101010` and six tests then failed
against a file that was already correct. It can produce a false result in
either direction and it leaves no trace in the source.

## Lifecycle

1. **Milestone starts.** Create `docs/<id>_<name>/` and its `README.md`. Break
   the roadmap's bullet list into phases and write one phase doc per phase.
   No plans yet.
2. **A phase starts.** Write `plans/phase_N_*.md`. This is the last moment
   before code — everything that is unclear should surface here, not halfway
   through the implementation.
3. **While building.** Amend the plan as reality intervenes; leave what changed
   visible rather than rewriting history. Append findings to the phase doc's
   Notes. Do not edit the phase's Goal or Acceptance — if those need to change,
   say so explicitly and note why.
4. **Phase ends.** Fill in the plan's Outcome, tick the phase's acceptance
   boxes, mark the phase ✅ in the milestone README.
5. **Milestone ends.** Mark it ✅ in `06-roadmap.md` with a short paragraph of
   what was delivered, as M0 already does. Nothing is deleted — the directory
   stays as the record.

## What goes where

The most common way a system like this rots is documents drifting into each
other. The rule:

| Kind of thing | Belongs in | Never in |
|---|---|---|
| A decision with a rationale | the decision log in [01-requirements.md](01-requirements.md) | a phase or plan doc |
| How to write any of these documents | [doc-system.md](doc-system.md) | here |
| A change to how the product behaves | the relevant numbered doc (`02`–`05`) | a phase doc |
| A new requirement | `01-requirements.md` as a new F-number | anywhere else |
| What we are building this week | a phase doc | `06-roadmap.md` |
| Which files to touch and in what order | a plan | a phase doc |
| Something surprising found while building | the phase's Notes, and if it is a decision, *also* the decision log | only the plan |

A phase doc that quietly contains a design decision is a decision nobody will
find. Write it in the log and link to it.

## Templates

### Milestone `README.md`

```markdown
# M1 — Core model

Roadmap entry: [06-roadmap.md](../06-roadmap.md)

| Phase | Status |
|---|---|
| [1 — Dataclasses](phase_1_dataclasses.md) | ✅ |
| [2 — Curve evaluation](phase_2_curve_evaluation.md) | in progress |
| [3 — Undo stack](phase_3_undo_stack.md) | not started |

## Milestone acceptance
Copied verbatim from the roadmap's "Done when".
```

### Phase — `phase_N_<name>.md`

```markdown
# M1 · Phase 2 — Curve evaluation

**Status:** in progress · **Plan:** [plans/phase_2_curve_evaluation.md](plans/phase_2_curve_evaluation.md)

## Goal
One paragraph. What exists after this that did not before.

## Scope
**In:** …
**Out:** … (and where it went instead — a later phase, a later milestone)

## Acceptance
- [ ] Each line testable. A test name, a command, or a screenshot.
- [ ] No line that a reasonable person could call done or not done.

## Implements
F-29, F-30, D-7 — and the section of [03-data-model.md](../03-data-model.md)
they come from.

## Notes
Appended while building. Surprises, dead ends, things the next phase inherits.
```

### Plan — `plans/phase_N_<name>.md`

```markdown
# Plan — M1 · Phase 2 — Curve evaluation

**Written:** 2026-09-20 · **Status:** in progress

## Approach
A paragraph on the shape of the solution, and the alternative that was
rejected. If there was no alternative, say so.

## Steps
1. … each one independently committable, with its test
2. …

## Files
`src/immersive/core/curves.py` — new
`tests/test_curves.py` — new

## Risks and unknowns
What might make this take twice as long.

## Out of scope for this plan
Things a reader might reasonably expect here, and where they actually are.

## Outcome
Filled in at the end. What actually happened, what the plan got wrong, and
anything the next phase needs to know.
```

## Git

One commit per plan step where the step is independently meaningful; squashing
a phase into a single commit is fine when the steps are not. The phase doc and
its plan are committed **with the code they describe**, not separately — a
phase marked complete in one commit and implemented in another is a lie for as
long as the gap lasts.

Commit subjects name the phase: `m1 phase 2: curve evaluation`.

## Why this exists rather than issues or a board

Because the documents are in the repository, they are reviewable in the same
diff as the code, they work offline, and they survive whatever tracker the
project is or is not using in two years. The cost is discipline: a stale phase
doc is worse than no phase doc, which is why the lifecycle above ends with
marking things complete rather than trailing off.
