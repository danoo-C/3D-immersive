# User issues

What came up from using the application rather than from the plan: a report,
a question, or a plan asked for. Each has its own file or folder here. None
of it is part of the numbered canon. When something lands, the facts it
establishes move to their proper home (a decision in
[01-requirements](../01-requirements.md), the spec, a phase doc), and the file
here stays as the record of how it came up.

## Where each one stands

| Issue | Status | Progress |
|---|---|---|
| [3D sensitivity](3d-sensitivity/README.md): a centimetre swings a sound from ear to ear, and a stem at the listener distorts | **Confirmed.** Fixed by [M4 phase 8](../m4_binaural_engine/phase_8_level_as_mixed.md), and heard: "exactly what I imagined" | `██████████` 100 % |
| [Stereo placement](stereo-placement/README.md): a stereo channel as two sources, independent or linked in symmetry | **Built** in the engine and the pane by [M4 phase 9](../m4_binaural_engine/phase_9_stereo_placement.md), to be heard. The views draw it at M5 | `████████░░` 80 % |
| [Test speed](tests-speeds.md): making the suite faster | **Steps 1–6 done.** Four follow-ups open, one of them blocked while CI cannot run | `████████░░` 81 % |

## How progress is counted

An issue passes through five stages, each worth two blocks of the bar:

| Stage | Means |
|---|---|
| Reported | written down, in the words it was raised in |
| Understood | the cause found and measured, or the ask stated back and agreed |
| Designed | what to build decided, with its open questions named |
| Built | in the code, tested, its decisions in the canon |
| Confirmed | heard or used by the person who raised it, and found right |

A plan with its own checklist, like the test-speed plan, counts its items
instead: 17 of 21 there.

## The files

**3D sensitivity**, [3d-sensitivity/](3d-sensitivity/README.md):

- [Why a centimetre can swing a sound from one ear to the other](3d-sensitivity/README.md):
  the report, explained and measured.
- [Why a placed channel at (0, 0, 0) distorts](3d-sensitivity/too-loud-at-the-listener.md):
  the second report, measured on the drum stem.
- [Level as mixed](3d-sensitivity/level-as-mixed.md): the design that fixed
  both, built as M4 phase 8 (D-128 to D-131).

**Stereo placement**, [stereo-placement/](stereo-placement/README.md):

- [A stereo channel as two sources](stereo-placement/README.md): the modes,
  the symmetry link, what was agreed on 2026-09-27, and how each open point
  was settled when it was built as M4 phase 9 (D-132 to D-135).

**Test speed**:

- [Test speed — plan](tests-speeds.md): the argument, the measurements, and
  the steps.
