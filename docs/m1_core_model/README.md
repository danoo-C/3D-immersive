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
| [2 — Curve evaluation](phase_2_curve_evaluation.md) | ✅ |
| [3 — Time and snapping](phase_3_time_and_snapping.md) | ✅ |
| [4 — Undo stack](phase_4_undo_stack.md) | ✅ |
| [5 — Project I/O](phase_5_project_io.md) | ✅ |

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

**M1 is complete.** A project can be built in code, edited through the undo
stack, undone, saved, reloaded and compared equal, all in pytest with no
window open and no audio device — which is the milestone's own acceptance and
also N-5, and it is why every phase of this milestone could be verified on
WSL.

What the five phases found, one line each, with the detail in each phase's
Notes:

| Phase | What it turned up |
|---|---|
| 1 — Dataclasses | `03` had no id scheme at all: it called `MediaFile.id` a uuid while its example used hand-written mnemonics, and neither was implementable |
| 2 — Curve evaluation | two of five mutations went uncaught, and they were the two things the plan had argued hardest for — the handle clamp and the solver's bisection bracket. Every plan since names its mutations up front because of this |
| 3 — Time and snapping | 960 ticks per beat rather than 1000, because F-16's triplets are not expressible in a resolution that is not divisible by three |
| 4 — Undo stack | the stack applies, validates and rolls back rather than predicting, so no command re-derives the rules it might break — and the one surviving mutation is unreachable, pinned by a test that asserts why |
| 5 — Project I/O | `03`'s own worked example of the file format was not loadable, and a round trip cannot tell a reader and a writer that are wrong together from two that are right |

The habit that came out of phase 2 — **name the mutations before writing the
tests, then run them against the finished suite** — has now been applied in
every phase of this milestone. Phase 5 named thirty-eight and four survived
their first run; all four were real, and the two lessons behind them are about
testing a *format* rather than a model:

- **A round trip proves the reader and the writer agree, not that either is
  right.** Every assertion that pins the format has to read the file.
- **A cross-platform behaviour asserted only end to end is asserted on one
  platform.** CI is Linux, `as_posix()` is a no-op there, and deleting the
  separator conversion left the whole suite green.

M9 inherits both with `.3dimtheme`, which is a different file with the same
shape of problem.
