# M1 · Phase 1 — Dataclasses

**Status:** not started · **Plan:** not written yet

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

- [ ] Every entity and field in [03](../03-data-model.md)'s Entities block
      exists, with the same names, and a test walks that list rather than
      trusting a reading of it.
- [ ] `Project.length` is **derived** from the last clip end and is not a
      stored field (D-53). Zero for an empty project; automation past the last
      clip does not extend it.
- [ ] There is no `Channel.index` anywhere, asserted (D-61). Reordering is a
      list operation and nothing else has to be kept in step.
- [ ] Solo is additive, non-soloed channels are silent while any solo is on,
      and an explicit mute still wins on its own channel (D-62). Expressed as a
      pure function over the channel list, so M3 and M4 share one answer.
- [ ] Clips on one channel never overlap and `offset + length` never exceeds
      `MediaFile.frames` — checked by a validator that returns *what* is wrong,
      not just that something is. Phase 5 needs the reasons to report them.
- [ ] `hrtf_bypass` is a plain bool, `pan` exists alongside the `pos.*` curves,
      and toggling bypass in either direction destroys no automation (F-42).
      A dataclass cannot get this wrong, but a test says so before anything
      later can.
- [ ] Two projects built identically compare equal, and comparison ignores
      nothing that matters — the milestone's own acceptance ends in "compared
      equal", so the comparison is load-bearing rather than incidental.
- [ ] `tests/test_layering.py` still passes with `core/` no longer empty, and
      its vacuity guard still passes too.

## Implements

The Entities and Rules sections of [03-data-model.md](../03-data-model.md).
F-10, F-12, F-42. D-6, D-11, D-53, D-61, D-62, and the bypass family D-32
through D-35. The module layout and the empty-`__init__` rule are D-29 and the
*Repository layout* section of [02-architecture.md](../02-architecture.md).

## Notes

Appended while building.
