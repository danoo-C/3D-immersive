# M5 · Phase 5 — Measured with the views playing

**Status:** in progress · **Plan:** [plans/phase_5_measured.md](plans/phase_5_measured.md)

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

- [ ] With one source dragged continuously during playback and 32 placed,
      the stand-in stream at 1 ms misses no more than one block in a
      thousand.
- [ ] Each view's repaint time with 32 channels is recorded.

## Implements

N-2; D-137 to D-142's measurement, with the views as the load.

## Notes

Appended while building.
