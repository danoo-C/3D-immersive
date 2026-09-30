# M5 · Phase 5 — Measured with the views playing

**Status:** ✅ · **Plan:** [plans/phase_5_measured.md](plans/phase_5_measured.md)

## Goal

The views repaint during playback: while a source is dragged, and when the
selection or a field changes. This phase measures that with the views as
the load, 32 channels placed and one dragged continuously. It uses
`python -m immersive.benchmark contention`, taught a load that drags, and
records the views' repaint cost. N-2 asks for no dropouts during normal UI
interaction, and dragging is the interaction M5 adds.

## Scope

**In:** a `dragging` load for `contention`; the views' repaint cost; the
counts recorded; making a repaint cheaper if the counts ask for it.

**Out:** the live count on the listening machine → phase 6.

## Acceptance

- [x] With one source dragged continuously during playback and 32 placed,
      the stand-in stream at 1 ms misses no more than one block in a
      thousand. *0 of 2252 at 1 ms, and 0 of 2247 at 5 ms (Notes).*
- [x] Each view's repaint time with 32 channels is recorded. *As points
      and as pairs; the 3D view made cheaper first (Notes).*

## Implements

N-2; D-137 to D-142's measurement, with the views as the load.

## Notes

Appended while building.

**Built and run (2026-09-30)** on the development machine: an i5-11400H
under WSL2, Python 3.13.12, numpy 2.4.6, SADIE II D1 at 512 frames,
offscreen. Nothing else ran meanwhile.

**The views' repaint** (`views`, 200 each, in ms), the window at its first
size, 32 sources and one bypassed:

| View | Points p50 | p99 | Pairs p50 | p99 |
|---|---|---|---|---|
| top | 1.23 | 2.77 | 3.38 | 5.96 |
| front | 1.12 | 1.39 | 3.31 | 6.61 |
| bypass strip | 0.17 | 0.26 | 0.19 | 0.36 |
| 3D | 2.91 | 4.83 | 7.11 | 11.10 |
| the whole window | 49.36 | 76.08 | 61.28 | 97.41 |

**The 3D view was made cheaper before it was recorded.** The first run
had it at 8.4 ms for points and 43 ms for pairs at the median, over two
frames at 60 Hz. Each point it drew worked out the camera again, and the
camera is a pass over every source, so a paint was quadratic in the
sources. It now works the camera out once a paint (`Projection`). The
ortho views never had this: their scale is `Scale`'s, a constant.

**With the window loaded** (`contention`, three rounds of 8 s, in turn),
blocks missed:

| Load | 5 ms | 1 ms | p99 at 1 ms |
|---|---|---|---|
| playing | 0 of 2253 | 0 of 2253 | 1.60 |
| scrolling | 0 of 2253 | 0 of 2251 | 2.09 |
| repainting | 18 of 2252 | 0 of 2256 | 6.29 |
| **dragging** | **0 of 2247** | **0 of 2252** | 3.53 |

A drag costs the UI thread a movement's work every 16 ms: `Placing`, a
`POSITION` command or two, both views and the pane's fields. The engine
does not notice it. The whole window repainted without pause remains the
heaviest load, and at D-39's 1 ms it misses nothing, as at M4 phase 12.
