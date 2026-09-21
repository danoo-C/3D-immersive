# M1 — Core model, headless

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Workflow:
[09-workflow.md](../09-workflow.md)

The first milestone that builds the product rather than the scaffolding around
it, and the last one with no UI at all. Everything here lives in
`src/immersive/core/`, imports neither Qt nor `sounddevice`, and is testable
with no window open and no audio device — which is N-5, and which is what makes
the whole thing verifiable on WSL.

| Phase | Status |
|---|---|
| [1 — Dataclasses](phase_1_dataclasses.md) | ✅ |
| [2 — Curve evaluation](phase_2_curve_evaluation.md) | not started |
| [3 — Time and snapping](phase_3_time_and_snapping.md) | not started |
| [4 — Undo stack](phase_4_undo_stack.md) | not started |
| [5 — Project I/O](phase_5_project_io.md) | not started |

The order is dependency order, and each phase is usable on its own. Phase 1
defines the shapes; 2 and 3 make two of them mean something; 4 is the only way
anything is allowed to change; 5 makes it survive a restart. Curve *shapes* are
phase 1 and curve *evaluation* is phase 2 deliberately — the model needs the
type to exist, not to work.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> a project can be built in code, edited, undone, saved, reloaded and compared
> equal — all in pytest, with no window open.

## Already delivered

One M1 bullet is done and one is half done.

`numpy>=2.0` was pinned during S0 (D-38), because the spike exercises the same
`rfft`/`irfft` path the realtime callback will.

The **import-graph test** exists from M0, in `tests/test_layering.py`, and it
carries its own test proving the detector is not passing vacuously — which it
has been, because `core/` has been empty. Phase 1 is the first time that test
has anything to bite on. Nothing to build; something to watch.

## What this milestone does not deliver

| Not here | Where |
|---|---|
| Decoding, resampling, peak pyramids | M2 — this milestone stores a `MediaFile`'s *metadata*, and never opens an audio file |
| Selection (D-57) | M3, with the timeline that makes it mean something. `core/selection.py` in [02](../02-architecture.md)'s layout stays empty until then |
| Cut/copy/paste (F-50, D-58) | M3 — the commands exist here, the clipboard does not |
| Autosave and the recovery sidecar (F-49, D-64) | M8 |
| The `.3dimtheme` format | M9, which is a different file with a different schema |
| Anything that draws, plays or allocates a buffer | M3 onward |

## Notes

Appended as phases complete.
