# M1 · Phase 3 — Time and snapping

**Status:** not started · **Plan:** not written yet

## Goal

`core/time.py` converts between the three ways this application talks about
time — samples, seconds, bars:beats — and snaps a sample position to the grid
or to a neighbouring clip edge. Samples stay the single source of truth; the
other two are views (D-11, and the *Time* section of
[03-data-model.md](../03-data-model.md)).

## Scope

**In:** samples ↔ seconds; samples ↔ bars:beats:ticks from `bpm` and
`time_signature`; snap divisions 1/1 through 1/32 plus triplets and "off"
(F-16); snapping to the grid **and** to other clips' edges (F-17); the
per-channel override, including disabling it (F-18).

**Out:** the ruler and its bars:beats ↔ min:sec toggle → M3, which displays
what this computes. Holding `Alt` to bypass snap → M3; it is an input gesture,
and this phase provides the "off" it resolves to. Tempo maps → never (D-26).

## Acceptance

- [ ] Round-trip: samples → bars:beats → samples is exact for every position on
      the grid, and the round-trip error never exceeds half a tick off it.
      Everything downstream assumes this and nothing else checks it.
- [ ] Every division from 1/1 to 1/32 and every triplet variant produces the
      grid spacing it claims, at 4/4 and at one other time signature. A
      division that is silently wrong is an arrangement that will not line up,
      discovered by ear three milestones later.
- [ ] Snapping picks the **nearest** candidate among the grid and the clip
      edges in range, not the nearest grid line with clip edges as an
      afterthought (F-17). Asserted with a clip edge deliberately placed just
      inside a grid line.
- [ ] A channel's `snap_override` wins over `Project.snap`, including when it
      disables snapping entirely (F-18); `null` inherits.
- [ ] Snapping is idempotent: snapping an already-snapped position returns it
      unchanged. A snap that drifts on repeated application will move clips
      that nobody dragged.
- [ ] **Changing the BPM moves the grid and not the material** (D-52).
      Asserted directly: build an arrangement, change `bpm`, and every clip
      `start` and every keyframe `t` is unchanged while their bars:beats
      readings are not. This is the surprising behaviour in the whole model,
      so it gets a test that states it rather than a comment.
- [ ] Nothing in this module reads or writes a `Project`. It takes the numbers
      it needs, so M4 can call it without a model and M3 can call it per
      mouse-move without allocating one.

## Implements

F-16, F-17, F-18, F-19. D-11, D-26, D-52. The *Time* section of
[03-data-model.md](../03-data-model.md), which owns the rule that samples are
the truth and everything else is a view.

## Notes

Appended while building.
