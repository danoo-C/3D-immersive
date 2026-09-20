# Documentation

| | |
|---|---|
| [00 — Overview](00-overview.md) | What the app is, the stack, what is in and out of scope |
| [01 — Requirements & Decisions](01-requirements.md) | Numbered requirements and the decision log |
| [02 — Architecture](02-architecture.md) | Layering, repo layout, threading, the port seam |
| [03 — Data Model](03-data-model.md) | Coordinates, time, entities, the `.3dim` file format |
| [04 — UI Specification](04-ui-spec.md) | Layout, palette, every panel and interaction |
| [05 — Audio Engine](05-audio-engine.md) | HRTF pipeline, the per-block hot path, realtime safety |
| [06 — Roadmap](06-roadmap.md) | Nine milestones and the risk register |
| [07 — QA Archive](07-qa-archive.md) | Closed: every question asked, the answer given, and where it landed |
| [08 — Environment](08-environment.md) | venv, `launch.py`, the `installer.py` spec, and why not PyPy |
| [09 — Workflow](09-workflow.md) | How a milestone gets built: per-milestone directories, phases and plans |

Alongside these, each milestone under way has its own directory —
`m1_core_model/` and so on — holding one document per build phase and a
`plans/` subdirectory beside them. [09](09-workflow.md) defines that system;
the directories are created one milestone at a time, as work reaches them.

The original hand-written spec is in [`../README.md`](../README.md) and is kept
as the source of intent; where it and these documents disagree, these win —
but the disagreement should be recorded in the decision log.

## Reading order

New to the project: 00 → 01 → 06.
Setting up to run it: 08.
About to build something: 09, then the current milestone's directory.
Implementing: 02 → 03 → the document for the area you're in.
Deciding something: check the decision log in 01 before re-opening it, and
[07](07-qa-archive.md) for why it went that way.

There are no open questions. Section C of [07](07-qa-archive.md) lists the
assumptions that were accepted rather than answered directly — those are the
soft spots most worth revisiting first if something turns out wrong.
