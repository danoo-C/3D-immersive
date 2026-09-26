# M4 · Phase 3 — Directions

**Status:** planned · **Plan:** [plans/phase_3_directions.md](plans/phase_3_directions.md)

## Goal

`audio/hrtf/lookup.py` answers "which measurements, and how much of each?"
for any direction: the triangle of the set's triangulated sphere that
contains it, and barycentric weights over its three corners (05, *3.
Spherical interpolation*). It answers for a whole block's sources in one
call, without allocating, so that phase 5 can ask it on the audio thread.
The triangle is found through a cube-map index and a walk rather than 05's
KD-tree, which allocates on every query (D-119).

## Scope

**In:** the triangulation by `scipy.spatial.ConvexHull`, built once per set;
the cube-map index, built with a centroid KD-tree off the audio thread;
the containing-triangle test and the walk; weights for a batch of
directions into preallocated arrays; the degenerate cases (a direction
exactly on an edge or a vertex, the poles); how a direction below the set's
lowest measurement is handled.

**Out:** what the weights are applied to → phases 4 and 5.

## Acceptance

- [ ] Every one of SADIE II D1's 8802 directions finds itself with a weight
      of 1 on its own vertex.
- [ ] For ten thousand random directions, the weights are non-negative, sum
      to 1, and reconstruct the direction from their triangle's corners.
- [ ] A direction on an edge or at a pole gets a valid triangle, never none.
- [ ] A batch of 32 directions is weighed with no array made inside the
      call, checked by the zero-allocation test's method.
- [ ] Weighing 32 directions takes a measured fraction of a block, recorded
      in the Notes against the spike's.

## Implements

*The HRTF pipeline, 3.* in [05-audio-engine.md](../05-audio-engine.md);
S0 [phase 3](../s0_listening_spike/phase_3_interpolation.md).

## Notes

Appended while building.
