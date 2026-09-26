# M4 · Phase 3 — Directions

**Status:** not started · **Plan:** not written yet

## Goal

`audio/hrtf/lookup.py` answers "which measurements, and how much of each?"
for any direction: the triangle of the set's triangulated sphere that
contains it, found through a KD-tree over face centroids, and barycentric
weights over its three corners (05, *3. Spherical interpolation*). It
answers for a whole block's sources in one call, without allocating, so
that phase 5 can ask it on the audio thread.

## Scope

**In:** the triangulation by `scipy.spatial.ConvexHull`, built once per set;
the centroid KD-tree; the containing-triangle test; weights for a batch of
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
